"""Feedback: sensing what's sealable (spec/layers.md's authoring layer).

`advise` reads a workspace's draft trace and senses whether the session it
records looks like a complete, checked one -- it issued a prompt, ran a
bash command, and that command's own redirect target now exists on disk, a
candidate gate verdict. This is a heuristic for a human or an agent
deciding whether to call `authoring.build_claim`; it is never a proof --
only `build_claim`'s cold certification earns that.
"""
import json
import os
import re
import shlex

from . import authoring

_OPSPLIT = re.compile(r'\|\||&&|[;&|\n]')
_REDIRECTS = ("<", ">", ">>", "2>", "2>>", "&>")


def _trace_events(ws: str) -> list:
    path = os.path.join(ws, authoring.TRACE)
    events = []
    if not os.path.isfile(path):
        return events
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def _redirect_targets(cmd: str) -> list:
    targets = []
    for sub in _OPSPLIT.split(cmd):
        sub = sub.strip()
        if not sub:
            continue
        try:
            tokens = shlex.split(sub)
        except ValueError:
            continue
        take_next = False
        for tok in tokens:
            if take_next:
                targets.append(tok)
                take_next = False
                continue
            if tok in _REDIRECTS:
                take_next = True
    return targets


def advise(ws: str) -> dict:
    """Sense whether the traced session at `ws` looks sealable: at least
    one prompt, at least one bash command, and at least one of that
    command's own redirect targets present on disk right now."""
    events = _trace_events(ws)
    prompts = [e for e in events if e.get("event") == "prompt"]
    bash_events = [e for e in events if e.get("event") == "bash" and e.get("cmd")]

    candidates = []
    for e in bash_events:
        candidates.extend(_redirect_targets(e["cmd"]))
    present = [c for c in candidates if os.path.isfile(os.path.join(ws, c))]

    sealable = bool(prompts) and bool(bash_events) and bool(present)
    return {"sealable": sealable, "candidates": candidates, "present": present}
