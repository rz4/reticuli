"""Quick session feedback before a claim is built."""
from __future__ import annotations

import os

from . import authoring


def advise(workspace: str) -> dict:
    try:
        events = authoring._events(workspace)
    except Exception as exc:
        return {"sealable": False, "reason": str(exc)}
    commands = [e for e in events if e.get("event") == "bash" and e.get("cmd")]
    prompts = [e for e in events if e.get("event") == "prompt"]
    return {"sealable": bool(commands and prompts), "prompts": len(prompts),
            "gates": len(commands), "workspace": os.fspath(workspace)}
