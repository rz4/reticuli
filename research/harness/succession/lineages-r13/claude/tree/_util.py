"""Small helpers shared by the layers above the kernel (spec/layers.md):
`_util.py` sits beside the kernel so that no layer imports a kernel
private. Nothing here is identity-bearing; it is plain filesystem and
bookkeeping plumbing that `registry.py`, `transfer.py`, `attest.py`, and
`record.py` are free to use or bypass in favor of the kernel facade.
"""
import hashlib
import json
import os
import shutil
import tempfile
import time

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX host
    fcntl = None

STORE = ".reticuli"
LEDGER = ".reticuli/ledger.jsonl"
RECIPE = "claim.toml"


def safe_path(base: str, name: str) -> str:
    """The path boundary: a name inside `base` resolves; an escape refuses."""
    if not name or not isinstance(name, str):
        raise ValueError(f"refuses an empty or non-string path: {name!r}")
    if os.path.isabs(name) or "\x00" in name:
        raise ValueError(f"refuses an absolute path: {name!r}")
    parts = name.replace("\\", "/").split("/")
    if any(p in ("", "..", ".") for p in parts):
        raise ValueError(f"refuses a path that escapes the claim: {name!r}")

    base_real = os.path.realpath(base)
    cur = base_real
    for part in parts:
        candidate = os.path.join(cur, part)
        if os.path.islink(candidate):
            raise ValueError(f"refuses a symlink component: {name!r}")
        cur = candidate

    resolved = os.path.normpath(os.path.join(base_real, *parts))
    if resolved != base_real and not resolved.startswith(base_real + os.sep):
        raise ValueError(f"refuses a path that escapes the claim: {name!r}")
    return resolved


def hash_bytes(path: str) -> str:
    """A plain sha256 of a file's bytes."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_into(src: str, dst: str) -> None:
    """Materialize one path's bytes, directories included."""
    if os.path.isdir(src):
        shutil.copytree(src, dst, symlinks=False, dirs_exist_ok=True)
    else:
        os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
        shutil.copyfile(src, dst)


def read_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str, obj) -> None:
    """Atomic JSON write: write to a scratch file, then replace."""
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, sort_keys=True)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def stamp() -> str:
    """UTC time of recording, YYYY-MM-DDTHH:MM:SSZ."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def step_output(step: dict) -> str:
    return step.get("output")


def declared_inputs(recipe: dict, d: str = None) -> list:
    """A recipe's pinned input paths: an explicit `inputs` list, or every
    entry named by `inputs_manifest`."""
    claim = (recipe or {}).get("claim", {}) or {}
    manifest_name = claim.get("inputs_manifest")
    if manifest_name:
        entries = [manifest_name]
        if d is not None:
            path = os.path.join(d, manifest_name)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    text = f.read()
            except OSError:
                return entries
            for line in text.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                head, _, rest = line.partition(" ")
                rest = rest.strip()
                if rest and len(head) == 64 and all(c in "0123456789abcdef" for c in head):
                    entries.append(rest)
                else:
                    entries.append(line)
        return entries
    return list(claim.get("inputs", []) or [])


def locked_append(path: str, line: str) -> None:
    """Append one line to `path`, serialized across processes where the
    host supports advisory locks."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        if fcntl is not None:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            except OSError:
                pass
        f.write(line)
        if not line.endswith("\n"):
            f.write("\n")
        if fcntl is not None:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass


def trace_append(path: str, entry: dict) -> None:
    """Append one JSON record as a line to a trace/ledger-shaped file."""
    locked_append(path, json.dumps(entry, sort_keys=True))


def ledger_add(d: str, entry: dict) -> None:
    """Append one ledger entry under `d`'s store: what a run cost."""
    record = dict(entry)
    record.setdefault("when", stamp())
    trace_append(os.path.join(d, LEDGER), record)
