"""_util: small helpers the layers above the kernel share.

Deliberately dependency-free of the kernel -- even its public surface --
so that no layer above ever reaches past this module for a primitive it
also names (`spec/layers.md`). Stdlib only.
"""
import datetime
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import PurePosixPath

STORE = ".reticuli"
LEDGER = ".reticuli/ledger.jsonl"
RECIPE = "claim.toml"

TRACE = ".reticuli/trace.jsonl"


def safe_path(base: str, name: str) -> str:
    """Resolve a declared name under `base`, refusing any escape: an
    empty or absolute name, any `..` component, or any component that is
    a symlink -- even one whose target stays inside `base`."""
    if not isinstance(name, str) or not name:
        raise ValueError(f"refusing an empty path: {name!r}")
    if os.path.isabs(name):
        raise ValueError(f"refusing an absolute path: {name!r}")
    parts = PurePosixPath(name).parts
    if not parts or any(p in ("..", ".") for p in parts):
        raise ValueError(f"refusing {name!r}")
    base_real = os.path.realpath(base)
    cur = base_real
    for part in parts:
        cur = os.path.join(cur, part)
        if os.path.islink(cur):
            raise ValueError(f"refusing a symlink component in {name!r}")
    if cur != base_real and not cur.startswith(base_real + os.sep):
        raise ValueError(f"{name!r} escapes the base")
    return cur


def hash_bytes(path: str) -> str:
    """sha256 hex of a file's bytes."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str, obj) -> None:
    """Write JSON atomically: build the bytes off to the side, then
    rename into place, so a reader never observes a partial write."""
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, sort_keys=True, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def copy_into(src: str, dst: str, names=None) -> str:
    """Copy named entries from `src` into `dst`, resolving every name
    through the path boundary on both sides. With `names` omitted,
    copies every top-level entry of `src`."""
    os.makedirs(dst, exist_ok=True)
    src_real = os.path.realpath(src)
    if names is None:
        names = sorted(os.listdir(src_real))
    for name in names:
        s = safe_path(src_real, name)
        d = safe_path(dst, name)
        parent = os.path.dirname(d) or dst
        os.makedirs(parent, exist_ok=True)
        if os.path.isdir(s):
            shutil.copytree(s, d, dirs_exist_ok=True)
        else:
            shutil.copy2(s, d)
    return dst


def declared_inputs(parsed: dict, d: str) -> list:
    """A recipe's pinned input paths: `[claim] inputs`, or the contents
    of `[claim] inputs_manifest` when that is declared instead."""
    claim = parsed.get("claim") or {}
    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        path = safe_path(d, manifest)
        paths = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                paths.append(parts[-1] if len(parts) > 1 else parts[0])
        return paths
    inputs = claim.get("inputs", [])
    return list(inputs)


def step_output(step: dict):
    return step.get("output")


def stamp() -> str:
    """UTC time, `YYYY-MM-DDTHH:MM:SSZ`."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def locked_append(path: str, line: str) -> None:
    """Append one line to `path`, holding an exclusive lock for the
    duration where the platform provides one."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        try:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        except ImportError:
            pass
        f.write(line.rstrip("\n") + "\n")


def ledger_add(d: str, event: dict) -> None:
    locked_append(os.path.join(d, LEDGER), json.dumps(event, sort_keys=True))


def trace_append(d: str, entry: dict) -> None:
    """Append one residue entry to the claim's trace log -- provenance
    the exchange layer keeps about itself, never consulted by identity."""
    locked_append(os.path.join(d, TRACE), json.dumps(entry, sort_keys=True))
