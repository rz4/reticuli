"""feedback: sensing what's sealable in a working session (spec/layers.md
"authoring"; v1: `pilot`).

A session's trace (`.reticuli/draft.jsonl`) is residue, not a claim -- this
module reads it and reports whether there is enough recorded (a prompt, and
a gate command run) for `authoring.build_claim` to have something to
certify. It never seals anything itself.
"""
import json
import os

TRACE = ".reticuli/draft.jsonl"


def _read_trace(ws: str) -> list:
    path = os.path.join(ws, TRACE)
    if not os.path.isfile(path):
        return []
    events = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def advise(ws: str) -> dict:
    """Whether `ws` looks sealable: a recorded trace carrying at least one
    prompt and at least one gate (bash) event to certify."""
    events = _read_trace(ws)
    prompts = sum(1 for e in events if e.get("event") == "prompt")
    gates = sum(1 for e in events if e.get("event") == "bash")
    sealable = bool(events) and prompts > 0 and gates > 0
    return {"sealable": sealable, "events": len(events),
            "prompts": prompts, "gates": gates}
