"""Turn a traced working session into a cold-certified claim."""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import tempfile

from . import kernel, render
from ._util import safe_path, copy_into

TRACE = ".reticuli/draft.jsonl"


def _events(ws):
    try:
        with open(safe_path(ws, TRACE), encoding="utf-8") as stream:
            return [json.loads(line) for line in stream if line.strip()]
    except (OSError, ValueError) as exc:
        raise kernel.ClaimError(f"cannot read session trace: {exc}") from exc


def _files(ws, names):
    """Expand literal declarations after checking confinement."""
    result = []
    for name in names or []:
        path = safe_path(ws, name)
        if not os.path.isfile(path):
            raise kernel.ClaimError(f"missing declared file: {name}")
        if name not in result:
            result.append(name)
    return result


def _shell_files(ws, command):
    # Only an exact directory entry is a candidate. os.path.exists alone can
    # silently case-fold on some hosts and would change a claim's identity.
    try:
        words = shlex.split(command)
    except ValueError:
        return []
    found = []
    for token in words:
        token = token.strip(";,()")
        if token.startswith("./"):
            token = token[2:]
        if not token or token.startswith("-"):
            continue
        try:
            path = safe_path(ws, token)
        except kernel.ClaimError:
            continue
        parent, base = os.path.split(path)
        if os.path.isdir(parent) and base in os.listdir(parent) and os.path.isfile(path):
            found.append(token)
    return list(dict.fromkeys(found))


def propose(ws, outputs, name=None, *, claim=None, generated=None):
    events = _events(ws)
    commands = [event.get("cmd") for event in events if event.get("event") == "bash" and isinstance(event.get("cmd"), str)]
    if not commands:
        raise kernel.ClaimError("session has no gate command")
    gate = commands[-1]
    outputs = _files(ws, outputs)
    claimed = _files(ws, claim)
    explicit_generated = _files(ws, generated)
    written = _files(ws, [event["path"] for event in events
                          if event.get("event") == "write" and isinstance(event.get("path"), str)
                          and event["path"] not in outputs])
    read = _files(ws, [event["path"] for event in events
                       if event.get("event") == "read" and isinstance(event.get("path"), str)])
    generated_files = list(dict.fromkeys([*written, *explicit_generated]))
    generated_files = [item for item in generated_files if item not in claimed and item not in outputs]
    candidates = _shell_files(ws, gate)
    inputs = list(dict.fromkeys([*claimed, *read, *(item for item in candidates
                 if item not in generated_files and item not in outputs)]))
    recipe = {"claim": {"name": name or os.path.basename(os.path.abspath(ws)), "inputs": inputs},
              "step": [{"kind": "produce", "output": item, "class": "generated"}
                       for item in generated_files] +
                      [{"kind": "gate", "output": item, "class": "validated", "run": gate}
                       for item in outputs]}
    return recipe


def build_claim(ws, outputs, into, *, name=None, claim=None, generated=None):
    recipe = propose(ws, outputs, name, claim=claim, generated=generated)
    if kernel.vacuous_gates(recipe):
        raise kernel.ClaimError("vacuous gate: every decider is generated")
    # Validate every trace-derived path before any copy can leave the session.
    names = [*recipe["claim"]["inputs"],
             *(step["output"] for step in recipe["step"])]
    for item in names:
        safe_path(ws, item)
    events = _events(ws)
    stamps = [event["ts"] for event in events if type(event.get("ts")) in (int, float)]
    calls = sum(event.get("event") == "prompt" for event in events)
    with tempfile.TemporaryDirectory(prefix="reticuli-authoring-") as room:
        with open(os.path.join(room, kernel.RECIPE), "w", encoding="utf-8") as stream:
            stream.write(render.dump_recipe(recipe))
        for item in names:
            if item in outputs:
                continue
            copy_into(safe_path(ws, item), safe_path(room, item))
        parsed = kernel.load_recipe(room)
        for step in parsed["step"]:
            if step["kind"] != "gate":
                continue
            outcome = kernel.run_gate(step["run"], room, parsed)
            if outcome["status"] != "ok":
                raise kernel.ClaimError("cold gate failed: " + outcome.get("stderr", "")[-300:])
            item = step["output"]
            if kernel._hash_file(safe_path(room, item)) != kernel._hash_file(safe_path(ws, item)):
                raise kernel.ClaimError("cold gate verdict mismatch: " + item)
        if os.path.exists(into) and os.listdir(into):
            raise kernel.ClaimError("claim target holds bytes")
        os.makedirs(into, exist_ok=True)
        shutil.copytree(room, into, dirs_exist_ok=True)
    manifest = kernel.seal(into)
    if calls:
        from ._util import ledger_add
        ledger_add(into, {"event": "oracle", "calls": calls,
                          "seconds": max(stamps) - min(stamps) if stamps else 0.0})
    return {"ok": kernel.verify(into)["ok"], "root": manifest["root"], "path": into}
