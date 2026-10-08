"""Core primitives: the two boundaries beneath everything.

The path boundary (`_safe`) refuses a recipe-declared name that escapes the
claim directory. The bytes boundary (`_hash_file`) is a plain sha256 of a
file's bytes. Everything else here is the shared vocabulary -- protocol
constants, the refusal type, and small host/IO helpers -- that every layer
above imports rather than redefines. Stdlib only, never the network.
"""
import hashlib
import json
import os
import platform
import shutil
import sys
import tempfile
import time

# -- the shared protocol -----------------------------------------------

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

# -- tuning constants ----------------------------------------------------

GATE_TIMEOUT = 120.0
FURNISH_TIMEOUT = 300.0
PRODUCER_TIMEOUT = 600.0
TOLERANCE = 2.0

MUTANT_FLOOR = 0.6
MUTANT_CEILING = 50
MUTANT_HEADROOM = 0.1

COST_KEYS = ("usd", "tokens", "calls", "seconds")
COST_LADDER = ("usd", "tokens", "calls", "seconds")
COST_UNITS = ("usd", "tokens", "calls", "seconds")

GUIDANCE_KEYS = ("guidance", "request")

KINDS = frozenset({"produce", "gate"})

_SHELL = "/bin/sh"


class ClaimError(Exception):
    """A refusal with a reason -- the only error this package raises."""


# -- the bytes boundary ----------------------------------------------------

def _hash_file(path: str) -> str:
    """A plain sha256 of a file's bytes."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# -- the path boundary -------------------------------------------------

def _safe(base: str, name: str) -> str:
    """Resolve `name` inside `base`; refuse anything that escapes the claim."""
    if not name or os.path.isabs(name):
        raise ClaimError(f"refused path: {name!r}")
    norm = os.path.normpath(name)
    if norm in (os.curdir, os.pardir):
        raise ClaimError(f"refused path: {name!r}")
    parts = norm.split(os.sep)
    if any(part == os.pardir or part == "" for part in parts):
        raise ClaimError(f"refused path: {name!r} escapes the claim")

    base_real = os.path.realpath(base)
    cur = base_real
    for part in parts:
        if os.path.islink(cur):
            raise ClaimError(f"refused path: {name!r} crosses a symlink")
        cur = os.path.join(cur, part)
    if os.path.islink(cur):
        raise ClaimError(f"refused path: {name!r} crosses a symlink")

    resolved = os.path.join(base_real, norm)
    if resolved != base_real and not resolved.startswith(base_real + os.sep):
        raise ClaimError(f"refused path: {name!r} escapes the claim")
    return resolved


# -- atomic JSON write -------------------------------------------------

def _write_json(path: str, obj) -> None:
    """Write `obj` to `path` as JSON, atomically (write-then-rename)."""
    directory = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# -- small host/IO helpers shared by the layers above ---------------------

def _now() -> str:
    """UTC time of recording, `YYYY-MM-DDTHH:MM:SSZ` (spec/record.md)."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _copy_into(src: str, dst: str, names) -> None:
    """Copy each named file from `src` into `dst`, creating directories."""
    for name in names:
        source = _safe(src, name)
        target = _safe(dst, name)
        os.makedirs(os.path.dirname(target) or dst, exist_ok=True)
        shutil.copy2(source, target)


def _judging_host() -> dict:
    """Describe the host a gate runs on (spec/record.md: `environment`)."""
    return {
        "platform": sys.platform,
        "machine": platform.machine(),
        "runtime": f"{platform.python_implementation()} {platform.python_version()}",
    }
