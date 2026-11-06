"""The innermost layer: two boundaries, the vocabulary, and the constants.

Everything else in the kernel reaches the filesystem through exactly two
functions here, and that is the whole point of the module:

* `_safe(claim, name)` is the PATH boundary.  A recipe is untrusted input, so
  every declared name is resolved through it — absolute paths, empty names,
  `..` components and symlink components are refused rather than followed
  (`spec/identity.md`, *File hashing rules*).
* `_hash_file(path)` is the BYTES boundary.  A hashed file must be a regular
  file with a single hard link, so its bytes live inside the claim and nowhere
  else; a FIFO, device, socket, directory, or hardlink to a foreign inode is
  refused, not hashed.

The constants below are the shared contract: protocol values (`NAMESPACE`,
`DIGEST`), on-disk layout (`STORE`, `MANIFEST`, `LEDGER`, `SIGN_DIR`),
environment-variable spellings, and the closed vocabularies.  Their VALUES
travel between implementations, so they are pinned by the core criterion; the
tuning numbers beside them are policy and are pinned only by kind.
"""
import hashlib
import json
import os
import platform
import shutil
import stat
import sys
import time

# -- the refusal ------------------------------------------------------------


class ClaimError(Exception):
    """A refusal with a reason — the only error the kernel raises.

    Hostile or damaged claim bytes must never surface as a raw
    TOMLDecodeError, JSONDecodeError, KeyError or UnicodeDecodeError: a
    verifier facing a wreck refuses in band and says why.
    """


# -- protocol and on-disk contract (pinned by value) ------------------------

#: The attestation signature namespace (carried from v1 so v1 signatures stay
#: verifiable).  Distinct from SIGN_NAMESPACE and RECORD_NAMESPACE: a
#: signature made for one purpose must not be presentable for another.
NAMESPACE = "reticuli"
#: The digest algorithm, stated in-band in every preimage.
DIGEST = "sha256"
#: The newest claim format this kernel understands (`spec/claim-format.md`).
FORMAT = 6

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
RECORD_FORMAT = 2

#: Residue, outside every root: the sealed parts map (so a broken verify can
#: NAME the file that moved), the audit receipt, and the gates' scratch space.
PARTS = ".reticuli/parts.json"
RECEIPT = ".reticuli/receipt.json"
SCRATCH = ".reticuli/scratch"
DECIDING = ".reticuli/deciding.json"
SEALED = ".reticuli/sealed"

# -- environment variables (pinned by value) --------------------------------

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
_ENV_PRODUCER = "RETICULI_PRODUCER"
_ENV_KEY = "RETICULI_KEY"
_ENV_CACHE_DIR = "RETICULI_CACHE"
_ENV_COLOR = "RETICULI_COLOR"
_ENV_PRICE = "RETICULI_PRICE"

#: The host allowlist a gate's scrubbed environment keeps.  Everything else
#: an inherited environment carries — credentials above all — never reaches a
#: gate.  LANG/LC_ALL/TZ/HOME are granted because tools need a coherent
#: environment; a verdict that depended on their VALUES would be a verdict
#: about the host, which `criteria/obligations_check.py` samples against.
_KEEP_ENV = ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "TZ",
             "RETICULI_JAILED")

# -- tuning and vocabulary (pinned by kind) ---------------------------------

#: Seconds a gate may run when its claim declares nothing.  A declared
#: `gate_timeout` IS the ceiling and may raise this (`criteria/run_check.py`).
GATE_TIMEOUT = 300.0
#: Seconds the furnish step (building the private venv) may take.
FURNISH_TIMEOUT = 900.0
#: Seconds one producer invocation may take.
PRODUCER_TIMEOUT = 3600.0
#: The cost band applied when a claim declares no tolerance — an OBSERVATION
#: a reader weighs, never a reason to reject (`spec/verification.md`).
TOLERANCE = 2.0

MUTANT_CEILING = 64
MUTANT_FLOOR = 4
MUTANT_HEADROOM = 8

#: The four cost units, and the ladder the comparison walks: exactly ONE unit
#: decides — the strongest both machines measured — so wall-clock can never
#: veto a comparison a stronger unit is able to make.
COST_KEYS = ("usd", "tokens", "calls", "seconds")
COST_LADDER = ("usd", "tokens", "calls", "seconds")
COST_UNITS = ("usd", "tokens", "calls", "seconds")
#: Both spellings of a produce step's producer hint.  Stripped from the
#: preimage at format 3 and above: a hint cannot decide acceptance.
GUIDANCE_KEYS = ("guidance", "request")
#: The step vocabulary the claim format defines — exactly two kinds.
KINDS = frozenset({"produce", "gate"})
#: The step classes, and the formats that admit each.
CLASSES = frozenset({"generated", "pinned", "validated", "carried"})
#: The shell a gate command is handed to.
_SHELL = "/bin/sh"


