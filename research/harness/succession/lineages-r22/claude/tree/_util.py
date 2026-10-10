"""Small helpers shared by the exchange layer: no layer imports a kernel
private, so registry/transfer/attest/record lean on this module instead of
reaching into `reticuli._kernel`.

`safe_path` is the path boundary (refuses an absolute path, a `.`/`..`
component, or a symlink crossing); `hash_bytes` is the bytes boundary (a
plain sha256, refusing anything that is not a regular, singly-linked file);
`copy_into` moves a file or directory's bytes from one place to another;
`read_json`/`write_json` round-trip JSON, the latter atomically so a reader
never observes a half-written file; `stamp` is the UTC timestamp spec/record.md
wants; `step_output` reads a step's declared output name; `ledger_add` and
`trace_append` append one JSON line to a claim's own residue logs;
`locked_append` is the shared primitive underneath both, serializing
concurrent writers with an advisory file lock where the platform has one.
"""
import datetime
import hashlib
import json
import os
import shutil
import stat
import tempfile

from . import kernel

STORE = ".reticuli"
LEDGER = ".reticuli/ledger.jsonl"
RECIPE = "claim.toml"


def safe_path(root: str, name: str) -> str:
    """Resolve a declared name under `root`, or refuse: no absolute path,
    no empty or `.`/`..` component, no symlink crossing."""
    if not isinstance(name, str) or not name:
        raise kernel.ClaimError(f"refuses an empty path: {name!r}")
    if os.path.isabs(name):
        raise kernel.ClaimError(f"refuses an absolute path: {name!r}")
    parts = name.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise kernel.ClaimError(f"path escapes the claim: {name!r}")
    resolved = os.path.realpath(root)
    for part in parts:
        resolved = os.path.join(resolved, part)
        if os.path.islink(resolved):
            raise kernel.ClaimError(f"path crosses a symlink: {name!r}")
    return resolved


def hash_bytes(path: str) -> str:
    """The bytes boundary: a plain sha256 of a file's content, refusing
    anything that is not a regular, singly-linked file."""
    st = os.lstat(path)
    if stat.S_ISLNK(st.st_mode):
        raise kernel.ClaimError(f"refuses a symlink: {path!r}")
    if not stat.S_ISREG(st.st_mode):
        raise kernel.ClaimError(f"refuses a non-regular file: {path!r}")
    if st.st_nlink != 1:
        raise kernel.ClaimError(f"refuses a hard-linked file: {path!r}")
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_into(src: str, dst: str) -> str:
    """Copy a file or directory tree's bytes from `src` to `dst`."""
    parent = os.path.dirname(dst) or "."
    os.makedirs(parent, exist_ok=True)
    if os.path.isdir(src):
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        shutil.copy2(src, dst)
    return dst


def read_json(path: str):
    """Read one JSON document, refusing malformed bytes with a reason."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as exc:
        raise kernel.ClaimError(f"malformed JSON {path!r}: {exc}") from exc


def write_json(path: str, obj) -> None:
    """Write JSON atomically: a reader never observes a half-written file."""
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp-", suffix=".json")
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


def stamp() -> str:
    """UTC time of recording, `YYYY-MM-DDTHH:MM:SSZ` (spec/record.md)."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def step_output(step: dict):
    """A recipe step's declared output name, or `None`."""
    return (step or {}).get("output")


def locked_append(path: str, text: str) -> None:
    """Append `text` to the file at `path`, serialized by an advisory file
    lock where the platform offers one -- the shared primitive underneath
    both `ledger_add` and `trace_append`."""
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        try:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        except ImportError:
            pass
        f.write(text)
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except (ImportError, NameError):
            pass


def ledger_add(d: str, entry: dict) -> None:
    """Append one JSON entry to the claim's cost ledger (`LEDGER`)."""
    locked_append(os.path.join(d, LEDGER), json.dumps(entry, sort_keys=True) + "\n")


def declared_inputs(d: str) -> list:
    """A claim's declared pinned inputs, read straight from its recipe
    (`[claim] inputs`) -- the exchange layer's own minimal reading of what
    the kernel's parsed recipe dict already carries."""
    recipe = kernel.load_recipe(d)
    return list(recipe.get("claim", {}).get("inputs", []))


def trace_append(d: str, entry: dict) -> None:
    """Append one JSON entry to the claim's trace residue, a diagnostic
    log distinct from the cost ledger."""
    path = os.path.join(d, STORE, "trace.jsonl")
    locked_append(path, json.dumps(entry, sort_keys=True) + "\n")
