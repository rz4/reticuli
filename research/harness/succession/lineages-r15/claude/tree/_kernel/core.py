"""Kernel core: the two boundaries and the primitives beneath everything.

The path boundary (`_safe`) refuses a name that escapes the claim directory.
The bytes boundary (`_hash_file`) is a plain sha256 of a file's bytes. Atomic
JSON writes (`_write_json`) never leave a half-written file behind. Every
refusal in this package and the layers above it raises `ClaimError` — the
one kernel exception, carrying a reason rather than a bare traceback.

Stdlib only; this module never touches the network.
"""
import hashlib
import json
import os
import platform
import shutil
import tempfile
import time

# -- Protocol constants: the on-disk / environment contract, shared verbatim
# across the kernel and the record format. ------------------------------

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

# -- Tuning constants and host-derived vocabulary: name and kind are the
# seam, exact value is policy. ------------------------------------------

GATE_TIMEOUT = 120.0
FURNISH_TIMEOUT = 600.0
PRODUCER_TIMEOUT = 1800.0
TOLERANCE = 2.0
MUTANT_CEILING = 64
MUTANT_FLOOR = 8
MUTANT_HEADROOM = 1.25

COST_KEYS = ("usd", "tokens", "calls", "seconds")
COST_LADDER = ("usd", "tokens", "calls", "seconds")
COST_UNITS = ("usd", "tokens", "calls", "seconds")
GUIDANCE_KEYS = ("guidance", "request")

# The step-kind vocabulary: content, not just type. Exactly the two kinds
# the claim format defines (`spec/claim-format.md`).
KINDS = frozenset({"produce", "gate"})

_SHELL = "/bin/sh"


class ClaimError(Exception):
    """A refusal with a reason -- the only kernel error."""


def _safe(base: str, name: str) -> str:
    """Resolve `name` as a path inside `base`, or refuse.

    A recipe-declared path is refused if it is absolute or empty, if any
    component is `..`, or if any component is a symlink -- even one whose
    target stays inside the claim (`spec/identity.md`).
    """
    if not name:
        raise ClaimError(f"empty path is refused: {name!r}")
    if os.path.isabs(name):
        raise ClaimError(f"absolute path is refused: {name!r}")
    parts = name.split(os.sep)
    if os.altsep:
        parts = [p for piece in parts for p in piece.split(os.altsep)]
    for part in parts:
        if part in ("", ".."):
            raise ClaimError(f"path escapes the claim: {name!r}")

    root = os.path.realpath(base)
    resolved = root
    for part in parts:
        candidate = os.path.join(resolved, part)
        if os.path.islink(candidate):
            raise ClaimError(f"path crosses a symlink: {name!r}")
        resolved = candidate

    resolved = os.path.realpath(resolved)
    if resolved != root and not resolved.startswith(root + os.sep):
        raise ClaimError(f"path escapes the claim: {name!r}")
    return resolved


def _hash_file(path: str) -> str:
    """The bytes boundary: a plain sha256 of the file's bytes."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_json(path: str, obj) -> None:
    """Write `obj` as JSON atomically: never leave a half-written file."""
    directory = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, sort_keys=True)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _now() -> str:
    """UTC time of recording, `YYYY-MM-DDTHH:MM:SSZ` (`spec/record.md`)."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _copy_into(base: str, dest: str, name: str) -> str:
    """Copy the claim-relative entry `name` from `base` into `dest`.

    Used to materialize a room: only names that resolve under `base`
    (via `_safe`) may be copied, and directories copy recursively.
    """
    src = _safe(base, name)
    target = os.path.join(dest, name)
    os.makedirs(os.path.dirname(target) or dest, exist_ok=True)
    if os.path.isdir(src):
        shutil.copytree(src, target)
    else:
        shutil.copy2(src, target)
    return target


def _judging_host() -> dict:
    """A functional probe of the host sandbox (`spec/verification.md`).

    The return shape beyond the `backend` field is implementation-defined;
    this reports what confinement, if any, is available on this host.
    """
    system = platform.system()
    if system == "Darwin" and shutil.which("sandbox-exec"):
        backend = "seatbelt"
    elif system == "Linux" and shutil.which("bwrap"):
        backend = "bubblewrap"
    elif os.environ.get(_JAILED):
        backend = "inherited"
    else:
        backend = "none"
    return {
        "backend": backend,
        "platform": system.lower(),
        "machine": platform.machine(),
        "runtime": f"{platform.python_implementation()} {platform.python_version()}",
    }
