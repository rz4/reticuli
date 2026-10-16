
import datetime
import hashlib
import json
import os
import platform
import shutil
import sys
import tempfile

class ClaimError(Exception):
    """A problem with the claim's format or content."""
    pass

# Protocol constants
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

# Tuning constants
GATE_TIMEOUT = 300
FURNISH_TIMEOUT = 300
PRODUCER_TIMEOUT = 300
TOLERANCE = 0.0
MUTANT_CEILING = 1.0
MUTANT_FLOOR = 0.0
MUTANT_HEADROOM = 0.0
COST_KEYS = ("producer", "developer")
COST_LADDER = tuple()
COST_UNITS = tuple()
GUIDANCE_KEYS = tuple()
KINDS = frozenset({"produce", "gate"})
_SHELL = "/bin/bash"

def _now():
    return datetime.datetime.utcnow().isoformat() + "Z"

def _copy_into(src, dst):
    shutil.copy(src, dst)

def _judging_host():
    return platform.node()

def _hash_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(128 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def _safe(claim_path, sub_path):
    if not sub_path:
        raise ClaimError("empty path is not allowed")

    if os.path.isabs(sub_path) or ".." in sub_path.split(os.path.sep):
        raise ClaimError(f"unsafe path: {sub_path!r}")

    real_claim_path = os.path.realpath(claim_path)
    candidate_path = os.path.realpath(os.path.join(real_claim_path, sub_path))

    if os.path.commonpath([real_claim_path, candidate_path]) != real_claim_path:
        raise ClaimError(f"path travels outside of claim: {sub_path!r}")
    
    return candidate_path

def _write_json(path, data):
    fd, name = tempfile.mkstemp(dir=os.path.dirname(path))
    with os.fdopen(fd, "w") as f:
        json.dump(data, f)
    os.rename(name, path)
