"""The kernel's innermost layer: two boundaries and the primitives on them.

The path boundary (`_safe`) refuses any claim-declared name that would
resolve outside the claim or through an internal symlink (spec/identity.md,
"File hashing rules"). The bytes boundary (`_hash_file`) is a plain sha256
of a regular, single-hard-linked file's bytes. `_write_json` writes a JSON
file atomically. `ClaimError` is the refusal vocabulary: the only error the
kernel raises on untrusted input, never a raw parse crash.

Everything here is a shared, on-disk/environment contract: the constants'
*values* are read by every layer above and by the record format
(spec/record.md, spec/kernel-api.md), so they are pinned exactly. Stdlib
only, never the network.
"""
import datetime
import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile

# -- The refusal vocabulary ------------------------------------------------


class ClaimError(Exception):
    """A refusal with a reason -- the only error the kernel raises."""


# -- Protocol constants: the on-disk / environment contract ---------------

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

# The minimal host allowlist a gate's scrubbed environment keeps, plus the
# kernel's own already-inside-a-sandbox signal.
_KEEP_ENV = ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "TZ", "RETICULI_JAILED")

# -- Tuning constants and host-derived vocabularies ------------------------
# Names and kinds are the seam; exact values are policy (spec/verification.md,
# "Implementation-defined behavior"), except KINDS, which is step vocabulary
# the recipe layer validates every step against and so is content, not just
# type.

GATE_TIMEOUT = 120.0
FURNISH_TIMEOUT = 300.0
PRODUCER_TIMEOUT = 600.0
TOLERANCE = 2.0

MUTANT_CEILING = 64
MUTANT_FLOOR = 0.6
MUTANT_HEADROOM = 0.1

# Strongest unit first: the cost ladder a comparison walks to find the one
# shared unit both sides measured (spec/verification.md).
COST_LADDER = ("usd", "tokens", "calls", "seconds")
COST_KEYS = ("usd", "tokens", "calls", "seconds")
COST_UNITS = ("usd", "tokens", "calls", "seconds")

# A produce step's hint key: both spellings are read (spec/claim-format.md,
# "Producer guidance versus criteria").
GUIDANCE_KEYS = ("guidance", "request")

# The step-kind vocabulary the claim format defines (spec/claim-format.md).
KINDS = frozenset({"produce", "gate"})

_SHELL = "/bin/sh"


# -- The bytes boundary -----------------------------------------------------


def _hash_file(path: str) -> str:
    """A plain sha256 of a file's bytes, refusing filesystem aliasing.

    Only a regular file with a single hard link is hashed (spec/identity.md,
    "File hashing rules"): a hardlink to an outside inode, or any special
    file (FIFO, device, socket), is refused rather than silently hashed.
    """
    st = os.lstat(path)
    if not stat.S_ISREG(st.st_mode):
        raise ClaimError(f"not a regular file: {path!r}")
    if st.st_nlink != 1:
        raise ClaimError(f"refusing a hard-linked file: {path!r}")
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


# -- The path boundary --------------------------------------------------


def _safe(base: str, name: str) -> str:
    """Resolve a claim-declared name under `base`, or refuse it.

    Refused: an absolute or empty name, any `..` or empty component, and
    any component that is a symlink -- even one whose target stays inside
    the claim (spec/identity.md). A plain relative name resolves to a real
    path under the claim.
    """
    if not isinstance(name, str) or name == "":
        raise ClaimError("a claim path must be a non-empty string")
    if os.path.isabs(name):
        raise ClaimError(f"a claim path must not be absolute: {name!r}")

    parts = name.split("/")
    for part in parts:
        if part in ("", ".", ".."):
            raise ClaimError(f"unsafe path component {part!r} in {name!r}")

    base_real = os.path.realpath(base)
    candidate = os.path.join(base_real, *parts)

    probe = base_real
    for part in parts:
        probe = os.path.join(probe, part)
        if os.path.islink(probe):
            raise ClaimError(f"a claim path must not cross a symlink: {name!r}")

    real = os.path.realpath(candidate)
    if real != candidate or not (
        real == base_real or real.startswith(base_real + os.sep)
    ):
        raise ClaimError(f"path escapes the claim: {name!r}")
    return real


# -- Atomic JSON write --------------------------------------------------


def _write_json(path: str, obj) -> None:
    """Write `obj` as JSON to `path`, atomically (write-temp, then rename)."""
    directory = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, sort_keys=True)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# -- Helpers the layers above import from core ------------------------------


def _now() -> str:
    """UTC time of recording, `YYYY-MM-DDTHH:MM:SSZ` (spec/record.md)."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _copy_into(base: str, dest: str, names) -> str:
    """Copy each named pinned file from `base` into `dest`, preserving
    its relative path. Used to materialize a room from a claim's pinned
    inputs. Refuses the same names `_safe` would refuse.
    """
    base_real = os.path.realpath(base)
    for name in names:
        src = _safe(base, name)
        rel = os.path.relpath(src, base_real)
        target = os.path.join(dest, rel)
        os.makedirs(os.path.dirname(target) or dest, exist_ok=True)
        shutil.copy2(src, target)
    return dest


def _judging_host() -> dict:
    """A functional probe of the host sandbox (spec/claim-format.md,
    "Gate execution contract"): a present-but-nonfunctional sandbox counts
    as none, honestly reported.
    """
    if sys.platform == "darwin" and shutil.which("sandbox-exec"):
        return {"backend": "seatbelt"}
    if shutil.which("bwrap"):
        return {"backend": "bubblewrap"}
    return {"backend": "none"}
