"""Small helpers the layers share, so that no layer imports a kernel private.

This module exists because of the blind rebuild. Layers above the kernel were
reaching for `kernel._safe`, `kernel._hash_file`, `kernel._write_json` -- names
`spec/kernel-api.md` pins only as a courtesy to the kernel's own suite. A
regrown kernel is free to spell its privates differently, and three of them
did, so an assembled tool would not import. The public spellings live here;
the kernel is consumed only through the pinned surface.
"""
import fcntl
import hashlib
import json
import os
import shutil
import time

#: On-disk vocabulary, in the spellings the layers above use. RECIPE keeps the
#: legacy name because a reader accepts either and older claims carry it.
STORE = ".reticuli"
LEDGER = ".reticuli/ledger.jsonl"
RECIPE = "claim.toml"
TRACE = ".reticuli/draft.jsonl"


def hash_bytes(data) -> str:
    """Lowercase hex sha256 of bytes, or of a str encoded UTF-8."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def safe_path(base: str, name: str) -> str:
    """A declared name resolved inside `base`, or None if it escapes.

    The kernel owns the refusing version; this one answers the question
    without raising, for the places that are deciding rather than enforcing.
    """
    if not isinstance(name, str) or not name or os.path.isabs(name):
        return None
    parts = [p for p in name.replace("\\", "/").split("/")
             if p not in ("", ".")]
    if not parts or any(p == ".." for p in parts):
        return None
    root = os.path.realpath(base)
    here = root
    for part in parts:
        here = os.path.join(here, part)
        if os.path.islink(here):
            return None
    resolved = os.path.normpath(here)
    if resolved != root and not resolved.startswith(root + os.sep):
        return None
    return resolved


def read_json(path: str, default=None):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError, UnicodeDecodeError):
        return default


def write_json(path: str, document) -> None:
    parent = os.path.dirname(path) or "."
    os.makedirs(parent, exist_ok=True)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(document, handle, sort_keys=True)
        handle.write("\n")
    os.replace(temporary, path)


def copy_into(source: str, target: str) -> None:
    parent = os.path.dirname(target)
    if parent:
        os.makedirs(parent, exist_ok=True)
    shutil.copyfile(source, target)
    try:
        shutil.copymode(source, target)
    except OSError:
        pass


def locked_append(path: str, line: str) -> None:
    """Append one line under an advisory lock: concurrent hooks interleave."""
    parent = os.path.dirname(path) or "."
    os.makedirs(parent, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        except OSError:
            pass
        handle.write(line if line.endswith("\n") else line + "\n")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass


def stamp(event: dict) -> dict:
    """A trace or ledger event, with a wall-clock mark if it has none."""
    marked = dict(event)
    marked.setdefault("ts", time.time())
    return marked


def trace_append(workspace: str, event: dict) -> dict:
    """Remember one session event. The trace is residue, never identity."""
    marked = stamp(event)
    locked_append(os.path.join(workspace, TRACE),
                  json.dumps(marked, sort_keys=True))
    return marked


def ledger_add(claim: str, event: dict) -> dict:
    """Append one cost/verdict event to a claim's ledger."""
    marked = dict(event)
    locked_append(os.path.join(claim, LEDGER),
                  json.dumps(marked, sort_keys=True))
    return marked


def declared_inputs(parsed: dict) -> list:
    """`[claim] inputs` as written -- the list, not the wider pinned set."""
    return list((parsed.get("claim") or {}).get("inputs") or [])


def step_output(step: dict):
    """The path a step pins, or None for a step that pins nothing."""
    output = step.get("output") if isinstance(step, dict) else None
    return output if isinstance(output, str) and output else None
