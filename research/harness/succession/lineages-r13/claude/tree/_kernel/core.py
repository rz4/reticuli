"""The two boundaries and the primitives beneath everything.

The path boundary (`_safe` refuses a name that escapes the claim), the
bytes boundary (`_hash_file` is a plain sha256 of the file), atomic JSON
writes, and the protocol constants every higher layer shares. Stdlib only,
never the network.
"""
import hashlib
import json
import os
import shutil
import tempfile
import time


class ClaimError(Exception):
    """A refusal with a reason -- the only kernel error."""


# Protocol constants: the on-disk / environment contract, shared verbatim
# across layers and with the record format.
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

# Tuning constants: the name and kind are the seam, the value is policy.
GATE_TIMEOUT = 120.0
FURNISH_TIMEOUT = 300.0
PRODUCER_TIMEOUT = 600.0
TOLERANCE = 2.0
MUTANT_CEILING = 50
MUTANT_FLOOR = 0.6
MUTANT_HEADROOM = 0.1

COST_KEYS = ("usd", "tokens", "calls", "seconds")
COST_LADDER = ("usd", "tokens", "calls", "seconds")
COST_UNITS = ("usd", "tokens", "calls", "seconds")

GUIDANCE_KEYS = ("guidance", "request")

KINDS = frozenset({"produce", "gate"})

_SHELL = "/bin/sh"


def _now() -> str:
    """UTC time of recording, YYYY-MM-DDTHH:MM:SSZ."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _hash_file(path: str) -> str:
    """The bytes boundary: a plain sha256 of the file's bytes."""
    st = os.lstat(path)
    if not os.path.isfile(path) or os.path.islink(path):
        raise ClaimError(f"refuses to hash a non-regular-file: {path!r}")
    if st.st_nlink != 1:
        raise ClaimError(f"refuses to hash a hard-linked file: {path!r}")
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe(base: str, name: str) -> str:
    """The path boundary: a name inside the claim resolves; an escape refuses."""
    if not name or not isinstance(name, str):
        raise ClaimError(f"refuses an empty or non-string path: {name!r}")
    if os.path.isabs(name) or "\x00" in name:
        raise ClaimError(f"refuses an absolute path: {name!r}")
    parts = name.replace("\\", "/").split("/")
    if any(p in ("", "..", ".") for p in parts):
        raise ClaimError(f"refuses a path that escapes the claim: {name!r}")

    base_real = os.path.realpath(base)
    cur = base_real
    for part in parts:
        candidate = os.path.join(cur, part)
        if os.path.islink(candidate):
            raise ClaimError(f"refuses a symlink component: {name!r}")
        cur = candidate

    resolved = os.path.normpath(os.path.join(base_real, *parts))
    if resolved != base_real and not resolved.startswith(base_real + os.sep):
        raise ClaimError(f"refuses a path that escapes the claim: {name!r}")
    return resolved


def _write_json(path: str, obj) -> None:
    """Atomic JSON write: write to a scratch file, then replace."""
    directory = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, sort_keys=True)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _copy_into(src: str, dst: str) -> None:
    """Materialize one path's bytes from a claim into a room, directories included."""
    if os.path.isdir(src):
        shutil.copytree(src, dst, symlinks=False, dirs_exist_ok=True)
    else:
        os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
        shutil.copyfile(src, dst)


def _judging_host() -> dict:
    """A plain description of this host's sandbox capability, unprobed here."""
    import platform
    import sys as _sys

    if platform.system() == "Darwin":
        backend = "seatbelt" if shutil.which("sandbox-exec") else "none"
    elif platform.system() == "Linux":
        backend = "bubblewrap" if shutil.which("bwrap") else "none"
    else:
        backend = "none"
    return {
        "backend": backend,
        "platform": platform.system().lower(),
        "machine": platform.machine(),
        "runtime": f"{platform.python_implementation()} {_sys.version.split()[0]}",
    }
