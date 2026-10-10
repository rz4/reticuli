"""Propose claims from a session trace and certify them from pinned bytes."""

import json
import os
import shlex
import shutil

from . import kernel, render
from ._util import safe_path, copy_into

TRACE = ".reticuli/draft.jsonl"


def _events(ws):
    try:
        with open(os.path.join(ws, TRACE), encoding="utf-8") as stream:
            return [json.loads(line) for line in stream if line.strip()]
    except (OSError, ValueError) as exc:
        raise kernel.ClaimError(f"cannot read session trace: {exc}") from exc


def _present_names(ws):
    names = set()
    for base, folders, files in os.walk(ws):
        folders[:] = [x for x in folders if x != kernel.STORE]
        for filename in files:
            names.add(os.path.relpath(os.path.join(base, filename), ws).replace(os.sep, "/"))
    return names


def _declared(ws, events, verdicts, claim, generated):
    present = _present_names(ws)
    writes = set()
    reads = set()
    commands = []
    for event in events:
        kind = event.get("event")
        if kind in ("read", "write") and isinstance(event.get("path"), str):
            path = event["path"]
            safe_path(ws, path)  # Refuse trace escapes before any copy.
            (reads if kind == "read" else writes).add(path)
        elif kind == "bash" and isinstance(event.get("cmd"), str):
            commands.append(event["cmd"])
    if not commands:
        raise kernel.ClaimError("session has no gate command")
    for path in list(verdicts) + list(claim or []) + list(generated or []):
        safe_path(ws, path)
    made = (writes | set(generated or [])) - set(claim or []) - set(verdicts)
    inputs = reads | set(claim or [])
    for command in commands:
        try:
            tokens = shlex.split(command)
        except ValueError as exc:
            raise kernel.ClaimError(f"invalid shell command: {exc}") from exc
        for token in tokens:
            if token.startswith("./"):
                token = token[2:]
            # Membership tests an actual directory entry, preserving case on
            # case-insensitive hosts as well as on case-sensitive ones.
            if token in present and token not in made and token not in verdicts:
                inputs.add(token)
    inputs -= made | set(verdicts)
    if not inputs <= present or not made <= present or not set(verdicts) <= present:
        raise kernel.ClaimError("declared file is absent from session")
    return sorted(inputs), sorted(made), commands[-1]


def propose(ws, outputs, name, *, claim=None, generated=None):
    events = _events(ws)
    inputs, made, command = _declared(ws, events, outputs, claim, generated)
    parsed = {"claim": {"name": name, "format": 3, "inputs": inputs},
              "step": [{"kind": "produce", "output": path,
                        "class": "generated", "guidance": f"regenerate {path} to pass the gate"}
                       for path in made] +
                      [{"kind": "gate", "output": path, "class": "validated",
                        "run": command} for path in outputs]}
    return parsed


def build_claim(ws, outputs, into, *, name=None, claim=None, generated=None):
    ws = os.path.realpath(ws)
    parsed = propose(ws, outputs, name or os.path.basename(into),
                     claim=claim, generated=generated)
    if kernel.vacuous_gates(parsed):
        raise kernel.ClaimError("vacuous gate: every decider is generated")
    if os.path.exists(into):
        if os.listdir(into):
            raise kernel.ClaimError("destination is not empty")
    else:
        os.makedirs(into)
    try:
        with open(os.path.join(into, kernel.RECIPE), "w", encoding="utf-8") as stream:
            stream.write(render.dump_recipe(parsed))
        names = set(parsed["claim"]["inputs"]) | {step["output"] for step in parsed["step"]}
        for path in names:
            copy_into(safe_path(ws, path), safe_path(into, path))
        sealed = kernel.seal(into)
        audited = kernel.audit(into)
        if not audited["ok"]:
            raise kernel.ClaimError("cold gate did not reproduce its pinned verdict")
        events = _events(ws)
        prompts = sum(event.get("event") == "prompt" for event in events)
        times = [event["ts"] for event in events if isinstance(event.get("ts"), (int, float))]
        elapsed = max(times) - min(times) if len(times) >= 2 else 0.0
        kernel.ledger(into, {"event": "oracle", "calls": prompts, "seconds": elapsed})
        return {"ok": True, "root": sealed["root"], "path": into}
    except Exception:
        shutil.rmtree(into, ignore_errors=True)
        raise
