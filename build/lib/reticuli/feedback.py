"""The feedback loop: in a draft session, what's sealable and what to fix.

Reads the trace, classifies each file (pinned input vs generated output vs gate
output), and nudges: an uncovered generated output needs a gate; once every
output is checked, the session is sealable. Read-only.
"""
from __future__ import annotations

import os

from . import authoring as A


def _present(session: str) -> list[str]:
    out = []
    for base, dirs, files in os.walk(session):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d != "__pycache__")
        for f in sorted(files):
            rel = os.path.relpath(os.path.join(base, f), session).replace(os.sep, "/")
            if not rel.startswith(".") and not rel.endswith((".pyc", ".pyo")):
                out.append(rel)
    return out


def advise(session: str) -> dict:
    session = os.path.abspath(session)
    ev = A._events(session)
    writes = {e["path"] for e in ev if e.get("event") == "write" and e.get("path")}
    reads = {e["path"] for e in ev if e.get("event") == "read" and e.get("path")}
    bashes = [e["cmd"] for e in ev if e.get("event") == "bash" and e.get("cmd")]

    gate_of: dict[str, str] = {}
    for f in _present(session):
        for cmd in bashes:
            if A._writes(cmd, f):
                gate_of.setdefault(f, cmd)
                break

    files = []
    for f in _present(session):
        base = os.path.basename(f)
        if f in gate_of:
            files.append({"path": f, "role": "generated", "kind": "gate", "covered": True})
        elif f in writes:
            covered = any(base in c for c in gate_of.values())
            files.append({"path": f, "role": "generated", "kind": "produced", "covered": covered})
        elif f in reads:
            files.append({"path": f, "role": "pinned", "kind": "input", "covered": True})
        else:
            files.append({"path": f, "role": "pinned", "kind": "present", "covered": True})

    uncovered = sorted(x["path"] for x in files if x["kind"] == "produced" and not x["covered"])
    gates = sorted(gate_of)
    sealable = bool(gates) and not uncovered
    if uncovered:
        nudge = ("add a gate that writes an output and names "
                 + ", ".join(os.path.basename(u) for u in uncovered))
    elif sealable:
        nudge = f"sealable — `ret seal --accept {os.path.basename(gates[-1])} --into <claim>`"
    else:
        nudge = "run a check with `ret run` to author a gate"

    return {"phase": "draft", "session": session, "files": files,
            "uncovered": uncovered, "gates": gates, "sealable": sealable,
            "nudge": nudge, "trace_events": len(ev)}
