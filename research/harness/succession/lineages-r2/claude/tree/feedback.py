"""feedback: sensing what's sealable (spec/layers.md).

`advise` is a heuristic, not a certification -- it reads a session's own
trace (`authoring.TRACE`) and reports whether the session LOOKS ready to
become a claim: some work happened (a `prompt`), and the session's last act
was a verifying command (a `bash` event), not a mid-edit. Cold, authoritative
certification is `authoring.build_claim`'s job; this module only decides
whether it is worth trying.

Stdlib only.
"""
import json
import os

from . import authoring


def _read_trace(ws: str) -> list:
    path = os.path.join(ws, authoring.TRACE)
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
    """Whether `ws`'s session looks sealable: some prompted work happened,
    and the trace's last event is a verifying command."""
    try:
        events = _read_trace(ws)
    except (OSError, json.JSONDecodeError) as e:
        return {"sealable": False, "reason": f"cannot read trace: {e}"}

    if not events:
        return {"sealable": False, "reason": "no session trace"}

    has_prompt = any(e.get("event") == "prompt" for e in events)
    ends_with_gate = events[-1].get("event") == "bash"

    if not has_prompt:
        return {"sealable": False, "reason": "no prompted work in the trace"}
    if not ends_with_gate:
        return {"sealable": False, "reason": "the session did not end on a verifying command"}
    return {"sealable": True, "reason": "ends with a verifying command"}
