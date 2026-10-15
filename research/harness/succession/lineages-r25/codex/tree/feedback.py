"""Lightweight advice about a recorded authoring session."""

import json
import os

from .authoring import TRACE


def advise(directory):
    path = os.path.join(directory, TRACE)
    try:
        with open(path, encoding="utf-8") as stream:
            events = [json.loads(line) for line in stream if line.strip()]
    except (OSError, ValueError):
        events = []
    return {"sealable": any(e.get("event") == "bash" for e in events),
            "events": len(events)}
