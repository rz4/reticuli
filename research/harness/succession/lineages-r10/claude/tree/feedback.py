"""feedback: sensing whether a session looks ready to become a claim.

`advise` reads a session's trace (`authoring.TRACE`) and reports whether it
looks sealable: has it run a gate at all, and did that gate's own verdict
file land on disk? This is a cheap, local sense -- it never re-runs
anything and never certifies cold; only `authoring.build_claim` does that.

Stdlib only.
"""
import json
import os
import shlex

from .authoring import TRACE


def _read_trace(ws: str) -> list:
    path = os.path.join(ws, TRACE)
    if not os.path.isfile(path):
        return []
    events = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def _redirect_targets(cmd: str) -> list:
    """Shell redirect targets (`>`, `>>`) named in a command -- the
    verdict files a gate most plainly declares."""
    try:
        tokens = shlex.split(cmd)
    except ValueError:
        return []
    targets = []
    for i, tok in enumerate(tokens):
        if tok in (">", ">>") and i + 1 < len(tokens):
            targets.append(tokens[i + 1])
    return targets


def advise(ws: str) -> dict:
    """Sense whether the session at `ws` looks sealable: a trace exists,
    it ran at least one gate command, and that command's redirect target
    is present on disk."""
    events = _read_trace(ws)
    if not events:
        return {"sealable": False, "reason": "no session trace"}

    bash_cmds = [e.get("cmd") for e in events if e.get("event") == "bash" and e.get("cmd")]
    if not bash_cmds:
        return {"sealable": False, "reason": "no gate command recorded"}

    candidates = _redirect_targets(bash_cmds[-1])
    if not candidates:
        return {"sealable": False, "reason": "no verdict file named by the gate"}

    missing = [c for c in candidates if not os.path.isfile(os.path.join(ws, c))]
    if missing:
        return {"sealable": False, "reason": f"verdict file(s) not present: {missing!r}"}

    return {"sealable": True, "candidates": candidates}
