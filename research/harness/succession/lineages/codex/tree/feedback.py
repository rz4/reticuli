"""Session feedback for a prospective claim."""

from __future__ import annotations

import os

from . import authoring, kernel


def advise(ws):
    try:
        events = authoring._events(ws)
        gates = [event for event in events if event.get("event") == "bash" and event.get("cmd")]
        return {"sealable": bool(gates), "gates": len(gates),
                "prompts": sum(event.get("event") == "prompt" for event in events)}
    except (kernel.ClaimError, OSError):
        return {"sealable": False, "gates": 0, "prompts": 0}
