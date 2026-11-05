"""Small helpers the layers share, so that NO LAYER IMPORTS A KERNEL PRIVATE.

This module exists because of a measured failure. The layers above the
kernel had been reaching for `kernel._safe`, `kernel._hf`, `kernel._atomic`
-- names the kernel's own acceptance check does not pin. A conforming kernel
is free to spell its internals any way it likes, so the blind rebuild
produced one that satisfied every pinned behavior and broke every layer
above it at import. The rule that replaced that habit: a layer may use only
the kernel's PINNED surface, and whatever else it needs lives here, beside
the kernel rather than inside it.

The values below are the on-disk vocabulary as the layers above speak it.
`RECIPE` is the LEGACY name on purpose: this constant is what an older
consumer of this module was given, and changing it would move a seam
nothing gains from moving. Read `kernel.RECIPE` for the canonical name.
"""
import hashlib
import json
import os
import time

STORE = ".reticuli"
LEDGER = ".reticuli/ledger.jsonl"
RECIPE = "claim.toml"


def hash_bytes(data) -> str:
    """The sha256 of some bytes, hex. The same digest the root is built on."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def hash_file(path: str) -> str:
    with open(path, "rb") as handle:
        return hash_bytes(handle.read())


def safe_path(base: str, declared: str) -> str:
    """Resolve a declared name inside a directory, or refuse.

    The layers' own copy of the path boundary: no absolute name, no `..`, no
    symlink component, nothing outside `base`.
    """
    if not isinstance(declared, str) or not declared or \
            os.path.isabs(declared):
        raise ValueError(f"unsafe path: {declared!r}")
    parts = declared.replace("\\", "/").split("/")
    if any(part == ".." for part in parts):
        raise ValueError(f"unsafe path: {declared!r}")
    root = os.path.realpath(base)
    here = root
    for part in parts:
        if part in ("", "."):
            continue
        here = os.path.join(here, part)
        if os.path.islink(here):
            raise ValueError(f"unsafe path (symlink): {declared!r}")
    resolved = os.path.normpath(here)
    if resolved != root and not resolved.startswith(root + os.sep):
        raise ValueError(f"unsafe path: {declared!r}")
    return resolved


def copy_into(source: str, destination: str) -> None:
    """Copy one file, making the parent as needed, mode and all."""
    import shutil
    os.makedirs(os.path.dirname(os.path.abspath(destination)), exist_ok=True)
    shutil.copyfile(source, destination)
    shutil.copymode(source, destination)


def read_json(path: str, default=None):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return default


def write_json(path: str, payload) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    temporary = path + ".writing"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, sort_keys=True)
        handle.write("\n")
    os.replace(temporary, path)


def stamp() -> str:
    """UTC, always: a recorded time must not depend on the host's zone."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def locked_append(path: str, line: str) -> None:
    """Append one line, atomically enough for concurrent writers.

    A single `write` of a short line under O_APPEND is not interleaved by
    any filesystem this tool supports, which is all the ordering a ledger
    of independent events needs.
    """
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(handle, (line.rstrip("\n") + "\n").encode("utf-8"))
    finally:
        os.close(handle)


def ledger_add(claim: str, event: dict) -> None:
    """One event onto a claim's ledger. Residue: outside every root."""
    payload = dict(event)
    payload.setdefault("when", stamp())
    locked_append(os.path.join(claim, LEDGER),
                  json.dumps(payload, sort_keys=True))


def trace_append(path: str, event: dict) -> None:
    """One event onto a session's trace."""
    locked_append(path, json.dumps(event, sort_keys=True))


def declared_inputs(parsed: dict) -> list:
    """Every path a recipe declares as a pinned input, as written."""
    table = (parsed or {}).get("claim") or {}
    found = list(table.get("inputs") or [])
    if table.get("environment"):
        found.append(table["environment"])
    if table.get("inputs_manifest"):
        found.append(table["inputs_manifest"])
    ordered, seen = [], set()
    for path in found:
        if path not in seen:
            seen.add(path)
            ordered.append(path)
    return ordered


def step_output(step: dict):
    """A step's output name, whatever else the step carries."""
    return (step or {}).get("output")
