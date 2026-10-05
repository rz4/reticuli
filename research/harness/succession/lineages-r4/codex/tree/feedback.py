"""Lightweight advice about a session's readiness to seal."""

import os

from .authoring import _events


def advise(ws):
    events = _events(ws)
    prompts = sum(event.get("event") == "prompt" for event in events)
    gates = [event.get("cmd") for event in events
             if event.get("event") == "bash" and event.get("cmd")]
    return {"sealable": bool(gates), "prompts": prompts,
            "gate": gates[-1] if gates else None,
            "trace": os.path.join(ws, ".reticuli", "draft.jsonl")}
