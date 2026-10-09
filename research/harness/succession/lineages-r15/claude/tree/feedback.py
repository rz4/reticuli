"""feedback: sensing whether a session looks ready to become a claim
(`spec/layers.md`). A cheap, warm heuristic over the session's trace -- has
a gate run, and does its command still exit clean right now? The only
authority over whether a session actually seals is
`authoring.build_claim`'s cold, sandboxed re-earning; this module exists to
tell a session along before that more expensive step, not to replace it.

Stdlib only.
"""
import json
import os

from reticuli import kernel
from reticuli.authoring import TRACE


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


def advise(ws: str) -> dict:
    """Is session `ws` worth trying to seal? `sealable` is true when at
    least one gate ran in this session's trace and its command still
    exits clean here, right now.
    """
    events = _read_trace(ws)
    gates = [e["cmd"] for e in events if e.get("event") == "bash" and e.get("cmd")]
    if not gates:
        return {"sealable": False, "reason": "no gate has run in this session"}

    ok = True
    for cmd in gates:
        result = kernel.run_gate(cmd, ws)
        if result["status"] != "ok":
            ok = False
    return {"sealable": ok, "gates": len(gates)}
