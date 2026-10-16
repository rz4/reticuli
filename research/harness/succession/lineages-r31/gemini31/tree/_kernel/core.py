import hashlib
import json
import os
import shutil

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

GATE_TIMEOUT = 1
FURNISH_TIMEOUT = 1
PRODUCER_TIMEOUT = 1
TOLERANCE = 1
MUTANT_CEILING = 1
MUTANT_FLOOR = 1
MUTANT_HEADROOM = 1
COST_KEYS = ()
COST_LADDER = ()
COST_UNITS = ()
GUIDANCE_KEYS = ()
KINDS = frozenset({"produce", "gate"})
_SHELL = ""

class ClaimError(Exception):
    pass

def _hash_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def _safe(base: str, path: str) -> str:
    if not path:
        raise ClaimError("empty path")
    resolved = os.path.realpath(os.path.join(base, path))
    base_real = os.path.realpath(base) + os.sep
    if not resolved.startswith(base_real):
        raise ClaimError("escape")
    return resolved

def _write_json(path: str, data: dict) -> None:
    import tempfile
    d = os.path.dirname(path)
    if not d:
        d = "."
    fd, tmp = tempfile.mkstemp(dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, path)
    except Exception:
        os.unlink(tmp)
        raise

def _now():
    pass

def _copy_into(src, dst):
    pass

def _judging_host():
    pass
