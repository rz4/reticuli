"""feedback: sensing whether a session looks sealable (spec/layers.md).

A light heuristic, never a certification: `advise` looks at a session's
trace for a prompt and a bash command whose redirect target is a file that
exists right now, and reports that the session LOOKS ready to become a
claim. `authoring.build_claim` is the only thing that actually earns one --
cold, against the gates, not against this guess.
"""
import json
import os
import re

TRACE = ".reticuli/draft.jsonl"

_REDIRECT = re.compile(r">>?\s*([^\s&|;]+)")


def _read_trace(ws: str) -> list:
    path = os.path.join(ws, TRACE)
    if not os.path.isfile(path):
        return []
    events = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def advise(ws: str) -> dict:
    """Does `ws`'s session trace look sealable: a prompt, and a bash
    command whose redirect target is a file that exists right now?"""
    events = _read_trace(ws)
    has_prompt = any(e.get("event") == "prompt" for e in events)

    targets = set()
    for e in events:
        if e.get("event") == "bash" and isinstance(e.get("cmd"), str):
            targets.update(_REDIRECT.findall(e["cmd"]))

    present = sorted(t for t in targets if os.path.isfile(os.path.join(ws, t)))
    return {"sealable": has_prompt and bool(present), "candidates": present}
