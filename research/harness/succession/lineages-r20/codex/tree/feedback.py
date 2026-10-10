"""Advisory view of a draft session."""

import json
import os

TRACE = ".reticuli/draft.jsonl"


def advise(workspace):
    path = os.path.join(workspace, TRACE)
    events = []
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as stream:
            for line in stream:
                if line.strip():
                    try:
                        events.append(json.loads(line))
                    except ValueError:
                        pass
    gates = [event.get("cmd") for event in events if event.get("event") == "bash" and event.get("cmd")]
    return {"sealable": bool(gates), "gates": gates, "events": len(events)}
