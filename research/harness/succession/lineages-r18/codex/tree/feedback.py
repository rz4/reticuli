"""Read a session trace and report whether it has a checked verdict."""
import json
import os

from .authoring import TRACE


def advise(workspace):
    path = os.path.join(workspace, TRACE)
    try:
        with open(path, encoding="utf-8") as stream:
            events = [json.loads(line) for line in stream if line.strip()]
    except (OSError, ValueError):
        events = []
    gates = [event for event in events if event.get("event") == "bash" and event.get("cmd")]
    return {"sealable": bool(gates), "events": len(events), "gates": len(gates)}
