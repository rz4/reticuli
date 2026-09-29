"""reticuli._kernel.core -- the innermost layer.

Two boundaries and the primitives everything else is built on:

  * the bytes boundary -- `_hash_file` is a plain sha256 of a file's bytes.
  * the path boundary -- `_safe` resolves a name to a real path inside a
    claim directory, and refuses (via `ClaimError`) any name that would
    escape it: absolute paths, empty names, or `..` traversal.

Also here: an atomic JSON writer (`_write_json`), the refusal vocabulary
(`ClaimError`), and the protocol constants shared verbatim across every
layer above this one (store/recipe/ledger paths, env var names, digest
and format identifiers). Stdlib only. Never the network.
"""
import hashlib
import json
import os
import platform
import shutil
import sys
import tempfile
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Protocol constants: the on-disk / environment contract. Shared verbatim
# across layers and with the record format -- changing a value here changes
# what reticuli is.
# ---------------------------------------------------------------------------
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

_KEEP_ENV = ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "TZ", "RETICULI_JAILED")

# ---------------------------------------------------------------------------
# Tuning constants and host-derived values. Exact values are policy for the
# layers that exercise them; the seam only pins name and kind.
# ---------------------------------------------------------------------------
GATE_TIMEOUT = float(os.environ.get(_ENV_TIMEOUT, 300))
FURNISH_TIMEOUT = 600.0
PRODUCER_TIMEOUT = 1800.0
TOLERANCE = float(os.environ.get(_ENV_TOLERANCE, 0.0))
MUTANT_CEILING = 1.0
MUTANT_FLOOR = 0.0
MUTANT_HEADROOM = 0.1

COST_KEYS = ("input_tokens", "output_tokens", "requests")
COST_LADDER = ("free", "cheap", "standard", "premium")
COST_UNITS = ("tokens", "requests", "seconds")
GUIDANCE_KEYS = ("goal", "constraints", "hints")
KINDS = frozenset({"produce", "gate", "sign", "vendor"})

_SHELL = os.environ.get("SHELL", "/bin/sh")


# ---------------------------------------------------------------------------
# Refusal vocabulary
# ---------------------------------------------------------------------------
class ClaimError(Exception):
    """A claim-level refusal: bad bytes, an escaping path, a broken record."""


# ---------------------------------------------------------------------------
# The bytes boundary
# ---------------------------------------------------------------------------
def _hash_file(path: str) -> str:
    """Plain sha256 of a file's bytes, as a hex digest."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# The path boundary
# ---------------------------------------------------------------------------
def _safe(base: str, name: str) -> str:
    """Resolve `name` to a real path inside `base`; refuse an escape."""
    if not name:
        raise ClaimError("empty name")
    if os.path.isabs(name):
        raise ClaimError(f"absolute path refused: {name!r}")
    base_real = os.path.realpath(base)
    candidate = os.path.realpath(os.path.join(base_real, name))
    if candidate != base_real and not candidate.startswith(base_real + os.sep):
        raise ClaimError(f"path escapes the claim: {name!r}")
    return candidate


# ---------------------------------------------------------------------------
# Atomic JSON write
# ---------------------------------------------------------------------------
def _write_json(path: str, obj) -> None:
    """Write `obj` as JSON to `path` atomically (write-tmp, then replace)."""
    directory = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Small helpers the kernel layers above import from core
# ---------------------------------------------------------------------------
def _now() -> str:
    """Current UTC time as an ISO-8601 string, ledger-ready."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _copy_into(base: str, name: str, src: str) -> str:
    """Copy the file at `src` into the claim at `name`; return the real path."""
    dest = _safe(base, name)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copyfile(src, dest)
    return dest


def _judging_host() -> dict:
    """A small, stable description of the host running the gate."""
    return {
        "implementation": platform.python_implementation(),
        "machine": platform.machine(),
        "platform": sys.platform,
        "python": platform.python_version(),
    }
