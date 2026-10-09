"""Feedback: sense what's sealable, without certifying anything (`spec/layers.md`).

`advise(ws)` (v1: `pilot`) looks at a session's trace and probes its last
gate command COLD, through `kernel.run_gate` -- the same scrub, sandbox,
and wall-clock bound a real seal would give it -- so a positive advisory
is never a guess about what the gate will do. It certifies nothing and
writes nothing: `authoring.build_claim` is the layer that seals.

Stdlib only.
"""
import json
import os

from reticuli import kernel

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
    """Whether `ws`'s session looks sealable right now: a prompt happened,
    a gate was run, and that gate still exits clean on the bytes present."""
    events = _read_trace(ws)
    has_prompt = any(e.get("event") == "prompt" for e in events)
    bash_events = [e for e in events if e.get("event") == "bash" and e.get("cmd")]
    if not has_prompt or not bash_events:
        return {"sealable": False, "reason": "no prompt-and-gate pair in the trace"}

    cmd = bash_events[-1]["cmd"]
    try:
        result = kernel.run_gate(cmd, ws, None)
    except Exception as e:
        return {"sealable": False, "reason": f"gate probe failed: {e}"}

    sealable = result["status"] == "ok"
    out = {"sealable": sealable}
    if not sealable:
        out["reason"] = f"gate probe status: {result['status']}"
    return out
