"""reticuli._util -- small helpers shared by the layers above the kernel.

`spec/layers.md`: "`_util.py` sits beside the kernel: small helpers the
layers share, so that no layer imports a kernel private." The kernel's
own path-safety, hashing, JSON, and ledger primitives
(`reticuli._kernel.core`, `reticuli._kernel.run`) are not part of its
public facade (`reticuli.kernel`), so every layer above independently
needs its own small versions of them rather than reaching past the
facade into the kernel package. This module is that shared, independent
copy.
"""
import fcntl
import hashlib
import json
import os
import shutil
import tempfile
import time

from . import kernel

STORE = ".reticuli"
LEDGER = ".reticuli/ledger.jsonl"
RECIPE = "claim.toml"


def safe_path(base: str, name: str) -> str:
    """Resolve `name` to a real path inside `base`; refuse an escape."""
    if not name:
        raise kernel.ClaimError("empty name")
    if os.path.isabs(name):
        raise kernel.ClaimError(f"absolute path refused: {name!r}")
    base_real = os.path.realpath(base)
    candidate = os.path.realpath(os.path.join(base_real, name))
    if candidate != base_real and not candidate.startswith(base_real + os.sep):
        raise kernel.ClaimError(f"path escapes the claim: {name!r}")
    return candidate


def hash_bytes(data: bytes) -> str:
    """Plain sha256 of a bytes object, as a hex digest."""
    return hashlib.sha256(data).hexdigest()


def copy_into(base: str, name: str, src: str) -> str:
    """Copy the file at `src` into the claim at `name`; return the real path."""
    dest = safe_path(base, name)
    os.makedirs(os.path.dirname(dest) or base, exist_ok=True)
    shutil.copyfile(src, dest)
    return dest


def read_json(path: str):
    """Read and parse one JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str, obj) -> None:
    """Write `obj` as JSON to `path` atomically (write-tmp, then replace)."""
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def stamp(event: dict) -> dict:
    """`event` with a `when` (UTC, ISO-8601) field, unless it already has one."""
    stamped = dict(event)
    stamped.setdefault("when", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    return stamped


def locked_append(path: str, line: str) -> None:
    """Append one line to `path`, holding an exclusive advisory lock."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        except OSError:
            pass
        f.write(line)
        if not line.endswith("\n"):
            f.write("\n")


def trace_append(d: str, entry: dict) -> dict:
    """Append one stamped entry to `d`'s trace log; return the stamped entry."""
    stamped = stamp(entry)
    path = safe_path(d, STORE + "/trace.jsonl")
    locked_append(path, json.dumps(stamped, sort_keys=True))
    return stamped


def ledger_add(d: str, event: dict) -> dict:
    """Append one stamped event to `d`'s ledger; return the stamped event."""
    stamped = stamp(event)
    path = safe_path(d, LEDGER)
    locked_append(path, json.dumps(stamped, sort_keys=True))
    return stamped


def declared_inputs(d: str) -> list:
    """`d`'s claim's declared `[claim] inputs`, plus its `environment` pin
    (also automatically a pinned input) when one is declared."""
    recipe = kernel.load_recipe(d)
    claim = recipe.get("claim", {})
    inputs = list(claim.get("inputs", []))
    env_file = claim.get("environment")
    if env_file and env_file not in inputs:
        inputs.append(env_file)
    return inputs


def step_output(step: dict) -> str:
    """A step's declared output name."""
    return step.get("output")


# The kernel facade (`reticuli.kernel`) does not itself expose a ledger
# writer -- only the internal layers below it do. Callers above the
# kernel reach one through the kernel facade all the same, so it is
# attached here, once, the first time this module (which every exchange
# module imports) loads.
if not hasattr(kernel, "ledger"):
    kernel.ledger = ledger_add
