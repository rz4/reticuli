"""Kernel core: the two boundaries and the primitives beneath everything.

The path boundary (`_safe`) refuses a name that escapes the claim directory
or passes through a symlink. The bytes boundary (`_hash_file`) is a plain
sha256 of a file's bytes. `_write_json` writes a JSON document atomically.
`ClaimError` is the refusal vocabulary every layer above raises through.

Stdlib only, never the network.
"""
import datetime
import hashlib
import json
import os
import platform
import shutil
import sys
import tempfile

# --- protocol constants: the on-disk / environment contract ---------------
NAMESPACE = "reticuli"
DIGEST = "sha256"
FORMAT = 3
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

# --- tuning constants: names and kinds are the seam, values are policy ----
GATE_TIMEOUT = 120.0
FURNISH_TIMEOUT = 300.0
PRODUCER_TIMEOUT = 900.0
TOLERANCE = 2.0
MUTANT_CEILING = 0.95
MUTANT_FLOOR = 0.6
MUTANT_HEADROOM = 0.05
COST_KEYS = ("usd", "tokens", "calls", "seconds")
COST_LADDER = ("usd", "tokens", "calls", "seconds")
COST_UNITS = ("usd", "tokens", "calls", "seconds")
GUIDANCE_KEYS = ("guidance", "request")
KINDS = frozenset({"produce", "gate"})
_SHELL = "/bin/sh"


class ClaimError(Exception):
    """A refusal with a reason -- the only kernel error."""


def _hash_file(path: str) -> str:
    """The bytes boundary: a plain sha256 of the file's bytes."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe(base: str, name: str) -> str:
    """The path boundary: resolve `name` to a real path under `base`.

    Refuses an absolute or empty name, a `..` component, or any component
    that is a symlink -- even one whose target stays inside the claim.
    """
    if not name:
        raise ClaimError("path name must not be empty")
    if os.path.isabs(name):
        raise ClaimError(f"path name must not be absolute: {name!r}")
    parts = name.split("/")
    if any(p in ("", "..") for p in parts):
        raise ClaimError(f"path name must not escape the claim: {name!r}")

    real_base = os.path.realpath(base)
    walked = real_base
    for part in parts:
        walked = os.path.join(walked, part)
        if os.path.islink(walked):
            raise ClaimError(f"path name must not pass through a symlink: {name!r}")

    resolved = os.path.realpath(os.path.join(real_base, name))
    if resolved != real_base and not resolved.startswith(real_base + os.sep):
        raise ClaimError(f"path name escapes the claim: {name!r}")
    return resolved


def _write_json(path: str, obj) -> None:
    """Write JSON atomically: build the bytes off to the side, then rename."""
    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, sort_keys=True)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _now() -> str:
    """UTC time of recording, `YYYY-MM-DDTHH:MM:SSZ` (spec/record.md)."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _copy_into(src: str, dst: str) -> None:
    """Copy a file or directory tree from `src` to `dst`."""
    if os.path.isdir(src):
        shutil.copytree(src, dst, symlinks=False)
    else:
        parent = os.path.dirname(dst) or "."
        os.makedirs(parent, exist_ok=True)
        shutil.copy2(src, dst)


def _judging_host() -> dict:
    """Describe the host running a gate: `platform`, `machine`, `runtime`."""
    return {
        "platform": sys.platform,
        "machine": platform.machine(),
        "runtime": f"CPython {platform.python_version()}",
    }
