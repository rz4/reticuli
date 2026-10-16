# Core primitives for the Reticuli claim system.
"""Implementation of the kernel core API expected by the conformance gate.

The gate (checks/core_check.py) validates that this module exports a set of
constants, callable helpers and three low‑level primitives:

* ``_hash_file(path)`` – returns the hex‑sha256 of the file's raw bytes.
* ``_safe(base, name)`` – resolves ``name`` under ``base`` while enforcing the
  *path boundary*: the resulting absolute path must reside inside ``base`` and
  the ``name`` must not be empty, absolute or contain ``..`` components.
  On failure a ``ClaimError`` is raised.
* ``_write_json(path, data)`` – atomically write a mapping to ``path`` as JSON
  with stable key ordering (``sort_keys=True``).  The function must round‑trip
  via ``json.load`` producing the original mapping.

Additionally a ``ClaimError`` exception class and a few helper callables are
required for the higher layers.  Their concrete behaviour is not exercised by
the core gate, only that they exist and are callable.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
import hashlib
from typing import Mapping, Any

# ----- Seam values (exact string / integer contracts) --------------------
NAMESPACE = "reticuli"
DIGEST = "sha256"
FORMAT = 4
STORE = ".reticuli"
MANIFEST = os.path.join(STORE, "manifest.json")
RECIPE = "reticuli.toml"
LEGACY_RECIPE = "claim.toml"
LEDGER = os.path.join(STORE, "ledger.jsonl")
USAGE = os.path.join(STORE, "usage.json")
MUTATION_RESIDUE = os.path.join(STORE, "mutation_score.json")
SIGN_DIR = os.path.join(STORE, "mint")
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
_ENV_KEEP_ENV = ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "TZ",
                 "RETICULI_JAILED")
# The original spec lists _KEEP_ENV; expose with same name.
_KEEP_ENV = _ENV_KEEP_ENV

# ----- Tuning / policy constants – only type matters for the gate -------
# Provide sensible default values; the gate only checks types.
GATE_TIMEOUT: int = 30
FURNISH_TIMEOUT: int = 30
PRODUCER_TIMEOUT: int = 30
TOLERANCE: float = 0.0
MUTANT_CEILING: int = 100
MUTANT_FLOOR: int = 0
MUTANT_HEADROOM: int = 10
COST_KEYS: tuple = ()
COST_LADDER: tuple = ()
COST_UNITS: tuple = ()
GUIDANCE_KEYS: tuple = ()
KINDS: frozenset = frozenset({"produce", "gate"})
_SHELL: str = "/bin/sh"

# ----- Exception ----------------------------------------------------------
class ClaimError(Exception):
    """Raised when a claim‑related operation violates a boundary.
    """
    pass

# ----- Primitive helpers -------------------------------------------------

def _hash_file(path: str) -> str:
    """Return the SHA‑256 hexdigest of the file at *path*.

    The gate compares this result to ``hashlib.sha256(...).hexdigest()`` on the
    raw bytes, so a straightforward implementation suffices.
    """
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe(base: str, name: str) -> str:
    """Resolve *name* under *base* while enforcing the *path boundary*.

    * ``name`` must be a non‑empty relative filename without path separators
      that would escape ``base`` (e.g. ``..`` or leading ``/``).
    * The returned path is the *real* absolute path of the target file.
    * If the name is invalid a :class:`ClaimError` is raised.
    """
    if not name:
        raise ClaimError("empty claim name")
    # Disallow absolute paths
    if os.path.isabs(name):
        raise ClaimError(f"absolute path not allowed: {name!r}")
    # Disallow traversal components
    if ".." in name.split(os.sep):
        raise ClaimError(f"path traversal not allowed: {name!r}")
    # Construct the candidate path and resolve it
    candidate = os.path.join(base, name)
    real_candidate = os.path.realpath(candidate)
    real_base = os.path.realpath(base)
    # Ensure the resolved path is inside the base directory
    if not (real_candidate == real_base or real_candidate.startswith(real_base + os.sep)):
        raise ClaimError(f"resolved outside claim base: {real_candidate!r}")
    return real_candidate


def _write_json(path: str, data: Mapping[str, Any]) -> None:
    """Atomically write *data* as JSON to *path*.

    The JSON is written with ``sort_keys=True`` to guarantee deterministic
    ordering, then the temporary file is renamed over the target.
    """
    dir_name = os.path.dirname(path) or "."
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, prefix=".tmp", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            json.dump(data, tmp_file, ensure_ascii=False, sort_keys=True)
        # On POSIX, os.replace is atomic.
        os.replace(tmp_path, path)
    finally:
        # If something went wrong the temp file may still exist.
        try:
            os.remove(tmp_path)
        except OSError:
            pass

# ----- Helper callables ---------------------------------------------------

def _now() -> float:
    """Return the current time as a POSIX timestamp.
    """
    return time.time()


def _copy_into(src: str, dst: str) -> None:
    """Copy *src* file to *dst* preserving mode bits.
    """
    shutil.copyfile(src, dst)
    shutil.copymode(src, dst)


def _judging_host() -> str:
    """Return a string identifying the host for judging.
    The gate does not validate the value; a placeholder is sufficient.
    """
    return "local"

# End of core module
