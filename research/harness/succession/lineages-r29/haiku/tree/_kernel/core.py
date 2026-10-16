"""Kernel core: the two boundaries and the primitives beneath everything.

* the path boundary  -- ``_safe`` resolves a recipe-declared name to a path
  inside the claim, refusing anything that escapes it;
* the bytes boundary -- ``_hash_file`` is a plain sha256 of a regular file's
  bytes, refusing non-regular files and hard links;
* atomic JSON write  -- ``_write_json`` (temp file + ``os.replace``);
* the refusal vocabulary -- ``ClaimError``, the only kernel error.

Also exports the protocol constants and tuning values the layers above
import from here. Stdlib only, never the network.
"""
import hashlib
import json
import os
import platform
import shutil
import stat
import sys
import tempfile
import time

# ---------------------------------------------------------------- protocol
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

# ------------------------------------------------------- environment names
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

# ------------------------------------------------------ tuning and policy
GATE_TIMEOUT = 120.0
FURNISH_TIMEOUT = 600.0
PRODUCER_TIMEOUT = 1800.0
TOLERANCE = 2.0
MUTANT_CEILING = 200
MUTANT_FLOOR = 8
MUTANT_HEADROOM = 1.25
_SHELL = "/bin/sh"

# Cost vocabulary, strongest unit first (usd > tokens > calls > seconds).
COST_KEYS = ("usd", "tokens", "calls", "seconds")
COST_UNITS = COST_KEYS
COST_LADDER = COST_KEYS

# Producer hints a format-3+ recipe strips from every step before hashing.
GUIDANCE_KEYS = ("guidance", "request")

# The step-kind vocabulary the claim format defines -- exactly these two.
KINDS = frozenset({"produce", "gate"})


# ------------------------------------------------------------- refusals
class ClaimError(Exception):
    """A refusal with a reason -- the only error the kernel raises."""


# ------------------------------------------------------------ host helpers
def _now() -> str:
    """UTC time of recording, ``YYYY-MM-DDTHH:MM:SSZ`` (the record format)."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _judging_host() -> dict:
    """The host that produced a record: platform, machine, runtime strings."""
    return {
        "platform": platform.system().lower(),
        "machine": platform.machine(),
        "runtime": f"CPython {platform.python_version()}"
        if sys.implementation.name == "cpython"
        else f"{sys.implementation.name} {platform.python_version()}",
    }


# ------------------------------------------------------------ bytes boundary
def _hash_file(path: str) -> str:
    """sha256 hex of a regular file's bytes; refuses anything else."""
    st = os.lstat(path)
    if not stat.S_ISREG(st.st_mode):
        raise ClaimError(f"not a regular file (refused): {path}")
    if st.st_nlink != 1:
        raise ClaimError(f"hard-linked file refused (nlink={st.st_nlink}): {path}")
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _copy_into(src: str, dst: str) -> None:
    """Copy a file, or the regular files of a tree, from src into dst.

    Symlinks and special files are refused rather than followed, so a copy
    can never smuggle bytes from outside the source.
    """
    if os.path.isdir(src) and not os.path.islink(src):
        for dirpath, dirnames, filenames in os.walk(src, followlinks=False):
            rel = os.path.relpath(dirpath, src)
            target_dir = dst if rel == os.curdir else os.path.join(dst, rel)
            os.makedirs(target_dir, exist_ok=True)
            for name in filenames:
                _copy_one(os.path.join(dirpath, name),
                          os.path.join(target_dir, name))
            for name in dirnames:
                full = os.path.join(dirpath, name)
                if os.path.islink(full):
                    raise ClaimError(f"symlink refused in copy: {full}")
    else:
        parent = os.path.dirname(os.path.abspath(dst))
        os.makedirs(parent, exist_ok=True)
        _copy_one(src, dst)


def _copy_one(src: str, dst: str) -> None:
    st = os.lstat(src)
    if not stat.S_ISREG(st.st_mode):
        raise ClaimError(f"not a regular file (refused): {src}")
    shutil.copyfile(src, dst)
    shutil.copymode(src, dst)


# ------------------------------------------------------------ path boundary
def _safe(d: str, rel: str) -> str:
    """Resolve a claim-relative name to a path under the claim directory.

    Refuses an empty or absolute name, any ``..`` / ``.`` / empty component,
    and any component that is a symlink (even one that stays inside the
    claim). The file need not exist.
    """
    if not isinstance(rel, str) or rel == "" or "\x00" in rel:
        raise ClaimError(f"empty or invalid path refused: {rel!r}")
    if rel.startswith("/") or os.path.isabs(rel):
        raise ClaimError(f"absolute path refused: {rel!r}")
    parts = rel.split("/")
    for part in parts:
        if part in ("", ".", ".."):
            raise ClaimError(f"path component {part!r} refused in {rel!r}")
    root = os.path.realpath(d)
    cur = root
    for part in parts:
        cur = os.path.join(cur, part)
        if os.path.islink(cur):
            raise ClaimError(f"symlink component refused in {rel!r}")
    resolved = os.path.join(root, *parts)
    if os.path.commonpath([resolved, root]) != root:
        raise ClaimError(f"path escapes the claim: {rel!r}")
    return resolved


# ------------------------------------------------------------- atomic write
def _write_json(path: str, obj) -> None:
    """Write obj as JSON atomically: temp file in the same dir, then replace."""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".tmp-")
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
