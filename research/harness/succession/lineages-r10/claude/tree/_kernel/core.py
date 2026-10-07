"""Kernel core: the two boundaries and the primitives beneath everything.

The path boundary (`_safe`) refuses any recipe-declared name that would
escape the claim directory. The bytes boundary (`_hash_file`) is a plain
sha256 of a file's bytes, refusing anything that is not a plain, singly
linked regular file. `_write_json` writes a document atomically. Everything
else here is the protocol vocabulary — constants and small helpers — that
the layers above import rather than redefine.

Stdlib only, never the network.
"""
import datetime
import hashlib
import json
import os
import platform
import shutil
import stat
import sys
import tempfile
from pathlib import PurePosixPath

# -- protocol constants: the on-disk / environment contract, shared verbatim
#    with the record format and every layer built on this kernel. -----------
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

# -- tuning constants and host-derived vocabulary: the name and kind are the
#    seam, the exact value is policy left to the layers that exercise it. ---
GATE_TIMEOUT = 120.0
FURNISH_TIMEOUT = 300.0
PRODUCER_TIMEOUT = 600.0
TOLERANCE = 2.0
MUTANT_CEILING = 50
MUTANT_FLOOR = 5
MUTANT_HEADROOM = 1.2

# usd > tokens > calls > seconds: the cost ladder's strongest-first order.
COST_KEYS = ("usd", "tokens", "calls", "seconds")
COST_LADDER = ("usd", "tokens", "calls", "seconds")
COST_UNITS = ("usd", "tokens", "calls", "seconds")
# a produce step's hint for a rebuilder; both spellings are read.
GUIDANCE_KEYS = ("guidance", "request")
# the step-kind vocabulary the claim format defines.
KINDS = frozenset({"produce", "gate"})
_SHELL = "/bin/sh"


class ClaimError(Exception):
    """A refusal with a reason -- the only kernel error."""


def _now() -> str:
    """UTC time of recording, `YYYY-MM-DDTHH:MM:SSZ`."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _judging_host() -> dict:
    """Describe the host a gate judges on: platform, machine, interpreter,
    and which sandbox backend (if any) is functionally available."""
    if os.environ.get(_JAILED):
        quarantine = "inherited"
    elif sys.platform == "darwin" and shutil.which("sandbox-exec"):
        quarantine = "seatbelt"
    elif sys.platform.startswith("linux") and shutil.which("bwrap"):
        quarantine = "bubblewrap"
    else:
        quarantine = "none"
    return {
        "platform": sys.platform,
        "machine": platform.machine(),
        "implementation": platform.python_implementation(),
        "python": platform.python_version(),
        "quarantine": quarantine,
    }


def _safe(base: str, name: str) -> str:
    """Resolve a recipe-declared name under `base`, refusing any escape.

    Refused: an empty or absolute name, any `..` component, and any
    component that is a symlink -- even one whose target stays inside the
    claim (spec/identity.md's file hashing rules).
    """
    if not isinstance(name, str) or not name:
        raise ClaimError("path boundary: refusing an empty path")
    if os.path.isabs(name):
        raise ClaimError(f"path boundary: refusing an absolute path {name!r}")
    parts = PurePosixPath(name).parts
    if not parts or any(p in ("..", ".") for p in parts):
        raise ClaimError(f"path boundary: refusing {name!r}")
    base_real = os.path.realpath(base)
    cur = base_real
    for part in parts:
        cur = os.path.join(cur, part)
        if os.path.islink(cur):
            raise ClaimError(f"path boundary: refusing a symlink component in {name!r}")
    if cur != base_real and not cur.startswith(base_real + os.sep):
        raise ClaimError(f"path boundary: {name!r} escapes the claim")
    return cur


def _hash_file(path: str) -> str:
    """A plain sha256 of a file's bytes; refuses anything but a regular,
    singly linked file (closes the filesystem-aliasing surface)."""
    st = os.stat(path, follow_symlinks=False)
    if not stat.S_ISREG(st.st_mode):
        raise ClaimError(f"the bytes boundary refuses a non-regular file: {path!r}")
    if st.st_nlink != 1:
        raise ClaimError(f"the bytes boundary refuses a hard-linked file: {path!r}")
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_json(path: str, obj) -> None:
    """Write JSON atomically: build the bytes off to the side, then rename
    into place, so a reader never observes a partially written document."""
    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, sort_keys=True, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _copy_into(src: str, dst: str, names=None) -> str:
    """Copy named entries from the claim at `src` into the room at `dst`,
    resolving every name through the path boundary on both sides. With
    `names` omitted, copies every top-level entry of `src`."""
    os.makedirs(dst, exist_ok=True)
    src_real = os.path.realpath(src)
    if names is None:
        names = sorted(os.listdir(src_real))
    for name in names:
        s = _safe(src_real, name)
        d = _safe(dst, name)
        os.makedirs(os.path.dirname(d), exist_ok=True)
        if os.path.isdir(s):
            shutil.copytree(s, d, dirs_exist_ok=True)
        else:
            shutil.copy2(s, d)
    return dst
