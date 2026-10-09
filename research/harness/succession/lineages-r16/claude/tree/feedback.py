"""feedback: sense what's sealable (`spec/layers.md`).

A traced session looks ready to seal once it shows at least one gate
attempt -- the one signal available from the trace alone, without
re-running anything or touching the filesystem beyond reading it.
"""
from reticuli.authoring import _read_trace


def advise(ws: str) -> dict:
    """Sense whether `ws`'s traced session looks ready to seal."""
    events = _read_trace(ws)
    bash_events = [e for e in events if e.get("event") == "bash"]
    return {"sealable": bool(bash_events), "bash_events": len(bash_events)}
