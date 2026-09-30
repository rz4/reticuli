"""Lightweight advice about whether a traced workspace can be sealed."""
from __future__ import annotations

import os

from . import authoring


def advise(ws):
    try:
        events = authoring._events(ws)
        prompts = [event for event in events if event.get("event") == "prompt"]
        gates = [event for event in events if event.get("event") == "bash" and event.get("cmd")]
        return {"sealable": bool(gates), "prompts": len(prompts),
                "gate": gates[-1]["cmd"] if gates else None}
    except Exception as exc:
        return {"sealable": False, "reason": str(exc)}
