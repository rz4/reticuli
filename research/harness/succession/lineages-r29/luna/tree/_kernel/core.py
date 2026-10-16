"""Shared constants and low-level primitives for the Reticuli kernel.

This module is deliberately limited to the Python standard library.  In
particular, file hashing and path resolution are strict boundaries: declared
paths must stay inside a claim and hashed files must be regular, unaliased
files.
"""

import datetime
import hashlib
import json
import os
import platform
import shutil
import stat
import tempfile
import sys


# On-disk and environment protocol.
NAMESPACE = "reticuli"
DIGEST = "sha256"
FORMAT = 4
STORE = ".reticuli"
MANIFEST = ".reticuli/manifest.json"
RECIPE = "reticuli.toml"
LEGACY_RECIPE = "claim.toml"
LEDGER = ".reticuli/ledger.jsonl"
USAGE = ".reticuli/usage.json"
MUTATION_RESIDUE = ".reticuli/mutation_score.json"
SIGN_DIR = ".reticuli/mint"
SIGN_NAMESPACE = "reticuli.mint"
RECORD_NAMESPACE = "reticuli.record"
RECORD_FORMAT = 1

_JAILED = "RETICULI_JAILED"
_ENV_CACHE = "RETICULI_ENV_CACHE"
_ENV_CLAIM = "RETICULI_CLAIM"
_ENV_MODEL = "RETICULI_MODEL"
_ENV_OUTPUT = "RETICULI_OUTPUT"
_ENV_OUTPUTS = "RETICULI_OUTPUTS"
_ENV_REQUEST = "RETICULI_REQUEST"
_ENV_SIGNERS = "RETICULI_SIGNERS"
_ENV_TIMEOUT = "RETICULI_GATE_TIMEOUT"
_ENV_TOLERANCE = "RETICULI_TOLERANCE"
_ENV_USAGE = "RETICULI_USAGE"
_ENV_VENDOR = "RETICULI_VENDOR"
_KEEP_ENV = ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "TZ", _JAILED)

# Policy/tuning defaults. The format pins the vocabulary; these defaults are
# kept centralized so all kernel layers can share them.
GATE_TIMEOUT = 120.0
FURNISH_TIMEOUT = 600.0
PRODUCER_TIMEOUT = 600.0
TOLERANCE = 2.0
MUTANT_CEILING = 100
MUTANT_FLOOR = 0.0
MUTANT_HEADROOM = 0.1
COST_KEYS = ("usd", "tokens", "calls", "seconds")
COST_LADDER = ("usd", "tokens", "calls", "seconds")
COST_UNITS = ("usd", "tokens", "calls", "seconds")
GUIDANCE_KEYS = ("guidance", "request")
KINDS = frozenset({"produce", "gate"})
_SHELL = "/bin/sh"


class ClaimError(Exception):
    """A refusal caused by invalid claim data or an unsafe operation."""


def _safe(root, name):
    """Resolve a declared relative path beneath *root*, refusing escapes.

    Every existing component is checked with lstat so symlinks are rejected,
    including links whose targets happen to remain inside the claim.
    """
    if not isinstance(name, str) or not name:
        raise ClaimError("claim path must be a non-empty relative path")
    if os.path.isabs(name):
        raise ClaimError(f"absolute claim path is not allowed: {name!r}")

    # Accept either separator as a path separator, independent of host OS.
    components = name.replace("\\", "/").split("/")
    if any(part in ("", ".", "..") for part in components):
        raise ClaimError(f"unsafe claim path: {name!r}")

    base = os.path.realpath(os.fspath(root))
    current = base
    for component in components:
        current = os.path.join(current, component)
        try:
            info = os.lstat(current)
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise ClaimError(f"cannot inspect claim path {name!r}: {exc}") from exc
        if stat.S_ISLNK(info.st_mode):
            raise ClaimError(f"symlink in claim path is not allowed: {name!r}")

    resolved = os.path.realpath(current)
    try:
        inside = os.path.commonpath((base, resolved)) == base
    except ValueError:
        inside = False
    if not inside:
        raise ClaimError(f"claim path escapes its directory: {name!r}")
    return resolved


def _hash_file(path):
    """Return the SHA-256 hex digest of a regular file's exact bytes.

    Hard links and special files are refused to prevent aliases and blocking
    reads from entering a claim's identity.
    """
    path = os.fspath(path)
    try:
        info = os.lstat(path)
    except OSError as exc:
        raise ClaimError(f"cannot read file {path!r}: {exc}") from exc
    if stat.S_ISLNK(info.st_mode):
        raise ClaimError(f"refusing symlink file: {path!r}")
    if not stat.S_ISREG(info.st_mode):
        raise ClaimError(f"refusing non-regular file: {path!r}")
    if info.st_nlink != 1:
        raise ClaimError(f"refusing file with multiple hard links: {path!r}")

    digest = hashlib.sha256()
    try:
        with open(path, "rb") as stream:
            # Check the opened inode as well, avoiding a simple lstat/open race.
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
                raise ClaimError(f"refusing aliased or non-regular file: {path!r}")
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except ClaimError:
        raise
    except OSError as exc:
        raise ClaimError(f"cannot hash file {path!r}: {exc}") from exc
    return digest.hexdigest()


def _write_json(path, value):
    """Atomically write canonical JSON to *path* (default JSON spacing)."""
    path = os.fspath(path)
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    data = (json.dumps(value, sort_keys=True, ensure_ascii=True) + "\n").encode("utf-8")
    fd, temporary = tempfile.mkstemp(prefix="." + os.path.basename(path) + ".", dir=parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        # Persist the directory entry where the host supports directory fsync.
        try:
            directory_fd = os.open(parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            pass
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _now():
    """Return the current UTC timestamp in an interoperable ISO form."""
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _copy_into(source, destination):
    """Copy *source* into an existing or newly created destination directory."""
    source = os.fspath(source)
    destination = os.fspath(destination)
    if os.path.isdir(source):
        os.makedirs(destination, exist_ok=True)
        for name in os.listdir(source):
            src = os.path.join(source, name)
            dst = os.path.join(destination, name)
            if os.path.isdir(src) and not os.path.islink(src):
                shutil.copytree(src, dst, dirs_exist_ok=True, symlinks=False)
            elif os.path.islink(src):
                raise ClaimError(f"refusing to copy symlink: {src!r}")
            else:
                shutil.copy2(src, dst)
    else:
        os.makedirs(os.path.dirname(os.path.abspath(destination)), exist_ok=True)
        shutil.copy2(source, destination)
    return destination


def _judging_host():
    """Describe this host for a verification/record environment field."""
    return {
        "platform": platform.system().lower(),
        "machine": platform.machine(),
        "runtime": platform.python_implementation() + " " + platform.python_version(),
    }
