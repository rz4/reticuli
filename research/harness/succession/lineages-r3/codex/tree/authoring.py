"""Turn a session trace and its declared boundary into a sealed claim."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import tempfile

from . import kernel, render
from ._util import safe_path

TRACE = ".reticuli/draft.jsonl"


def _events(ws):
    try:
        with open(os.path.join(ws, TRACE), encoding="utf-8") as stream:
            return [json.loads(line) for line in stream if line.strip()]
    except (OSError, ValueError) as exc:
        raise kernel.ClaimError(f"cannot read session trace: {exc}") from exc


def _exact_file(ws, name):
    """Require each spelling to be an actual directory entry on every host."""
    if not isinstance(name, str):
        return False
    try:
        safe_path(ws, name)
        current = ws
        parts = name.split("/")
        for part in parts:
            if part not in os.listdir(current):
                return False
            current = os.path.join(current, part)
        return os.path.isfile(current)
    except (OSError, kernel.ClaimError):
        return False


def _declared(ws, names):
    for name in names:
        safe_path(ws, name)
        if not _exact_file(ws, name):
            raise kernel.ClaimError(f"declared file is missing: {name}")


def propose(ws, outputs, name=None, *, claim=None, generated=None):
    events = _events(ws)
    outputs = list(dict.fromkeys(outputs))
    writes = [e["path"] for e in events if e.get("event") == "write" and isinstance(e.get("path"), str)]
    reads = [e["path"] for e in events if e.get("event") == "read" and isinstance(e.get("path"), str)]
    declared_inputs = list(dict.fromkeys(claim or []))
    generated_names = list(dict.fromkeys([*writes, *(generated or [])]))
    for path in [*outputs, *reads, *declared_inputs, *generated_names]:
        safe_path(ws, path)
    gate_commands = [e["cmd"] for e in events if e.get("event") == "bash" and isinstance(e.get("cmd"), str)]
    if not gate_commands:
        raise kernel.ClaimError("session has no gate command")
    command = gate_commands[-1]
    candidates = list(reads)
    try:
        tokens = shlex.split(command)
    except ValueError as exc:
        raise kernel.ClaimError(f"invalid gate command: {exc}") from exc
    for token in tokens:
        token = token.rstrip(";,)")
        if token.startswith("./"):
            token = token[2:]
        if token and _exact_file(ws, token):
            candidates.append(token)
    inputs = sorted(set(declared_inputs) | {p for p in candidates if p not in generated_names and p not in outputs})
    generated_names = sorted(p for p in set(generated_names) if p not in declared_inputs and p not in outputs)
    _declared(ws, [*inputs, *generated_names, *outputs])
    recipe = {"claim": {"name": name or os.path.basename(os.path.abspath(ws)), "inputs": inputs},
              "step": [{"kind": "produce", "output": p, "class": "generated"} for p in generated_names]
                      + [{"kind": "gate", "output": p, "class": "validated", "run": command}
                         for p in outputs]}
    return recipe


def build_claim(ws, outputs, into, *, name=None, claim=None, generated=None):
    parsed = propose(ws, outputs, name, claim=claim, generated=generated)
    vacuous = kernel.vacuous_gates(parsed)
    if vacuous:
        raise kernel.ClaimError("vacuous gate: " + ", ".join(vacuous))
    names = [*parsed["claim"]["inputs"],
             *(s["output"] for s in parsed["step"] if s["kind"] == "produce")]
    with tempfile.TemporaryDirectory(prefix="reticuli-author-") as room:
        for path in names:
            target = safe_path(room, path)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copyfile(safe_path(ws, path), target)
        with open(os.path.join(room, kernel.RECIPE), "w", encoding="utf-8") as stream:
            stream.write(render.dump_recipe(parsed))
        for step in parsed["step"]:
            if step["kind"] != "gate":
                continue
            outcome = kernel.run_gate(step["run"], room, parsed)
            if outcome["status"] != "ok":
                raise kernel.ClaimError("cold gate " + outcome["status"] + ": " + outcome.get("stderr", ""))
            output = step["output"]
            if kernel._hash_file(safe_path(ws, output)) != kernel._hash_file(safe_path(room, output)):
                raise kernel.ClaimError("cold gate verdict mismatch: " + output)
        kernel.seal(room)
        if os.path.exists(into):
            if os.path.isdir(into):
                shutil.rmtree(into)
            else:
                raise kernel.ClaimError("claim destination is not a directory")
        os.makedirs(os.path.dirname(os.path.abspath(into)), exist_ok=True)
        shutil.copytree(room, into)
    events = _events(ws)
    prompts = [e for e in events if e.get("event") == "prompt"]
    times = [e["ts"] for e in events if type(e.get("ts")) in (int, float)]
    kernel.ledger(into, {"event": "oracle", "calls": len(prompts),
                         "seconds": max(times) - min(times) if times else 0.0})
    return {"ok": kernel.verify(into)["ok"], "root": kernel.verify(into)["root"], "path": into}
