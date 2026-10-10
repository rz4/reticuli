"""Summarize whether a traced workspace is ready to be sealed."""

from __future__ import annotations

import os

from . import authoring, kernel


def advise(workspace):
    try:
        events = authoring._events(workspace)
        commands = [event["cmd"] for event in events
                    if event.get("event") == "bash" and isinstance(event.get("cmd"), str)]
        if not commands:
            return {"sealable": False, "reason": "no gate in session"}
        # A gate has to have run in the trace; the authoring step will certify
        # its result in a fresh room before actually sealing.
        return {"sealable": True, "gate": commands[-1]}
    except kernel.ClaimError as exc:
        return {"sealable": False, "reason": str(exc)}
