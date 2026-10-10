"""Brief advice about whether a session has enough evidence to author."""
import json
import os

from . import kernel


def advise(directory):
    path = os.path.join(directory, ".reticuli", "draft.jsonl")
    try:
        with open(path, encoding="utf-8") as stream:
            events = [json.loads(line) for line in stream if line.strip()]
    except (OSError, ValueError):
        events = []
    gates = [e for e in events if e.get("event") == "bash" and e.get("cmd")]
    return {"sealable": bool(gates), "events": len(events),
            "reason": "checked session" if gates else "no checked command"}
