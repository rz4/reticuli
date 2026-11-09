"""The generation jail: confine what a PRODUCER may read, and record what it
tried to touch.

`run.py` holds the judgment sandbox -- gates are confined so a stranger's
criterion cannot reach the user's files.  This module is the other half of the
produce/judge split: the producer is confined so it cannot reach the one thing
that would let it cheat -- the original bytes it is being asked to re-derive.
In a rebuild those bytes sit in the SOURCE CLAIM, materialized generated
outputs and all; an unconfined producer can simply read them back and every
"reproduction" is a copy.  The jail closes that road and says whether it was
tried.

Two guarantees, in order of strength:

  1. DENIAL, kernel-enforced on both backends: content under a forbidden root
     cannot be read or written.  Seatbelt denies the access; bubblewrap masks
     the root with an empty filesystem.  Either way the original is
     unrecoverable from inside.
  2. THE TOUCH RECEIPT, best-effort evidence where the platform provides a
     channel: on macOS the Sandbox subsystem logs every denial with its exact
     path, and the receipt collects them after the run.  bubblewrap's mask
     produces no denial events, so there the receipt honestly reports that no
     attempt record is available.  The receipt is attached evidence, not the
     guarantee; the denial is the guarantee.

The policy is the inverse of the gate jail's: (allow default), deny the
forbidden roots, then re-allow the room and any kept roots -- last match wins,
so a room NESTED under a forbidden root is still fully usable.  All paths are
matched RESOLVED (seatbelt compares realpaths; `/tmp` vs `/private/tmp` once
slipped a deny).

Sandboxes do not nest.  Inside an existing jail (`RETICULI_JAILED`), or on a
host where neither backend actually applies, the backend is `none` -- and a
caller that REQUESTED confinement is refused rather than silently served an
unjailed run.  The jailed producer's own environment carries `RETICULI_JAILED`
set to the backend name, so a nested gate reports `inherited` instead of dying
against the no-nesting rule.
"""
import os
import shutil
import subprocess
import sys
import time

from .core import _JAILED, ClaimError
from .run import (
    _bwrap_hardening,
    _quote_sb,
    _seatbelt_usable,
)

_BWRAP_JAIL_OK = None

#: How long the unified log is given to settle before denials are collected.
#: Measured on the clone campaign: denials logged during the run are visible
#: ~1s after the process exits; collecting immediately loses the tail.
_LOG_SETTLE_SECONDS = 1.2


def _bwrap_jail_usable() -> bool:
    """Does bwrap accept THIS jail's argv shape, not the gate jail's?

    The gate jail ro-binds the root; this one needs a writable root bind plus
    a tmpfs mask, and a host can accept one shape and refuse the other.  The
    probe mirrors the real argv, same rule as `_bwrap_probe`: presence is not
    usability, and a non-functional sandbox counts as none, honestly.
    """
    global _BWRAP_JAIL_OK
    if _BWRAP_JAIL_OK is None:
        if not shutil.which("bwrap"):
            _BWRAP_JAIL_OK = False
        else:
            try:
                probe = subprocess.run(
                    ["bwrap", "--bind", "/", "/", "--dev-bind", "/dev", "/dev",
                     "--proc", "/proc", "--tmpfs", "/var/empty",
                     "--die-with-parent", *_bwrap_hardening(), "true"],
                    capture_output=True, check=False, timeout=30)
                _BWRAP_JAIL_OK = probe.returncode == 0
            except (OSError, subprocess.SubprocessError):
                _BWRAP_JAIL_OK = False
    return _BWRAP_JAIL_OK


def jail_backend() -> str:
    """Which generation jail this host can apply, here, now.

    `none` inside an existing jail: re-applying refuses (sandboxes do not
    nest), and unlike a gate -- which may honestly run `inherited`, because
    the outer jail still confines it -- a producer jail that is not THIS
    jail enforces someone else's policy, not the forbidden roots."""
    if os.environ.get(_JAILED):
        return "none"
    if sys.platform == "darwin" and _seatbelt_usable():
        return "seatbelt"
    if _bwrap_jail_usable():
        return "bubblewrap"
    return "none"


def _ancestor_chain(*paths: str) -> list[str]:
    """Every proper ancestor, deduplicated, order kept -- a subpath allow does
    not open the road TO the subtree (see run.py's strict tier), so ancestors
    of the room that sit under a forbidden root need metadata back."""
    seen: dict[str, None] = {}
    for p in paths:
        d = os.path.dirname(p)
        while len(d) > 1:
            seen.setdefault(d, None)
            d = os.path.dirname(d)
    return list(seen)


