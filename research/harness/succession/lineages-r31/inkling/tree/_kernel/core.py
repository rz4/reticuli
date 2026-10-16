import hashlib
import json
import os
import tempfile
import time

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
_KEEP_ENV = ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "TZ", "RETICULI_JAILED")

GATE_TIMEOUT = 120.0
FURNISH_TIMEOUT = 300.0
PRODUCER_TIMEOUT = 300.0
TOLERANCE = 2.0
MUTANT_CEILING = 1.0
MUTANT_FLOOR = 0.0
MUTANT_HEADROOM = 0.2
COST_KEYS = ("usd", "tokens", "calls", "seconds")
COST_LADDER = ("usd", "tokens", "calls", "seconds")
COST_UNITS = ("usd", "tokens", "calls", "seconds")
GUIDANCE_KEYS = ("guidance", "request")
KINDS = frozenset({"produce", "gate"})
_SHELL = "/bin/sh"

RECORD_NAMESPACE = "reticuli.record"
RECORD_FORMAT = 1

def _hash_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()

def _safe(base, name):
    if not isinstance(name, str):
        raise ClaimError("name must be string")
    if name == "":
        raise ClaimError("empty name refused")
    if name.startswith("/"):
        raise ClaimError("absolute path refused")
    for part in name.replace("\\", "/").split("/"):
        if part == "..":
            raise ClaimError("path escapes claim")
    target = os.path.join(base, name)
    base_abs = os.path.abspath(base)
    target_abs = os.path.abspath(target)
    current = base_abs
    for part in name.replace("\\", "/").split("/"):
        if part == "" or part == ".":
            continue
        current = os.path.join(current, part)
        if os.path.islink(current):
            raise ClaimError("symlink component refused")
    target_real = os.path.realpath(target_abs)
    base_real = os.path.realpath(base_abs)
    if target_real == base_real:
        return target_real
    if target_real.startswith(base_real + os.sep):
        return target_real
    raise ClaimError("path escapes claim")

def _write_json(path, obj):
    dir_path = os.path.dirname(path) if os.path.dirname(path) else "."
    if dir_path and not os.path.exists(dir_path):
        os.makedirs(dir_path, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dir_path, prefix=".tmp_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, sort_keys=True, ensure_ascii=True)
            f.write("\n")
        os.rename(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

def _now():
    return time.time()

def _copy_into(src, dst):
    import shutil
    shutil.copy2(src, dst)

def _judging_host():
    try:
        return os.uname().nodename
    except AttributeError:
        import platform
        return platform.node()
