"""Small, dependency-free primitives shared by the Reticuli kernel.

This module is deliberately the bottom of the package: it owns the common
on-disk names, refusals, safe path handling, and a few host/file helpers.
"""

from __future__ import annotations

import hashlib
import json
import ntpath
import os
import platform
import shutil
import stat
import tempfile
from datetime import datetime, timezone


# Shared on-disk and environment protocol.
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
_KEEP_ENV = (
    "PATH",
    "HOME",
    "TMPDIR",
    "LANG",
    "LC_ALL",
    "TZ",
    "RETICULI_JAILED",
)

# Policy defaults used by the higher kernel layers.
GATE_TIMEOUT = 120.0
FURNISH_TIMEOUT = 600.0
PRODUCER_TIMEOUT = 3600.0
TOLERANCE = 2.0
MUTANT_CEILING = 100
MUTANT_FLOOR = 0.6
MUTANT_HEADROOM = 0.1
COST_KEYS = ("usd", "tokens", "calls", "seconds")
COST_LADDER = ("usd", "tokens", "calls", "seconds")
COST_UNITS = ("usd", "tokens", "calls", "seconds")
GUIDANCE_KEYS = ("guidance", "request")
KINDS = frozenset({"produce", "gate"})
_SHELL = "sh"


class ClaimError(Exception):
    """A claim or one of its declared files cannot safely be used."""


def _as_path(value: os.PathLike | str) -> str:
    """Return a text filesystem path, translating bad path inputs to refusal."""
    try:
        path = os.fspath(value)
    except (TypeError, ValueError) as exc:
        raise ClaimError(f"invalid path: {value!r}") from exc
    if not isinstance(path, str):
        raise ClaimError("filesystem paths must be text")
    if "\x00" in path:
        raise ClaimError("path contains a NUL character")
    return path


def _safe(root: os.PathLike | str, name: os.PathLike | str) -> str:
    """Resolve a claim-relative name, refusing absolute paths and escapes.

    Existing symlink components are refused even when their targets happen to
    remain inside the claim.  A not-yet-created final path is allowed, which
    is needed for generated outputs.
    """
    rel = _as_path(name)
    if not rel:
        raise ClaimError("claim path must not be empty")
    if os.path.isabs(rel) or ntpath.isabs(rel) or ntpath.splitdrive(rel)[0]:
        raise ClaimError(f"claim path must be relative: {rel!r}")

    # Treat both common separators as separators for traversal checking.  This
    # also prevents a recipe written on one platform from becoming an escape
    # when read on another.
    components = rel.replace("\\", "/").split("/")
    if any(component == ".." for component in components):
        raise ClaimError(f"claim path escapes its directory: {rel!r}")

    base = os.path.realpath(_as_path(root))
    candidate = os.path.abspath(os.path.join(base, rel))
    try:
        if os.path.commonpath((base, candidate)) != base:
            raise ClaimError(f"claim path escapes its directory: {rel!r}")
    except ValueError as exc:
        raise ClaimError(f"claim path is on a different volume: {rel!r}") from exc

    # Inspect each existing component without following it.  Do not reject a
    # missing output: producers and gates commonly resolve paths before they
    # create them.
    cursor = base
    native_parts = [part for part in rel.split(os.sep) if part not in ("", ".")]
    if os.altsep:
        native_parts = [piece for part in native_parts
                        for piece in part.split(os.altsep)
                        if piece not in ("", ".")]
    for part in native_parts:
        if part == "..":
            # Usually caught above; keep the check adjacent to the walk too.
            raise ClaimError(f"claim path escapes its directory: {rel!r}")
        cursor = os.path.join(cursor, part)
        try:
            info = os.lstat(cursor)
        except FileNotFoundError:
            continue
        except NotADirectoryError as exc:
            raise ClaimError(f"not a directory in claim path: {rel!r}") from exc
        except OSError as exc:
            raise ClaimError(f"cannot inspect claim path {rel!r}: {exc}") from exc
        if stat.S_ISLNK(info.st_mode):
            raise ClaimError(f"symlink in claim path: {rel!r}")

    # Resolve again after the component walk, both as a final containment check
    # and to protect callers if a path changes between the checks above.
    resolved = os.path.realpath(candidate)
    try:
        if os.path.commonpath((base, resolved)) != base:
            raise ClaimError(f"claim path escapes its directory: {rel!r}")
    except ValueError as exc:
        raise ClaimError(f"claim path is on a different volume: {rel!r}") from exc
    return resolved


