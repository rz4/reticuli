"""_util: small helpers shared by the exchange layer (registry, transfer,
attest, record).

No layer imports a kernel private (spec/layers.md): the exchange layer gets
its own store/ledger/path primitives here instead of reaching into
reticuli._kernel. Stdlib only.
"""
import datetime
import fcntl
import hashlib
import json
import os
import shutil

STORE = ".reticuli"
LEDGER = ".reticuli/ledger.jsonl"
RECIPE = "claim.toml"


def hash_bytes(data: bytes) -> str:
    """The sha256 hex digest of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def safe_path(base: str, name: str) -> str:
    """A declared name resolved under `base`; refuses escapes (spec/identity.md)."""
    if not isinstance(name, str) or name == "" or os.path.isabs(name):
        raise ValueError(f"refused path: {name!r}")
    parts = name.split("/")
    if any(p in ("", ".", "..") for p in parts):
        raise ValueError(f"refused path: {name!r}")
    base_real = os.path.realpath(base)
    resolved = os.path.realpath(os.path.join(base_real, name))
    if resolved != base_real and not resolved.startswith(base_real + os.sep):
        raise ValueError(f"refused path escaping base: {name!r}")
    return resolved


def copy_into(src: str, dst: str) -> None:
    """Copy a file or directory tree at `src` to `dst`, stdlib only."""
    parent = os.path.dirname(dst)
    if parent:
        os.makedirs(parent, exist_ok=True)
    if os.path.isdir(src) and not os.path.islink(src):
        shutil.copytree(src, dst, symlinks=False, dirs_exist_ok=True)
    else:
        shutil.copy2(src, dst)


def read_json(path: str):
    """Parsed JSON from `path`."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str, obj) -> None:
    """Write `obj` as JSON to `path`, atomically."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, sort_keys=True, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def stamp() -> str:
    """UTC time of recording, `YYYY-MM-DDTHH:MM:SSZ`."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def locked_append(path: str, line: str) -> None:
    """Append one line to `path`, serialized against concurrent writers."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.write(line)
            if not line.endswith("\n"):
                f.write("\n")
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def trace_append(d: str, entry: dict) -> dict:
    """Append one event to a claim's residue trace (`.reticuli/trace.jsonl`)."""
    rec = dict(entry)
    rec.setdefault("when", stamp())
    locked_append(os.path.join(d, STORE, "trace.jsonl"), json.dumps(rec, sort_keys=True))
    return rec


def ledger_add(d: str, entry: dict) -> dict:
    """Append one event to a claim's ledger (the same relative path the
    kernel's own production-cost ledger uses)."""
    rec = dict(entry)
    rec.setdefault("when", stamp())
    locked_append(os.path.join(d, LEDGER), json.dumps(rec, sort_keys=True))
    return rec


def declared_inputs(parsed: dict) -> list:
    """Every pinned input path a parsed recipe declares (`[claim] inputs`)."""
    return list(parsed.get("claim", {}).get("inputs", []) or [])


def step_output(parsed: dict, output: str):
    """The step dict in a parsed recipe whose `output` matches, or `None`."""
    for step in parsed.get("step", []) or []:
        if step.get("output") == output:
            return step
    return None
