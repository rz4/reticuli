"""The kernel's core layer: constants, the path and bytes boundaries, atomic IO, the refusal vocabulary."""
import hashlib
import json
import os
import shutil
import stat
import sys
import time

# ---------------------------------------------------------------- vocabulary

RECIPE = "reticuli.toml"
#: What the recipe was called before the file took the tool's name. Claims
#: sealed under it stay readable forever: the filename is NOT in the root
#: preimage -- `parts["recipe"]` is the PARSED recipe -- so a rename moves no
#: root, and a reader that only knew one name would refuse a claim whose
#: identity is unchanged. New claims are written as RECIPE.
LEGACY_RECIPE = "claim.toml"
STORE = ".reticuli"
MANIFEST = os.path.join(STORE, "manifest.json")
LEDGER = os.path.join(STORE, "ledger.jsonl")
SIGN_DIR = os.path.join(STORE, "mint")
MUTATION_RESIDUE = os.path.join(STORE, "mutation_score.json")
USAGE = os.path.join(STORE, "usage.json")

DIGEST = "sha256"

#: The claim-format version this kernel understands. A recipe may declare
#: `[claim] format`; absent means 1, so existing claims keep their identity.
#: Format 3 removes producer GUIDANCE from the root preimage (see `root`): a
#: hint that helps a producer find a realization cannot decide whether one is
#: accepted, so it is not part of identity. Formats 1 and 2 are unchanged, so
#: every claim sealed under them keeps its root.
FORMAT = 3

#: Step keys that are GUIDANCE, not criteria: they instruct a producer, they
#: never judge its output. Excluded from the preimage at format 3+.
GUIDANCE_KEYS = ("request", "guidance")

#: ssh signature namespaces -- interchange currency, carried from v1 so that
#: signatures made by one kernel verify under another.  The two domains are
#: distinct on purpose: an attestation must never authorize a mint.
NAMESPACE = "reticuli"
SIGN_NAMESPACE = "reticuli.mint"

#: "you are already inside a platform sandbox" -- one well-known name, so a
#: conformant kernel inherits the jail instead of trying to nest one.
_JAILED = "RETICULI_JAILED"

#: environment knobs a host may set
_ENV_TIMEOUT = "RETICULI_GATE_TIMEOUT"
_ENV_SIGNERS = "RETICULI_SIGNERS"
_ENV_TOLERANCE = "RETICULI_TOLERANCE"
_ENV_VENDOR = "RETICULI_VENDOR"
_ENV_MODEL = "RETICULI_MODEL"

#: environment a producer is handed
_ENV_OUTPUT = "RETICULI_OUTPUT"
_ENV_OUTPUTS = "RETICULI_OUTPUTS"
_ENV_REQUEST = "RETICULI_REQUEST"
_ENV_USAGE = "RETICULI_USAGE"
_ENV_CLAIM = "RETICULI_CLAIM"

KINDS = frozenset({"produce", "gate"})
GATE_TIMEOUT = 600.0
#: Building a claim's declared environment (venv + hash-pinned installs) may
#: download wheels; give it its own generous ceiling, separate from gates.
FURNISH_TIMEOUT = 900.0
#: Where furnished environments are cached, overridable for tests and for
#: hosts with their own cache discipline. The cache is host residue: keyed by
#: the environment file's digest, never part of any identity.
_ENV_CACHE = "RETICULI_ENV_CACHE"
#: A mutant gets this multiple of the healthy GATE's own runtime before the
#: clock counts as having detected it, bounded at both ends: never less than
#: the floor, since a gate that passes in 40ms must not have its mutants judged
#: against 400ms of a loaded machine, and never more than the ceiling, since a
#: slow gate would otherwise make a twenty-mutant run unaffordable.
MUTANT_HEADROOM = 10.0
MUTANT_FLOOR = 5.0
MUTANT_CEILING = 60.0
PRODUCER_TIMEOUT = 3600.0
TOLERANCE = 2.0
COST_KEYS = ("calls", "tokens", "usd")
# What `cost` totals. Wider than COST_KEYS on purpose: a producer may REPORT
# calls/tokens/usd, but wall-clock is the kernel's own measurement and must
# never be overwritten by a self-report -- so "seconds" is totalled here and
# not accepted from a usage payload. It is the last unit of the cost
# envelope's unit ladder (usd > tokens > calls > seconds); without it, two
# machines that measured only wall-clock share no unit to compare.
COST_UNITS = ("calls", "tokens", "usd", "seconds")
# The cost envelope compares ONE unit: the strongest both machines measured.
# Money is better evidence of work than tokens, tokens than calls, and
# wall-clock is the last resort -- it measures the host and its load as much
# as the work, so it must never veto a comparison a stronger unit can make.
COST_LADDER = ("usd", "tokens", "calls", "seconds")

