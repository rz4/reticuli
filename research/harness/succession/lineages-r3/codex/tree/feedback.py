"""Lightweight advice about a session's readiness to seal."""

from __future__ import annotations

from . import authoring


def advise(ws):
    try:
        events = authoring._events(ws)
        prompts = [e for e in events if e.get("event") == "prompt"]
        gates = [e for e in events if e.get("event") == "bash" and e.get("cmd")]
        return {"sealable": bool(gates), "prompts": len(prompts), "gates": len(gates)}
    except Exception as exc:
        return {"sealable": False, "reason": str(exc)}