# -- the bytes boundary -----------------------------------------------------


def _hash_file(path: str) -> str:
    """The sha256 of a file's bytes, with the filesystem adversaries refused.

    A declared file must be a REGULAR file with a SINGLE link, so its bytes
    live inside the claim and nowhere else.  A hardlink to a foreign inode
    keeps a local-looking path yet would seal outside bytes as the claim's
    own; a FIFO or device would block or return nonsense; a directory is not
    a file.  All are refused here, at the one bytes boundary.
    """
    try:
        st = os.lstat(path)
    except OSError as exc:
        raise ClaimError(f"{path}: {exc.strerror or exc}") from None
    if stat.S_ISLNK(st.st_mode):
        raise ClaimError(f"{path}: a declared file may not be a symlink")
    if not stat.S_ISREG(st.st_mode):
        raise ClaimError(f"{path}: not a regular file")
    if st.st_nlink != 1:
        raise ClaimError(
            f"{path}: {st.st_nlink} hard links — a declared file's bytes must "
            f"live inside the claim and nowhere else")
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ClaimError(f"{path}: {exc.strerror or exc}") from None
    return digest.hexdigest()


def hash_bytes(data: bytes) -> str:
    """The sha256 of bytes already in hand."""
    return hashlib.sha256(data).hexdigest()


# -- the path boundary ------------------------------------------------------


def _safe(claim: str, name: str) -> str:
    """Resolve a recipe-declared path inside the claim, or refuse it.

    Refused: an absolute or empty name, any `..` component (with a link in
    play, `link/../x` resolves against the link's TARGET, so no lexical
    reading of such a path is trustworthy), and any symlink component — even
    one whose target stays inside the claim, because an internal link can
    alias generated bytes as a pinned name.
    """
    if not isinstance(name, str) or not name.strip():
        raise ClaimError("a declared path must be a non-empty string")
    flat = name.replace("\\", "/")
    if flat.startswith("/") or os.path.isabs(name) or ":" in flat.split("/")[0][1:2]:
        raise ClaimError(f"declared path {name!r} is absolute")
    parts = [p for p in flat.split("/") if p not in ("", ".")]
    if not parts:
        raise ClaimError(f"declared path {name!r} names nothing")
    if ".." in parts:
        raise ClaimError(
            f"declared path {name!r} has a '..' component — a declared path "
            f"is confined to the claim directory")
    base = os.path.realpath(claim)
    here = base
    for part in parts:
        here = os.path.join(here, part)
        if os.path.islink(here):
            raise ClaimError(
                f"declared path {name!r} has a symlink component ({part!r}) — "
                f"a link can alias generated bytes as a pinned name")
    if here != base and not here.startswith(base + os.sep):
        raise ClaimError(f"declared path {name!r} escapes the claim directory")
    return here


def safe_path(claim: str, name: str) -> str:
    """The path boundary, under the name the layers above import."""
    return _safe(claim, name)


# -- small primitives the whole kernel shares -------------------------------


def _write_json(path: str, payload) -> None:
    """Write JSON atomically: a crash never leaves half a manifest."""
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    tmp = path + ".writing"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def _read_json(path: str):
    """Read JSON, refusing damaged bytes in band."""
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except OSError as exc:
        raise ClaimError(f"{path}: {exc.strerror or exc}") from None
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ClaimError(f"{path}: not readable as JSON ({exc})") from None


def _now() -> str:
    """The current UTC time, `YYYY-MM-DDTHH:MM:SSZ`.

    UTC whatever TZ says: a recorded time is a fact about the moment, not
    about the host's locale.
    """
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _copy_into(src: str, dst: str) -> None:
    """Copy one file to `dst`, creating parents and carrying the mode.

    The mode matters: a format-6 build digest commits the owner-execute bit,
    so a copy that dropped it would change what the digest names.
    """
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    shutil.copyfile(src, dst)
    shutil.copymode(src, dst)


def copy_into(src: str, dst: str) -> None:
    """`_copy_into`, under the name the layers above import."""
    _copy_into(src, dst)


def _judging_host() -> dict:
    """The verdict environment, as residue on a redo's ledger."""
    return {
        "python": f"{platform.python_implementation()} "
                  f"{platform.python_version()}",
        "platform": sys.platform,
        "machine": platform.machine(),
    }


def _finite(value) -> bool:
    """True for a real measurement: a number, not a boolean, not NaN or inf.

    Neither NaN nor an infinity reports any work done, and both poison the
    comparison a cost exists for — so neither is a measurement.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return value == value and value not in (float("inf"), float("-inf"))
