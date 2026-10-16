import hashlib
import json
import os
import platform
import shutil
import tempfile
import time

class ClaimError(Exception):
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

# Tuning
KINDS = frozenset({"produce", "gate"})
GATE_TIMEOUT = 120.0
FURNISH_TIMEOUT = 300.0
PRODUCER_TIMEOUT = 600.0
TOLERANCE = 2.0
MUTANT_CEILING = 1.0
MUTANT_FLOOR = 0.6
MUTANT_HEADROOM = 0.1
COST_KEYS = ("usd", "tokens", "calls", "seconds")
COST_LADDER = ("usd", "tokens", "calls", "seconds")
COST_UNITS = ("usd", "tokens", "calls", "seconds")
GUIDANCE_KEYS = ("request", "guidance")
_SHELL = shutil.which("sh") or "/bin/sh"

def _now() -> float:
    return time.time()

def _judging_host() -> str:
    return platform.node()

def _copy_into(src: str, dst: str) -> None:
    shutil.copytree(src, dst)

def _hash_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()

def _safe(root: str, name: str) -> str:
    if not name:
        raise ClaimError("empty name")
    if os.path.isabs(name) or ".." in name:
        raise ClaimError(f"refused path escape: {name!r}")
    path = os.path.join(root, name)
    path = os.path.normpath(path)
    real_root = os.path.realpath(root) + os.sep
    real_path = os.path.realpath(path)
    if not real_path.startswith(real_root):
        raise ClaimError(f"path escapes claim: {name}")
    if os.path.basename(real_path) != os.path.basename(name):
        raise ClaimError(f"basename changed: {name}")
    return real_path

def _write_json(path: str, data: object) -> None:
    dir_path = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=dir_path, suffix=".json.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, sort_keys=True)
        os.rename(tmp, path)
    except:
        os.unlink(tmp)
        raise