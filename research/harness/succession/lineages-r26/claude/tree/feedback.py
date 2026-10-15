"""Sensing whether a session looks ready to seal.

`advise` is a light heuristic over a session's trace, not a verdict: it
looks for a gate that has actually run and left a verdict file on disk, the
same signal a human watching the session would notice. The authoritative
answer is always `authoring.build_claim` actually succeeding.

Stdlib only.
"""
import os
import re

from . import authoring

_REDIRECT_RE = re.compile(r">>?\s*([^\s|&;]+)")


def _redirect_targets(cmd: str) -> list:
    return [m.group(1).strip("'\"") for m in _REDIRECT_RE.finditer(cmd)]


def advise(ws: str) -> dict:
    """Does this session look sealable right now?"""
    events = authoring._read_trace(ws)
    bash_events = [e for e in events if e.get("event") == "bash" and "cmd" in e]
    if not bash_events:
        return {"sealable": False, "reason": "no gate has run in this session"}

    candidates = []
    for e in bash_events:
        candidates.extend(_redirect_targets(e["cmd"]))

    existing = sorted({c for c in candidates if os.path.isfile(os.path.join(ws, c))})
    if not existing:
        return {"sealable": False, "reason": "no verdict file found on disk"}

    return {"sealable": True, "candidates": existing}
