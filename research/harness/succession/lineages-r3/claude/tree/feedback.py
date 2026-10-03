"""Feedback: sensing what's sealable (spec/layers.md, "authoring";
v1: `pilot`).

`advise` is a cheap heuristic over a session's trace: it looks at what a
traced bash command claims to leave behind (a shell redirect target) and
checks whether that file is actually sitting on disk right now, under
its own exact name (spec/identity.md, "Identity must not depend on the
host filesystem" -- no case-folded `os.path.isfile`). It never re-runs
anything and never raises -- a session with nothing to sense yet is
simply not sealable. Deciding whether a draft actually forms a sound
claim (vacuous gates refused, every verdict re-earned cold) is
`authoring.build_claim`'s job, not this one's.
"""
import json
import os

from reticuli import kernel

TRACE = f"{kernel.STORE}/draft.jsonl"


def _read_trace(ws: str) -> list:
    path = os.path.join(ws, *TRACE.split("/"))
    if not os.path.isfile(path):
        return []
    events = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def _existing_names(ws: str) -> set:
    names = set()
    for root, dirs, files in os.walk(ws):
        dirs[:] = [d for d in dirs if d != kernel.STORE]
        for fname in files:
            rel = os.path.relpath(os.path.join(root, fname), ws).replace(os.sep, "/")
            names.add(rel)
    return names


def _redirect_targets(cmd: str) -> list:
    """Every token immediately following a bare `>` or `>>` in `cmd` --
    the output-file half of a shell redirect, the cheapest signal a
    traced command names a file it expects to leave behind.
    """
    tokens = cmd.split()
    return [tokens[i + 1] for i, tok in enumerate(tokens)
            if tok in (">", ">>") and i + 1 < len(tokens)]


def advise(ws: str) -> dict:
    """Sense whether `ws`'s traced session looks ready to become a
    claim: at least one bash event whose redirect target currently
    exists on disk, under its own exact name.
    """
    existing = _existing_names(ws)
    reasons = []
    for event in _read_trace(ws):
        if event.get("event") != "bash":
            continue
        cmd = event.get("cmd")
        if not isinstance(cmd, str):
            continue
        for target in _redirect_targets(cmd):
            if target in existing:
                reasons.append(f"{cmd!r} left {target!r} on disk")
    return {"sealable": bool(reasons), "reasons": reasons}
