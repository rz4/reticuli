"""Small helpers shared by the layers above the kernel.

Nothing here is identity-bearing; these are plain filesystem, hashing, and
bookkeeping primitives the exchange layer (`registry.py`, `transfer.py`,
`attest.py`, `record.py`) reuses so each of those modules does not
reinvent path confinement or atomic JSON writes on its own. Refusals raise
`kernel.ClaimError` -- the one error vocabulary this project speaks in band.

Stdlib only.
"""
import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone

from . import kernel

STORE = ".reticuli"
LEDGER = ".reticuli/ledger.jsonl"
RECIPE = "claim.toml"


def hash_bytes(path: str) -> str:
    """A plain sha256 of a regular file's bytes."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str, obj) -> None:
    """Atomic JSON write: build the bytes off to the side, then rename in."""
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, sort_keys=True, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def copy_into(src: str, dst: str) -> str:
    """Copy a file or directory tree from `src` to `dst`, refusing symlinks."""
    if os.path.islink(src):
        raise kernel.ClaimError(f"refused: symlink {src!r}")
    if os.path.isdir(src):
        os.makedirs(dst, exist_ok=True)
        for entry in sorted(os.listdir(src)):
            copy_into(os.path.join(src, entry), os.path.join(dst, entry))
    else:
        parent = os.path.dirname(dst) or "."
        os.makedirs(parent, exist_ok=True)
        shutil.copy2(src, dst)
    return dst


def safe_path(root: str, name: str) -> str:
    """Resolve `name` under `root`, or refuse (no escapes, no symlinks)."""
    if not name:
        raise kernel.ClaimError("refused: empty path")
    if os.path.isabs(name):
        raise kernel.ClaimError(f"refused: absolute path {name!r}")
    parts = name.split("/")
    for part in parts:
        if part in ("", ".", ".."):
            raise kernel.ClaimError(f"refused: path escapes the claim: {name!r}")

    realroot = os.path.realpath(root)
    cur = realroot
    for part in parts:
        cur = os.path.join(cur, part)
        if os.path.islink(cur):
            raise kernel.ClaimError(f"refused: symlink component in {name!r}")

    if not (cur == realroot or cur.startswith(realroot + os.sep)):
        raise kernel.ClaimError(f"refused: path escapes the claim: {name!r}")
    return cur


def declared_inputs(d: str) -> list:
    """A claim's declared pinned inputs, from its recipe."""
    recipe = kernel.load_recipe(d)
    return list(recipe.get("claim", {}).get("inputs", []))


def step_output(recipe: dict, output: str):
    """The step in `recipe` pinning `output`, or `None`."""
    for step in recipe.get("step", []):
        if step.get("output") == output:
            return step
    return None


def stamp() -> str:
    """UTC time of recording, `YYYY-MM-DDTHH:MM:SSZ` (spec/record.md)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ledger_add(d: str, entry: dict) -> None:
    """Append one JSON entry to a claim's cost ledger."""
    path = os.path.join(d, LEDGER)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def trace_append(d: str, entry: dict) -> None:
    """Append one JSON entry to a claim's provenance trace -- residue, never identity."""
    path = os.path.join(d, STORE, "trace.jsonl")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def locked_append(path: str, line: str) -> None:
    """Append one line to `path`, serialized with an advisory file lock
    where the host provides one."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    text = line if line.endswith("\n") else line + "\n"
    try:
        import fcntl
    except ImportError:
        with open(path, "a", encoding="utf-8") as f:
            f.write(text)
        return
    with open(path, "a", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.write(text)
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
