import hashlib
import json
import os
import shutil
import time
import tempfile
import platform

class ClaimError(Exception):
    pass

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
_KEEP_ENV = ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "TZ",
              "RETICULI_JAILED")

GATE_TIMEOUT = 30.0
FURNISH_TIMEOUT = 30.0
PRODUCER_TIMEOUT = 30.0
TOLERANCE = 1e-6
MUTANT_CEILING = 1.0
MUTANT_FLOOR = 0.0
MUTANT_HEADROOM = 0.1
COST_KEYS = ("cpu", "mem", "disk")
COST_LADDER = (1, 10, 100)
COST_UNITS = ("ms", "mb", "kb")
GUIDANCE_KEYS = ("priority", "weight")
KINDS = frozenset({"produce", "gate"})
_SHELL = "/bin/sh"

def _now() -> float:
    return time.time()

def _copy_into(src: str, dst: str) -> None:
    shutil.copy2(src, dst)

def _judging_host() -> str:
    return platform.node()

def _hash_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

def _safe(root: str, path: str) -> str:
    if not path:
        raise ClaimError("Empty path")
    
    root_abs = os.path.realpath(root)
    target = os.path.realpath(os.path.join(root_abs, path))
    
    prefix = root_abs if root_abs.endswith(os.sep) else root_abs + os.sep
    if not target.startswith(prefix):
        raise ClaimError(f"Path {path} escapes claim root")
        
    return target

def _write_json(path: str, data: dict) -> None:
    dir_name = os.path.dirname(path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
    
    fd, temp_path = tempfile.mkstemp(dir=dir_name, prefix=".tmp-json-")
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, sort_keys=True)
        os.replace(temp_path, path)
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise
