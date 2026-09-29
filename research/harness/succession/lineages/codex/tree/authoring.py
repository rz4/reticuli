"""Turn a session trace and declared claim boundary into a cold certified claim."""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import tempfile
from pathlib import Path

from . import kernel, render, registry
from ._util import copy_into, safe_path

TRACE = ".reticuli/draft.jsonl"


def _events(ws):
    try:
        with open(safe_path(ws, TRACE), encoding="utf-8") as source:
            return [json.loads(line) for line in source if line.strip()]
    except (OSError, ValueError) as exc:
        raise kernel.ClaimError(f"cannot read session trace: {exc}") from exc


def _actual_file(ws, name):
    """Require exact directory-entry spelling on case-folding hosts."""
    try:
        path = safe_path(ws, name)
        pieces = Path(name).parts
        parent = os.path.abspath(ws)
        for piece in pieces:
            if piece not in os.listdir(parent):
                return False
            parent = os.path.join(parent, piece)
        return os.path.isfile(path)
    except (OSError, ValueError, kernel.ClaimError):
        return False


def _confined(ws, name):
    return safe_path(ws, name)


def propose(ws, outputs, name=None, claim=None, generated=None):
    events = _events(ws)
    if not outputs:
        raise kernel.ClaimError("claim needs a verdict output")
    gates = [event["cmd"] for event in events if event.get("event") == "bash" and isinstance(event.get("cmd"), str)]
    if not gates:
        raise kernel.ClaimError("session has no gate")
    declared = list(dict.fromkeys(claim or []))
    writes = [event["path"] for event in events if event.get("event") == "write" and isinstance(event.get("path"), str)]
    reads = [event["path"] for event in events if event.get("event") == "read" and isinstance(event.get("path"), str)]
    for path in (*outputs, *declared, *(generated or []), *writes, *reads):
        _confined(ws, path)
    products = list(dict.fromkeys([*writes, *(generated or [])]))
    products = [path for path in products if path not in declared and path not in outputs]
    candidates = list(reads)
    for command in gates:
        try:
            candidates.extend(shlex.split(command))
        except ValueError:
            candidates.extend(re.findall(r"[\w./-]+", command))
    inputs = list(declared)
    for candidate in candidates:
        if candidate in inputs or candidate in products or candidate in outputs or candidate.startswith(".reticuli/"):
            continue
        if _actual_file(ws, candidate):
            inputs.append(candidate)
    for path in (*inputs, *products, *outputs):
        _confined(ws, path)
    for path in (*inputs, *products):
        if not _actual_file(ws, path):
            raise kernel.ClaimError(f"missing claim file: {path}")
    data = {"claim": {"name": name or os.path.basename(os.path.abspath(ws)), "inputs": sorted(inputs)},
            "step": [{"kind": "produce", "output": path, "class": "generated"} for path in sorted(products)]}
    data["step"].extend({"kind": "gate", "output": output, "class": "validated", "run": gates[-1]} for output in outputs)
    if kernel.vacuous_gates(data):
        raise kernel.ClaimError("vacuous gate: every decider is generated")
    return data


def build_claim(ws, outputs, into, name=None, claim=None, generated=None):
    data = propose(ws, outputs, name, claim, generated)
    events = _events(ws)
    if os.path.exists(into) and (not os.path.isdir(into) or os.listdir(into)):
        raise kernel.ClaimError("claim target contains bytes")
    with tempfile.TemporaryDirectory(prefix="reticuli-author-") as room:
        Path(room, kernel.RECIPE).write_text(render.dump_recipe(data), encoding="utf-8")
        names = [*data["claim"]["inputs"], *(step["output"] for step in data["step"] if step["kind"] == "produce")]
        for path in names:
            copy_into(safe_path(ws, path), safe_path(room, path))
        for step in data["step"]:
            if step["kind"] != "gate":
                continue
            result = kernel.run_gate(step["run"], room, data)
            output = step["output"]
            if result["status"] != "ok" or not os.path.isfile(safe_path(room, output)):
                raise kernel.ClaimError(f"gate {output} failed cold: {result['stderr'][-200:]}")
            if kernel._hash_file(safe_path(room, output)) != kernel._hash_file(safe_path(ws, output)):
                raise kernel.ClaimError(f"gate {output} verdict changed cold")
        if not kernel.audit(_seal_temp(room))["ok"]:
            raise kernel.ClaimError("claim verdict does not reproduce cold")
        os.makedirs(into, exist_ok=True)
        for path in [kernel.RECIPE, *names, *outputs]:
            copy_into(safe_path(room, path), safe_path(into, path))
        components = registry.detect_components(ws, data["claim"]["inputs"])
        manifest = registry.seal_with(into, components=components)
        prompts = [e for e in events if e.get("event") == "prompt"]
        times = [e["ts"] for e in events if isinstance(e.get("ts"), (int, float))]
        seconds = float(max(times) - min(times)) if len(times) >= 2 else 0.0
        kernel.ledger(into, {"event": "oracle", "calls": len(prompts), "seconds": seconds})
        return {"ok": True, "root": manifest["root"], "path": into}


def _seal_temp(room):
    kernel.seal(room)
    return room
