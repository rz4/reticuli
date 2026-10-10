"""Report whether a traced session has enough evidence to be sealed."""

import os

from . import authoring


def advise(ws):
    try:
        events = authoring._events(ws)
    except Exception as exc:
        return {"sealable": False, "reason": str(exc)}
    has_gate = any(event.get("event") == "bash" for event in events)
    has_prompt = any(event.get("event") == "prompt" for event in events)
    return {"sealable": has_gate and has_prompt,
            "trace": os.path.join(ws, authoring.TRACE),
            "events": len(events)}