def jail_wrap(room: str, forbid=(), keep=(), deny_network=False):
    """The producer jail, as a command prefix: `(backend, argv_prefix, state)`.

    `room` is where the producer works, read-write.  `forbid` roots are
    unreadable and unwritable; `keep` roots are carved back out of them (a
    credential store under a forbidden home, the room's venv under a
    forbidden scratch tree).  `state` goes back into `jail_receipt` after the
    run.  Backend `none` returns an empty prefix -- the CALLER decides
    whether unconfined is acceptable; `rebuild --jail` refuses.
    """
    room = os.path.realpath(room)
    forbid = [os.path.realpath(p) for p in forbid]
    keep = [os.path.realpath(p) for p in keep]
    backend = jail_backend()
    state = {"backend": backend, "room": room, "forbidden_roots": forbid,
             "network": "denied" if deny_network else "allowed",
             "since": time.strftime("%Y-%m-%d %H:%M:%S")}
    if backend == "seatbelt":
        lines = ["(version 1)", "(allow default)"]
        if deny_network:
            lines.append("(deny network*)")
        if forbid:
            subpaths = " ".join(f'(subpath "{_quote_sb(p)}")' for p in forbid)
            lines.append(f"(deny file-read* {subpaths})")
            lines.append(f"(deny file-write* {subpaths})")
        reallow = " ".join(f'(subpath "{_quote_sb(p)}")'
                           for p in [room, *keep])
        lines.append(f"(allow file-read* {reallow})")
        lines.append(f"(allow file-write* {reallow})")
        # the road TO the room: realpath(3) stats every ancestor as its own
        # lookup, and an ancestor under a forbidden root is denied by the
        # subpath deny above.  Metadata on the chain leaks that directories
        # exist, nothing more.
        lines.append("".join(
            f'(allow file-read-metadata (literal "{_quote_sb(a)}"))'
            for a in _ancestor_chain(room, *keep)))
        return backend, ["sandbox-exec", "-p", "".join(lines)], state
    if backend == "bubblewrap":
        argv = ["bwrap", "--bind", "/", "/", "--dev-bind", "/dev", "/dev",
                "--proc", "/proc", "--die-with-parent", *_bwrap_hardening()]
        for p in forbid:
            # masks, not denials: the root reads as empty.  A directory takes
            # a tmpfs; a plain file is shadowed by an empty one.
            argv += (["--tmpfs", p] if os.path.isdir(p)
                     else ["--ro-bind", "/dev/null", p])
        # re-open the room and the kept roots AFTER the masks -- bwrap mounts
        # stack in argv order, the same last-match-wins the seatbelt arm has
        for p in (room, *keep):
            if os.path.exists(p):
                argv += ["--bind", p, p]
        if deny_network:
            argv += ["--unshare-net"]
        return backend, argv, state
    return backend, [], state


def _collect_touches(since: str, forbid) -> list:
    """macOS only: Sandbox-subsystem denials in [since, now] whose path is
    under a forbidden root -- the producer's out-of-room access attempts."""
    try:
        out = subprocess.run(
            ["log", "show", "--start", since,
             "--predicate", 'sender == "Sandbox"', "--style", "compact"],
            capture_output=True, text=True, timeout=120).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        return [{"error": f"log collection failed: {exc}"}]
    touches = []
    for line in out.splitlines():
        if "deny(" not in line:
            continue
        for root in forbid:
            if root in line:
                # ...Sandbox: proc(pid) deny(1) <operation> <path>
                touches.append(line.split("Sandbox:", 1)[-1].strip())
                break
    seen: dict[str, None] = {}
    for t in touches:
        seen.setdefault(t, None)
    return list(seen)


def jail_receipt(state: dict, exit_code: int) -> dict:
    """The touch receipt: what the producer tried outside its room.

    Seatbelt hosts get the positive record from the unified log, split into
    content attempts (file-read-data / file-write -- the cheat that matters)
    and metadata lookups (ancestor-stat noise the deny boundary also catches).
    bubblewrap hosts get the denial without the record, and the receipt says
    so instead of implying a clean log.  A BREACH verdict means attempts were
    made AND DENIED -- the room's bytes are untainted either way; what policy
    does with the attempt is the caller's verdict, not this module's.
    """
    receipt = dict(state)
    receipt["exit"] = exit_code
    if state["backend"] == "seatbelt" and state["forbidden_roots"]:
        time.sleep(_LOG_SETTLE_SECONDS)
        touches = _collect_touches(state["since"], state["forbidden_roots"])
        data = [t for t in touches if isinstance(t, str)
                and ("file-read-data" in t or "file-write" in t)]
        meta = [t for t in touches if t not in data]
        receipt["content_attempts"] = data
        receipt["metadata_lookups"] = len(meta)
        receipt["verdict"] = (
            "CLEAN" if not data
            else f"BREACH ATTEMPT — {len(data)} out-of-room content access(es), all denied")
    else:
        receipt["content_attempts"] = None
        receipt["verdict"] = ("CLEAN (denial enforced; no attempt record on "
                              "this backend)" if state["backend"] != "none"
                              else "UNJAILED")
    return receipt


def require_jail() -> str:
    """The backend, or a refusal: a caller that asked for confinement is
    never silently served an unjailed producer."""
    backend = jail_backend()
    if backend == "none":
        inside = os.environ.get(_JAILED)
        why = (f"already inside a {inside} jail, and sandboxes do not nest"
               if inside else "no usable sandbox backend on this host")
        raise ClaimError(f"jail: cannot confine the producer — {why}. "
                         "Run without --jail only if an unconfined producer "
                         "is acceptable; the ledger will say which it was.")
    return backend
