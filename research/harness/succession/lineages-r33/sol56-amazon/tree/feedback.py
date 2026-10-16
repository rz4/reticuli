"""Lightweight advice for an authoring workspace."""
from __future__ import annotations

import json
import os

TRACE = os.path.join(".reticuli", "draft.jsonl")


def _events(ws):
    path = os.path.join(os.fspath(ws), TRACE)
    result = []
    try:
        with open(path, encoding="utf-8") as stream:
            for line in stream:
                try:
                    value = json.loads(line)
                except (ValueError, TypeError):
                    continue
                if isinstance(value, dict):
                    result.append(value)
    except OSError:
        pass
    return result


def advise(ws):
    """Describe whether a traced workspace has enough evidence to seal.

    Advice is intentionally non-authoritative; authoring itself performs the
    cold gate and identity checks.
    """
    events = _events(ws)
    prompts = [e for e in events if e.get("event") == "prompt"]
    gates = [e for e in events if e.get("event") in ("bash", "gate") and
             isinstance(e.get("cmd") or e.get("run"), str)]
    writes = [e.get("path") for e in events if e.get("event") == "write" and
              isinstance(e.get("path"), str)]
    sealable = bool(gates) and any(
        os.path.isfile(os.path.join(os.fspath(ws), name))
        for name in os.listdir(ws)
        if name not in (".reticuli", "reticuli.toml", "claim.toml")
    )
    return {"sealable": sealable, "events": len(events),
            "prompts": len(prompts), "gates": len(gates), "writes": writes,
            "reason": "a gate was observed" if sealable else "no checked session observed"}


__all__ = ["advise"]
