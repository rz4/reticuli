"""Shared constants and filesystem primitives for the claim kernel.

Declared paths are untrusted.  Resolve them inside the claim before reading
or copying, and hash only ordinary, unaliased files.
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


class ClaimError(Exception):
    """A claim cannot be read or acted on as requested."""


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
_KEEP_ENV = ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "TZ", _JAILED)

GATE_TIMEOUT = 120.0
FURNISH_TIMEOUT = 300.0
PRODUCER_TIMEOUT = 1200.0
TOLERANCE = 2.0
MUTANT_CEILING = 32
MUTANT_FLOOR = 0.0
MUTANT_HEADROOM = 4
COST_KEYS = ("usd", "tokens", "calls", "seconds")
COST_LADDER = COST_KEYS
COST_UNITS = COST_KEYS
GUIDANCE_KEYS = ("guidance", "request")
KINDS = frozenset({"produce", "gate"})
_SHELL = "/bin/sh"


def _safe(directory: str | os.PathLike[str], name: str) -> str:
    """Resolve a recipe path without allowing an alias or claim escape."""
    if not isinstance(name, str) or not name or os.path.isabs(name):
        raise ClaimError(f"unsafe claim path: {name!r}")
    components = name.split("/")
    if any(part in ("", ".", "..") for part in components):
        raise ClaimError(f"unsafe claim path: {name!r}")
    base = os.path.realpath(directory)
    current = base
    for part in components:
        current = os.path.join(current, part)
        if os.path.islink(current):
            raise ClaimError(f"symlink in claim path: {name!r}")
    resolved = os.path.realpath(current)
    if os.path.commonpath((base, resolved)) != base or resolved == base:
        raise ClaimError(f"path escapes claim: {name!r}")
    return resolved


def _hash_file(path: str | os.PathLike[str]) -> str:
    """Return the SHA-256 of a regular file's bytes, without filesystem aliases."""
    try:
        info = os.lstat(path)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ClaimError(f"not an unaliased regular file: {path}")
        digest = hashlib.sha256()
        with open(path, "rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
    except OSError as exc:
        raise ClaimError(f"cannot hash {path}: {exc}") from exc


def _write_json(path: str | os.PathLike[str], value: object) -> None:
    """Atomically write JSON with the identity format's canonical spacing."""
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=parent,
                                         prefix=".tmp-", delete=False) as stream:
            temporary = stream.name
            json.dump(value, stream, sort_keys=True)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None and os.path.exists(temporary):
            os.unlink(temporary)


def _now() -> str:
    """Current UTC time in the record format."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _copy_into(source: str | os.PathLike[str], destination: str | os.PathLike[str]) -> None:
    """Copy an ordinary file into a room, creating its parent directories."""
    _hash_file(source)
    os.makedirs(os.path.dirname(os.path.abspath(destination)), exist_ok=True)
    shutil.copyfile(source, destination)


def _judging_host() -> dict[str, str]:
    """Describe the host executing a gate or producing a record."""
    return {"platform": platform.system().lower(),
            "machine": platform.machine(),
            "runtime": platform.python_implementation() + " " + platform.python_version()}
