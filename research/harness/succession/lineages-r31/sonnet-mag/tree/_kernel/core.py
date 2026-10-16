"""Kernel core: path boundary, bytes boundary, atomic JSON, refusals, constants."""
import hashlib
import json
import os
import platform
import shutil
import stat
import sys
import tempfile
import time

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
_KEEP_ENV = ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "TZ",
             "RETICULI_JAILED")

GATE_TIMEOUT = 600
FURNISH_TIMEOUT = 600
PRODUCER_TIMEOUT = 1800
TOLERANCE = 2.0
MUTANT_CEILING = 64
MUTANT_FLOOR = 8
MUTANT_HEADROOM = 4
COST_KEYS = ("usd", "tokens", "calls", "seconds")
COST_LADDER = ("usd", "tokens", "calls", "seconds")
COST_UNITS = ("usd", "tokens", "calls", "seconds")
GUIDANCE_KEYS = ("guidance", "request")
KINDS = frozenset({"produce", "gate"})
_SHELL = "/bin/sh"


class ClaimError(Exception):
    """A refusal with a reason — the only kernel error."""


def _now() -> float:
    return time.time()


def _judging_host() -> dict:
    return {"interpreter": platform.python_version(),
            "platform": sys.platform,
            "sandbox": bool(os.environ.get(_JAILED))}


def _safe(d: str, name: str) -> str:
    """Resolve `name` inside claim dir `d`, refusing any escape or symlink."""
    if not isinstance(name, str) or not name:
        raise ClaimError(f"empty path name: {name!r}")
    if "\x00" in name:
        raise ClaimError(f"bad path name: {name!r}")
    if os.path.isabs(name) or name.startswith(("/", "\\")):
        raise ClaimError(f"absolute path refused: {name!r}")
    parts = name.replace("\\", "/").split("/")
    if any(p == ".." for p in parts):
        raise ClaimError(f"path escapes the claim: {name!r}")
    root = os.path.realpath(d)
    cur = root
    for p in parts:
        if p in ("", "."):
            continue
        cur = os.path.join(cur, p)
        if os.path.islink(cur):
            raise ClaimError(f"symlink component refused: {name!r}")
    full = os.path.realpath(os.path.join(root, *[p for p in parts
                                                 if p not in ("", ".")]))
    if full == root or not full.startswith(root + os.sep):
        raise ClaimError(f"path escapes the claim: {name!r}")
    return full


def _hash_file(path: str) -> str:
    """Plain sha256 of a regular, singly-linked file's bytes."""
    try:
        st = os.lstat(path)
    except OSError as e:
        raise ClaimError(f"cannot read {path!r}: {e}")
    if not stat.S_ISREG(st.st_mode):
        raise ClaimError(f"not a regular file: {path!r}")
    if st.st_nlink != 1:
        raise ClaimError(f"hardlinked file refused: {path!r}")
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_json(path: str, obj) -> None:
    """Atomic JSON write: temp file in the same directory, then rename."""
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, sort_keys=True, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _copy_into(src: str, dst: str) -> None:
    """Copy a file to dst, creating parent directories."""
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    shutil.copyfile(src, dst)
