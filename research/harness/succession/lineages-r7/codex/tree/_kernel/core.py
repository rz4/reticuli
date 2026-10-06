"""Core constants and filesystem boundaries for content-addressed claims."""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import platform
import shutil
import stat
import tempfile


class ClaimError(Exception):
    """A claim is malformed or crosses a declared boundary."""


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
_KEEP_ENV = ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "TZ",
             "RETICULI_JAILED")

GATE_TIMEOUT = 120.0
FURNISH_TIMEOUT = 300.0
PRODUCER_TIMEOUT = 3600.0
TOLERANCE = 2.0
MUTANT_CEILING = 100
MUTANT_FLOOR = 0.0
MUTANT_HEADROOM = 0.0
COST_KEYS = ("usd", "tokens", "calls", "seconds")
COST_LADDER = COST_KEYS
COST_UNITS = COST_KEYS
GUIDANCE_KEYS = ("guidance", "request")
KINDS = frozenset({"produce", "gate"})
_SHELL = "/bin/sh"


def _now() -> str:
    """Return a UTC timestamp suitable for a record."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe(directory: str | os.PathLike[str], name: str) -> str:
    """Resolve a declared relative path within a claim, without aliases."""
    if not isinstance(name, str) or not name or os.path.isabs(name):
        raise ClaimError(f"unsafe claim path: {name!r}")
    pieces = name.split(os.sep)
    if any(piece in ("", ".", "..") for piece in pieces):
        raise ClaimError(f"unsafe claim path: {name!r}")
    base = os.path.realpath(directory)
    path = base
    for piece in pieces:
        path = os.path.join(path, piece)
        if os.path.islink(path):
            raise ClaimError(f"symlink in claim path: {name!r}")
    resolved = os.path.realpath(path)
    if not resolved.startswith(base + os.sep):
        raise ClaimError(f"claim path escapes directory: {name!r}")
    return resolved


def _hash_file(path: str | os.PathLike[str]) -> str:
    """Hash bytes of one ordinary, unaliased file."""
    try:
        info = os.lstat(path)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ClaimError(f"not a regular single-link file: {path}")
        digest = hashlib.sha256()
        with open(path, "rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
    except OSError as error:
        raise ClaimError(f"cannot hash {path}: {error}") from error


def _write_json(path: str | os.PathLike[str], value: object) -> None:
    """Replace a JSON file atomically using a temporary peer file."""
    path = os.fspath(path)
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=parent,
                                         prefix=".tmp-", delete=False) as target:
            temporary = target.name
            json.dump(value, target, sort_keys=True)
            target.write("\n")
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and os.path.exists(temporary):
            os.unlink(temporary)


def _copy_into(source: str | os.PathLike[str], destination: str | os.PathLike[str]) -> str:
    """Copy one file to a destination path, creating its parent directory."""
    destination = os.fspath(destination)
    os.makedirs(os.path.dirname(os.path.abspath(destination)), exist_ok=True)
    return shutil.copy2(source, destination)


def _judging_host() -> dict[str, str]:
    """Describe the host used to judge a claim."""
    return {"platform": platform.system().lower(),
            "machine": platform.machine(),
            "runtime": platform.python_implementation() + " " + platform.python_version()}
