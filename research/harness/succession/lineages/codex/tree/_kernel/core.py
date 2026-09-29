"""Core constants and filesystem primitives for a Reticuli claim."""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import shutil
import tempfile


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

GATE_TIMEOUT = 60
FURNISH_TIMEOUT = 60
PRODUCER_TIMEOUT = 60
TOLERANCE = 0.0
MUTANT_CEILING = 1.0
MUTANT_FLOOR = 0.0
MUTANT_HEADROOM = 0.0
COST_KEYS = ()
COST_LADDER = ()
COST_UNITS = ()
GUIDANCE_KEYS = ()
KINDS = frozenset()
_SHELL = os.environ.get("SHELL", "/bin/sh")


class ClaimError(Exception):
    """A claim cannot be read or validated as requested."""


def _safe(root: str, name: str) -> str:
    """Resolve a relative claim path, refusing paths outside the claim."""
    if not isinstance(name, str) or not name or os.path.isabs(name):
        raise ClaimError(f"unsafe claim path: {name!r}")
    base = os.path.realpath(root)
    resolved = os.path.realpath(os.path.join(base, name))
    if resolved == base or os.path.commonpath((base, resolved)) != base:
        raise ClaimError(f"unsafe claim path: {name!r}")
    return resolved


def _hash_file(path: str) -> str:
    """Return the SHA-256 digest of a file's exact bytes."""
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: str, value: object) -> None:
    """Write JSON through a temporary file in the destination directory."""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".tmp-", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(value, output, sort_keys=True, ensure_ascii=False)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _now() -> str:
    """Return the current UTC time in ISO 8601 form."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _copy_into(source: str, destination: str) -> None:
    """Copy a file into a destination path, creating its parent directory."""
    os.makedirs(os.path.dirname(os.path.abspath(destination)), exist_ok=True)
    shutil.copy2(source, destination)


def _judging_host() -> str:
    """Return a stable local host label."""
    return os.uname().nodename if hasattr(os, "uname") else os.environ.get("COMPUTERNAME", "unknown")
