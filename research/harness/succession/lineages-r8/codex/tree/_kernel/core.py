"""Shared kernel constants and the filesystem boundary for a claim."""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import platform
import shutil
import stat
import sys
import tempfile


class ClaimError(Exception):
    """A claim is invalid or cannot safely be read."""


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
PRODUCER_TIMEOUT = 3600.0
TOLERANCE = 2.0
MUTANT_CEILING = 100
MUTANT_FLOOR = 1
MUTANT_HEADROOM = 10
COST_KEYS = ("usd", "tokens", "calls", "seconds")
COST_LADDER = COST_KEYS
COST_UNITS = COST_KEYS
GUIDANCE_KEYS = ("guidance", "request")
KINDS = frozenset({"produce", "gate"})
_SHELL = "/bin/sh"


def _now() -> str:
    """Current UTC time in the record's timestamp form."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe(directory: str | os.PathLike[str], name: str) -> str:
    """Resolve a declared name, refusing aliases and paths outside the claim."""
    if not isinstance(name, str) or not name or os.path.isabs(name):
        raise ClaimError(f"unsafe claim path: {name!r}")
    components = name.split("/")
    if any(part in ("", ".", "..") for part in components):
        raise ClaimError(f"unsafe claim path: {name!r}")

    base = os.path.realpath(directory)
    candidate = os.path.join(base, *components)
    cursor = base
    for part in components:
        cursor = os.path.join(cursor, part)
        if os.path.islink(cursor):
            raise ClaimError(f"symlink in claim path: {name!r}")
    resolved = os.path.realpath(candidate)
    if os.path.commonpath((base, resolved)) != base or resolved == base:
        raise ClaimError(f"claim path escapes directory: {name!r}")
    return resolved


def _hash_file(path: str | os.PathLike[str]) -> str:
    """Hash one ordinary, uniquely linked file's bytes with SHA-256."""
    try:
        info = os.lstat(path)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ClaimError(f"not a regular, uniquely linked file: {path}")
        digest = hashlib.sha256()
        with open(path, "rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError as exc:
        raise ClaimError(f"cannot hash {path}: {exc}") from exc


def _write_json(path: str | os.PathLike[str], value: object) -> None:
    """Replace a JSON document atomically in the destination directory."""
    destination = os.fspath(path)
    parent = os.path.dirname(os.path.abspath(destination))
    os.makedirs(parent, exist_ok=True)
    encoded = (json.dumps(value, sort_keys=True) + "\n").encode("utf-8")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=parent, prefix=".reticuli-", delete=False) as stream:
            temporary = stream.name
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary is not None and os.path.exists(temporary):
            os.unlink(temporary)


def _copy_into(source: str | os.PathLike[str], destination: str | os.PathLike[str]) -> None:
    """Copy an ordinary file, creating its destination directory if needed."""
    _hash_file(source)
    os.makedirs(os.path.dirname(os.path.abspath(destination)), exist_ok=True)
    shutil.copyfile(source, destination)


def _judging_host() -> dict[str, str]:
    """Describe the interpreter and machine used to judge a claim."""
    return {
        "platform": sys.platform,
        "machine": platform.machine(),
        "runtime": platform.python_implementation() + " " + platform.python_version(),
    }
