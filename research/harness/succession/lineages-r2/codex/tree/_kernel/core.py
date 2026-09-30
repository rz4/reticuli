"""Small, standard-library-only primitives for claim handling.

The constants in this module are shared with the layers above the kernel.
Filesystem helpers raise ClaimError when untrusted claim data cannot be used.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import platform
import shutil
import stat
import tempfile
from pathlib import Path


class ClaimError(Exception):
    """A claim cannot be used as requested."""


NAMESPACE = "reticuli"
DIGEST = "sha256"
FORMAT = 3
STORE = ".reticuli"
MANIFEST = ".reticuli/manifest.json"
RECIPE = "reticuli.toml"
LEGACY_RECIPE = "claim.toml"
LEDGER = ".reticuli/ledger.jsonl"
USAGE = ".reticuli/usage.json"
MUTATION_RESIDUE = ".reticuli/mutation_score.json"
SIGN_DIR = ".reticuli/mint"
SIGN_NAMESPACE = "reticuli.mint"

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

GATE_TIMEOUT = 120.0
FURNISH_TIMEOUT = 300.0
PRODUCER_TIMEOUT = 3600.0
TOLERANCE = 2.0
MUTANT_CEILING = 100
MUTANT_FLOOR = 0.0
MUTANT_HEADROOM = 10
COST_KEYS = ("usd", "tokens", "calls", "seconds")
COST_LADDER = COST_KEYS
COST_UNITS = COST_KEYS
GUIDANCE_KEYS = ("guidance", "request")
KINDS = frozenset(("produce", "gate"))
_SHELL = "/bin/sh"


def _now() -> str:
    """Return the current UTC time in the record timestamp form."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe(directory: os.PathLike[str] | str, name: str) -> str:
    """Resolve a recipe path beneath *directory*, rejecting aliases and escapes."""
    if not isinstance(name, str) or not name or os.path.isabs(name):
        raise ClaimError(f"invalid claim path: {name!r}")
    components = Path(name).parts
    if not components or any(part == ".." for part in components):
        raise ClaimError(f"claim path escapes directory: {name!r}")
    base = os.path.realpath(directory)
    candidate = os.path.join(base, name)
    cursor = base
    for part in components:
        cursor = os.path.join(cursor, part)
        if os.path.islink(cursor):
            raise ClaimError(f"symlink in claim path: {name!r}")
    resolved = os.path.realpath(candidate)
    if os.path.commonpath((base, resolved)) != base or resolved == base:
        raise ClaimError(f"claim path escapes directory: {name!r}")
    return resolved


def _hash_file(path: os.PathLike[str] | str) -> str:
    """Return plain SHA-256 of a regular, singly linked file's bytes."""
    try:
        info = os.lstat(path)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ClaimError(f"not a regular singly linked file: {path}")
        digest = hashlib.sha256()
        with open(path, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
                raise ClaimError(f"not a regular singly linked file: {path}")
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError as exc:
        raise ClaimError(f"cannot hash file {path}: {exc}") from exc


def _write_json(path: os.PathLike[str] | str, value: object) -> None:
    """Atomically replace a JSON document, with canonical key ordering."""
    target = os.fspath(path)
    parent = os.path.dirname(os.path.abspath(target))
    os.makedirs(parent, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=parent,
                                         prefix=".reticuli-", delete=False) as stream:
            temporary = stream.name
            json.dump(value, stream, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if temporary is not None and os.path.exists(temporary):
            os.unlink(temporary)


def _copy_into(source: os.PathLike[str] | str, destination: os.PathLike[str] | str) -> str:
    """Copy a regular file to a destination path, creating its parent."""
    _hash_file(source)
    target = os.fspath(destination)
    os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
    shutil.copyfile(source, target)
    return target


def _judging_host() -> dict[str, str]:
    """Describe the host and interpreter used to judge a claim."""
    return {
        "platform": platform.system().lower(),
        "machine": platform.machine(),
        "runtime": platform.python_implementation() + " " + platform.python_version(),
    }
