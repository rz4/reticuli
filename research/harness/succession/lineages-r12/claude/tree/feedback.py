"""Feedback: sensing what a session is ready to seal
(`spec/layers.md`'s authoring layer).

`advise` reads a session's draft trace and re-runs its last recorded gate
command live, in place -- the lightweight question "would this seal
right now?", without copying anything or certifying a claim the way
`authoring.build_claim` does.

Stdlib only.
"""
import json
import os

from . import kernel

TRACE = ".reticuli/draft.jsonl"


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
    """Is `ws` sealable right now? Re-runs the trace's last `bash` event
    (the gate) in place and reports whether it currently passes."""
    ws = os.path.abspath(ws)
    events = _read_trace(ws)
    bash_events = [e for e in events if e.get("event") == "bash"]
    if not bash_events:
        return {"sealable": False, "reason": "no gate recorded"}
    result = kernel.run_gate(bash_events[-1]["cmd"], ws)
    return {"sealable": result["status"] == "ok", "status": result["status"]}
