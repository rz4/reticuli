"""Kernel core - public surface for the layers above it."""

import hashlib
import json
import os
import tempfile
import time
from typing import Any, Dict, FrozenSet, Tuple, Union


class ClaimError(Exception):
    """A refusal with a reason — the only kernel error."""
    pass


# Protocol constants whose VALUE is the on-disk / environment contract
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
_KEEP_ENV = ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "TZ", "RETICULI_JAILED")


# Tuning constants and host-derived values
GATE_TIMEOUT = 30.0
FURNISH_TIMEOUT = 30.0
PRODUCER_TIMEOUT = 30.0
TOLERANCE = 2.0
MUTANT_CEILING = 1000.0
MUTANT_FLOOR = 0.0
MUTANT_HEADROOM = 0.1
COST_KEYS = ("usd", "tokens", "calls", "seconds")
COST_LADDER = ("usd", "tokens", "calls", "seconds")
COST_UNITS = ("usd", "tokens", "calls", "seconds")
GUIDANCE_KEYS = ("guidance", "request")
KINDS = frozenset({"produce", "gate"})
_SHELL = "/bin/sh"


def _now() -> float:
    """Return current time as a float."""
    return time.time()


def _copy_into(src: str, dst: str) -> None:
    """Copy file src to dst, creating directories as needed."""
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(src, "rb") as fsrc:
        with open(dst, "wb") as fdst:
            fdst.write(fsrc.read())


def _judging_host() -> Dict[str, str]:
    """Return information about the judging host."""
    return {
        "platform": os.name,
        "machine": os.uname().machine if hasattr(os, 'uname') else "unknown",
        "runtime": f"Python {os.sys.version.split()[0]}"
    }


def _hash_file(path: str) -> str:
    """Return the SHA-256 hex digest of a file's contents."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe(base: str, name: str) -> str:
    """Resolve a name inside the base directory, refusing escapes."""
    if not name or name.startswith("/") or ".." in name.split("/"):
        raise ClaimError(f"unsafe name: {name!r}")
    base = os.path.realpath(base)
    target = os.path.realpath(os.path.join(base, name))
    if not target.startswith(base + os.sep):
        raise ClaimError(f"unsafe name: {name!r}")
    return target


def _write_json(path: str, data: Any) -> None:
    """Atomically write JSON data to a path."""
    dir_name = os.path.dirname(path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
    
    # Write to temporary file first
    handle, temp_path = tempfile.mkstemp(dir=dir_name, prefix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as f:
            json.dump(data, f, sort_keys=True, separators=(", ", ": "))
        os.replace(temp_path, path)
    except Exception:
        os.unlink(temp_path)
        raise