"""Propose and cold-certify a claim from a session trace."""

import json
import os
import re
import shutil
import tempfile

from . import kernel, render
from ._util import safe_path, copy_into

TRACE = ".reticuli/draft.jsonl"


def _events(ws):
    try:
        with open(os.path.join(ws, TRACE), encoding="utf-8") as stream:
            return [json.loads(line) for line in stream if line.strip()]
    except (OSError, ValueError) as exc:
        raise kernel.ClaimError("cannot read session trace") from exc


def _real_entry(ws, name):
    """Reject case-folded matches even on a case-insensitive host."""
    try:
        safe_path(ws, name)
    except kernel.ClaimError:
        return False
    cursor = ws
    for part in name.split("/"):
        if part not in os.listdir(cursor):
            return False
        cursor = os.path.join(cursor, part)
    return os.path.isfile(cursor)


def propose(ws, outputs, name, *, claim=None, generated=None):
    ws = os.path.abspath(ws)
    events = _events(ws)
    outputs = list(dict.fromkeys(outputs))
    for output in outputs:
        safe_path(ws, output)
    writes = set()
    reads = set()
    commands = []
    for event in events:
        if event.get("event") == "write" and isinstance(event.get("path"), str):
            writes.add(event["path"])
        elif event.get("event") == "read" and isinstance(event.get("path"), str):
            # An explicit traced read is a claim path even if it escapes.
            safe_path(ws, event["path"])
            reads.add(event["path"])
        elif event.get("event") == "bash" and isinstance(event.get("cmd"), str):
            commands.append(event["cmd"])
    pinned = set(claim or ()) | reads
    produced = set(generated or ()) | (writes - pinned - set(outputs))
    for command in commands:
        for token in re.findall(r"[A-Za-z0-9_./-]+", command):
            if token in produced or token in outputs or token.startswith("-"):
                continue
            if _real_entry(ws, token):
                pinned.add(token)
    pinned -= set(outputs)
    produced -= pinned
    for path in pinned | produced:
        safe_path(ws, path)
        if not _real_entry(ws, path):
            raise kernel.ClaimError("missing declared session file: " + path)
    steps = [{"kind": "produce", "output": path, "class": "generated",
              "guidance": f"regenerate {path} to pass the gate"}
             for path in sorted(produced)]
    for output in outputs:
        if not commands:
            raise kernel.ClaimError("session has no gate command")
        steps.append({"kind": "gate", "output": output, "class": "validated",
                      "run": commands[-1]})
    recipe = {"claim": {"name": name, "format": 3, "inputs": sorted(pinned)},
              "step": steps}
    if kernel.vacuous_gates(recipe):
        raise kernel.ClaimError("vacuous gate: every decider is generated")
    return recipe


def build_claim(ws, outputs, into, *, name=None, claim=None, generated=None):
    ws = os.path.abspath(ws)
    recipe = propose(ws, outputs, name or os.path.basename(os.path.normpath(into)),
                     claim=claim, generated=generated)
    with tempfile.TemporaryDirectory(prefix="reticuli-authoring-") as room:
        for path in recipe["claim"]["inputs"]:
            copy_into(safe_path(ws, path), safe_path(room, path))
        for step in recipe["step"]:
            if step["kind"] == "produce":
                copy_into(safe_path(ws, step["output"]), safe_path(room, step["output"]))
        with open(os.path.join(room, kernel.RECIPE), "w", encoding="utf-8") as stream:
            stream.write(render.dump_recipe(recipe))
        for step in recipe["step"]:
            if step["kind"] != "gate":
                continue
            output = step["output"]
            warm = safe_path(ws, output)
            if not os.path.isfile(warm):
                raise kernel.ClaimError("missing warm verdict: " + output)
            result = kernel.run_gate(step["run"], room, recipe)
            cold = safe_path(room, output)
            if result["status"] != "ok" or not os.path.isfile(cold):
                raise kernel.ClaimError("gate did not re-earn verdict cold")
            if kernel._hash_file(warm) != kernel._hash_file(cold):
                raise kernel.ClaimError("cold verdict differs from session verdict")
        sealed = kernel.seal(room)
        if os.path.exists(into):
            if os.path.isdir(into):
                shutil.rmtree(into)
            else:
                os.unlink(into)
        os.makedirs(os.path.dirname(os.path.abspath(into)), exist_ok=True)
        shutil.copytree(room, into)
    events = _events(ws)
    prompts = sum(event.get("event") == "prompt" for event in events)
    times = [event["ts"] for event in events if type(event.get("ts")) in (int, float)]
    if prompts or times:
        kernel.ledger(into, {"event": "oracle", "calls": prompts,
                             "seconds": max(times) - min(times) if times else 0.0})
    return {"ok": True, "root": sealed["root"], "path": into}