#: env names a gate is allowed to see.  Everything else is scrubbed, so a
#: hostile gate cannot read an inherited secret and seal it into a verdict.
_KEEP_ENV = ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "TZ", _JAILED)

_SHELL = shutil.which("sh") or "/bin/sh"


class ClaimError(Exception):
    """A claim is damaged, hostile, or cannot be judged here.

    Everything the kernel refuses, it refuses in band with this: hostile bytes
    never surface as a raw TOMLDecodeError / JSONDecodeError / KeyError, and a
    verifier facing a wreck neither crashes nor blesses it.
    """


# ------------------------------------------------------------- small helpers

def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _judging_host() -> None:
    """Judging executes claim code -- sandboxes, process groups, sh -- and
    all of it is POSIX. Identity (root, seal, verify, reading records) works
    on any platform; on any other, judging refuses here, in band and in
    words, instead of dying in a traceback halfway through a verdict.
    """
    if os.name != "posix":
        raise ClaimError(
            f"judging runs on POSIX (macOS or Linux); this platform "
            f"({sys.platform}) can verify identity but cannot run gates")


def _write_json(path: str, payload) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, sort_keys=True, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def _safe(claimdir: str, name: str) -> str:
    """THE PATH BOUNDARY.  Resolve `name` inside the claim, or refuse.

    A claim's own recipe is untrusted input: a name that is absolute, climbs
    out with `..`, or is a symlink would let the kernel read or write outside
    the claim it is judging -- or alias one part of the claim as another.

    NO COMPONENT OF A DECLARED PATH MAY BE A SYMLINK, not even one whose
    target stays inside the claim.  An internal link from a pinned name to a
    generated output smuggles bytes across the pinned/generated boundary in
    both directions the design cares about: sealing hashes generated bytes
    into the root through the alias, and materializing flattens the link, so
    a blind rebuilder's room arrives holding the implementation it was never
    to see.  `..` is refused outright for the same reason a lexical check
    cannot be trusted: `link/../x` resolves relative to the link's target,
    not its name.  The hardlink rule in `_hash_file` closes this channel's
    twin.
    """
    if not isinstance(name, str) or not name:
        raise ClaimError(f"not a usable path: {name!r}")
    if "\x00" in name:
        raise ClaimError("a path may not contain NUL")
    if os.path.isabs(name) or name.startswith("~"):
        raise ClaimError(f"path escapes the claim (not relative): {name}")
    base = os.path.realpath(claimdir)
    walked = base
    for part in name.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            raise ClaimError(f"a path may not contain '..': {name}")
        walked = os.path.join(walked, part)
        if os.path.islink(walked):
            raise ClaimError(f"a path component is a symlink: {name} ({part})")
    resolved = os.path.realpath(os.path.join(base, name))
    if resolved == base:
        raise ClaimError(f"path is the claim directory itself: {name}")
    if not resolved.startswith(base + os.sep):
        raise ClaimError(f"path escapes the claim directory: {name}")
    return resolved


def _hash_file(path: str) -> str:
    """THE BYTES BOUNDARY.  sha256 of a file that lives inside the claim.

    A declared file must be a REGULAR file with a SINGLE link, so its bytes are
    the claim's own.  A hardlink to an outside inode keeps a local-looking name
    yet seals foreign bytes; a FIFO or device would block or feed nonsense into
    the claim; a directory is not a file.  All are refused here.
    """
    try:
        st = os.lstat(path)
    except OSError as exc:
        raise ClaimError(f"declared file is unreadable: {path} ({exc.strerror})") from None
    if stat.S_ISLNK(st.st_mode):
        raise ClaimError(f"declared file is a symlink: {path}")
    if stat.S_ISDIR(st.st_mode):
        raise ClaimError(f"declared file is a directory: {path}")
    if not stat.S_ISREG(st.st_mode):
        raise ClaimError(f"declared file is not a regular file: {path}")
    if st.st_nlink != 1:
        raise ClaimError(f"declared file has {st.st_nlink} links, so its bytes "
                         f"live outside the claim too: {path}")
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ClaimError(f"declared file is unreadable: {path} ({exc})") from None
    return digest.hexdigest()


def _copy_into(src: str, dst: str) -> None:
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    try:
        shutil.copyfile(src, dst)
        # Carry the permission bits: a generated output may legitimately BE an
        # executable (a compiled binary), and copyfile drops the exec bit, so a
        # gate that runs its own output would fail with "Permission denied" the
        # moment the claim is materialized anywhere. Only the low 9 bits travel
        # -- setuid, setgid and sticky are deliberately not carried into a
        # workspace the kernel just created.
        os.chmod(dst, stat.S_IMODE(os.stat(src).st_mode) & 0o777)
    except (OSError, shutil.Error) as exc:
        raise ClaimError(f"cannot materialize {dst}: {exc}") from None
