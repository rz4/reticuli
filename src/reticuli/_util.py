"""Small helpers the layers above the kernel share.

These exist for a reason worth stating. In v1 the shell modules imported the
kernel's PRIVATE helpers (`kernel._copy`, `_h`, `_ledger_add`, `_out`,
`_read`, `_seeds`) — tolerable only because one hand wrote both sides. The
v2 kernel was regrown blind from its acceptance check, which pins a public
surface and says nothing about private helpers; the regrown kernel duly
named them differently or not at all. So the layers above depend on the
kernel's PINNED PUBLIC surface only, and keep their own small utilities
here. Nothing in this module reaches into `kernel._*`.

If a helper here ever needs the kernel's semantics exactly (path
confinement, file hashing), the kernel's public behavior is the authority
and this module must follow it — see spec/identity.md.
"""
import hashlib
import json
import os
import shutil
import time

try:
    import fcntl  # POSIX advisory locks
except ImportError:                       # Windows: judging already refuses
    fcntl = None

STORE = ".reticuli"
LEDGER = os.path.join(STORE, "ledger.jsonl")
RECIPE = "claim.toml"


def locked_append(path: str, line: str) -> None:
    """Append one line, serialized against concurrent writers.

    An agent swarm and its subprocesses append to one trace at once; a plain
    O_APPEND write can tear when a line exceeds the platform's atomic-write
    size, so each append takes a brief exclusive lock for its write. POSIX
    flock; where it is unavailable (Windows, some network filesystems) the
    append is best-effort — capture is re-derivable residue, never identity, so
    a lost or torn line costs a re-run, never a wrong root."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        if fcntl is not None:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            except OSError:
                pass                       # unlockable fs: proceed best-effort
        f.write(line)
        f.flush()                          # leave the lock's window as small as the write


def stamp(event: dict) -> dict:
    """Capture provenance for one trace event: a unique id, and the originating
    run and its parent where a coordinator declared them (`RETICULI_RUN` /
    `RETICULI_PARENT`), so an agent swarm's causal tree is reconstructable from
    one shared trace. `ts` is informational only: ordering comes from the append
    order and these fields, never from the clock, which two concurrent writers
    cannot be trusted to stamp in causal order."""
    ev = dict(event)
    ev.setdefault("ts", round(time.time(), 3))
    ev["id"] = os.urandom(8).hex()
    run = os.environ.get("RETICULI_RUN")
    if run:
        ev["run"] = run
    parent = os.environ.get("RETICULI_PARENT")
    if parent:
        ev["parent"] = parent
    return ev


def trace_append(path: str, event: dict) -> None:
    """Stamp a capture event with provenance and append it, lock-serialized."""
    locked_append(path, json.dumps(stamp(event), sort_keys=True) + "\n")


def hash_bytes(b: bytes) -> str:
    """sha256 hex of raw bytes — the digest spec/identity.md names."""
    return hashlib.sha256(b).hexdigest()


def read_json(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str, obj: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=True)
        f.write("\n")


def copy_into(src: str, dst: str) -> None:
    """Copy a file, creating the destination's parent directories."""
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    shutil.copyfile(src, dst)


def ledger_add(d: str, entry: dict) -> None:
    """Append one JSON line to the claim's ledger (residue, never identity),
    lock-serialized like the trace so a concurrent write cannot tear it."""
    os.makedirs(os.path.join(d, STORE), exist_ok=True)
    locked_append(os.path.join(d, LEDGER), json.dumps(entry, sort_keys=True) + "\n")


def step_output(step: dict) -> str:
    return step["output"]


def declared_inputs(recipe: dict) -> list[str]:
    """The claim's pinned inputs — part of its identity (spec/claim-format.md)."""
    return recipe.get("claim", {}).get("inputs", [])


def safe_path(root: str, name: str) -> str:
    """Join a recipe-declared path under `root`, refusing any that escapes it:
    absolute, empty, a `..` climb, or a symlink whose target leaves the claim.
    Mirrors the kernel's confinement rule (spec/identity.md); the kernel's
    behavior is the authority if the two ever disagree."""
    if not name or os.path.isabs(name):
        raise ValueError(f"unsafe recipe path (absolute or empty): {name!r}")
    root_r = os.path.realpath(root)
    full = os.path.realpath(os.path.join(root_r, name))
    if full != root_r and not full.startswith(root_r + os.sep):
        raise ValueError(f"unsafe recipe path (escapes the claim root): {name!r}")
    return os.path.join(root, name)