def _hash_file(path: os.PathLike | str) -> str:
    """Return the lowercase SHA-256 of one ordinary, singly-linked file."""
    filename = _as_path(path)
    try:
        before = os.lstat(filename)
    except OSError as exc:
        raise ClaimError(f"cannot read file {filename!r}: {exc}") from exc
    if stat.S_ISLNK(before.st_mode):
        raise ClaimError(f"refusing symlink: {filename!r}")
    if not stat.S_ISREG(before.st_mode):
        raise ClaimError(f"not a regular file: {filename!r}")
    if before.st_nlink != 1:
        raise ClaimError(f"file must have exactly one hard link: {filename!r}")

    digest = hashlib.sha256()
    try:
        # O_NOFOLLOW closes the small race between lstat and open where the
        # platform provides it.  fstat also verifies the opened object itself.
        flags = os.O_RDONLY
        flags |= getattr(os, "O_BINARY", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(filename, flags)
        with os.fdopen(fd, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
                raise ClaimError(f"not a singly-linked regular file: {filename!r}")
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except ClaimError:
        raise
    except OSError as exc:
        raise ClaimError(f"cannot read file {filename!r}: {exc}") from exc
    return digest.hexdigest()


def _write_json(path: os.PathLike | str, value: object) -> None:
    """Atomically replace *path* with sorted, UTF-8 JSON."""
    filename = _as_path(path)
    try:
        data = (json.dumps(value, sort_keys=True) + "\n").encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ClaimError(f"value is not JSON serializable: {exc}") from exc

    target = os.path.abspath(filename)
    directory = os.path.dirname(target) or os.curdir
    try:
        os.makedirs(directory, exist_ok=True)
        fd, temporary = tempfile.mkstemp(
            prefix="." + os.path.basename(target) + ".", suffix=".tmp",
            dir=directory,
        )
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
            temporary = ""
            # Make the directory entry durable where the platform permits it.
            try:
                dir_fd = os.open(directory, os.O_RDONLY)
            except OSError:
                pass
            else:
                try:
                    os.fsync(dir_fd)
                except OSError:
                    pass
                finally:
                    os.close(dir_fd)
        finally:
            if temporary:
                try:
                    os.unlink(temporary)
                except OSError:
                    pass
    except OSError as exc:
        raise ClaimError(f"cannot write JSON file {target!r}: {exc}") from exc


def _now() -> str:
    """Return the current UTC time in the record-friendly second precision."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _copy_into(source: os.PathLike | str, destination: os.PathLike | str) -> None:
    """Copy a file or directory into a destination, creating parents as needed."""
    src = _as_path(source)
    dst = _as_path(destination)
    if os.path.isdir(src):
        os.makedirs(dst, exist_ok=True)
        shutil.copytree(src, dst, dirs_exist_ok=True, symlinks=True)
    else:
        if os.path.isdir(dst):
            dst = os.path.join(dst, os.path.basename(src))
        parent = os.path.dirname(os.path.abspath(dst))
        os.makedirs(parent, exist_ok=True)
        shutil.copy2(src, dst, follow_symlinks=False)


def _judging_host() -> dict[str, str]:
    """Describe the host strings suitable for a record's environment member."""
    implementation = platform.python_implementation()
    return {
        "platform": sys_platform(),
        "machine": platform.machine() or "unknown",
        "runtime": f"{implementation} {platform.python_version()}",
    }


def sys_platform() -> str:
    """A compact platform identifier, kept separate for a readable record."""
    return platform.system().lower() or "unknown"
