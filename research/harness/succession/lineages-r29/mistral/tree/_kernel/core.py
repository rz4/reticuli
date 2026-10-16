"""The innermost kernel: primitives for identity and verification.

- The path boundary: refuse names that escape the claim.
- The bytes boundary: plain SHA-256 of file bytes.
- Atomic JSON write.
- The refusal vocabulary.

Stdlib only, never the network.
"""
import hashlib
import json
import os
import sys
import time
from typing import Any, Dict, List, Set, Tuple, Union


class ClaimError(Exception):
    """A refusal with a reason: the only error the kernel raises."""


# Protocol constants (on-disk and environment contract)
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
_KEEP_ENV = ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "TZ", "RETICULI_JAILED")

# Tuning and host-derived constants
GATE_TIMEOUT: float = 300.0
FURNISH_TIMEOUT: float = 600.0
PRODUCER_TIMEOUT: float = 3600.0
TOLERANCE: float = 0.05
MUTANT_CEILING: float = 1.0
MUTANT_FLOOR: float = 0.0
MUTANT_HEADROOM: float = 0.1
COST_KEYS: Tuple[str, ...] = ("usd", "tokens", "calls", "seconds")
COST_LADDER: Tuple[Tuple[str, str], ...] = (
    ("usd", "usd"),
    ("usd", "tokens"),
    ("usd", "calls"),
    ("usd", "seconds"),
)
COST_UNITS: Tuple[str, ...] = ("usd", "tokens", "calls", "seconds")
GUIDANCE_KEYS: Tuple[str, ...] = ("guidance", "request")
KINDS: frozenset = frozenset({"produce", "gate"})
_SHELL: str = "/bin/sh"


def _now() -> str:
    """Current UTC time in canonical format."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _hash_file(path: str) -> str:
    """SHA-256 digest of the file's bytes.

    Raises ClaimError if the path is not a regular file with st_nlink == 1.
    """
    try:
        st = os.stat(path)
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
            raise ClaimError(f"{path!r} must be a regular file with a single link")
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError as e:
        raise ClaimError(f"could not read {path!r}: {e}")


def _safe(claim_dir: str, name: str) -> str:
    """Resolve a name inside the claim directory.

    Raises ClaimError if the name escapes, is absolute, or is empty.
    """
    if not name or name.startswith("/") or name.startswith("../") or "/../" in name:
        raise ClaimError(f"{name!r} is not a valid claim-local name")
    
    # Resolve the claim directory to its realpath, ensuring no symlink escapes
    real_claim = os.path.realpath(claim_dir)
    if not os.path.isdir(real_claim):
        raise ClaimError(f"claim directory {real_claim!r} does not exist")
    
    # Join and resolve the path
    joined = os.path.join(real_claim, name)
    try:
        resolved = os.path.realpath(joined)
    except OSError:
        raise ClaimError(f"{name!r} does not resolve under the claim")
    
    # Ensure resolved is under the real claim directory
    if not resolved.startswith(real_claim + os.sep):
        raise ClaimError(f"{name!r} escapes the claim")
    
    # Reject any symlink component
    parts = os.path.relpath(resolved, real_claim).split(os.sep)
    for i in range(1, len(parts) + 1):
        partial = os.path.join(real_claim, *parts[:i])
        if os.path.islink(partial):
            raise ClaimError(f"{name!r} contains a symlink component: {partial!r}")
    
    return resolved


def _write_json(path: str, obj: Any) -> None:
    """Write `obj` to `path` as canonical JSON."""
    serialized = json.dumps(obj, sort_keys=True, ensure_ascii=True, separators=(", ", ": "))
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(serialized)
    except OSError as e:
        raise ClaimError(f"could not write JSON to {path!r}: {e}")


def _copy_into(src: str, dst_dir: str) -> None:
    """Copy a file into a directory, preserving its basename."""
    basename = os.path.basename(src)
    dst = os.path.join(dst_dir, basename)
    try:
        with open(src, "rb") as fsrc:
            with open(dst, "wb") as fdst:
                fdst.write(fsrc.read())
    except OSError as e:
        raise ClaimError(f"could not copy {src!r} into {dst_dir!r}: {e}")


def _judging_host() -> Dict[str, str]:
    """Return the host environment (platform, machine, runtime)."""
    return {
        "platform": sys.platform,
        "machine": os.uname().machine,
        "runtime": f"{sys.implementation.name} {sys.version.split()[0]}",
    }


# Import stat for _hash_file
import stat