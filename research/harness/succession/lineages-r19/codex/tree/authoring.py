"""Propose a claim from a session trace and certify its verdict cold."""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import tempfile

from . import _util, kernel, render


TRACE = ".reticuli/draft.jsonl"


def _events(workspace):
    try:
        with open(os.path.join(workspace, TRACE), encoding="utf-8") as stream:
            return [json.loads(line) for line in stream if line.strip()]
    except (OSError, ValueError) as exc:
        raise kernel.ClaimError("cannot read session trace: " + str(exc)) from exc


def _real_file(workspace, name):
    """Check each directory entry with its exact spelling on every host."""
    try:
        path = _util.safe_path(workspace, name)
        directory = os.path.abspath(workspace)
        for part in name.split("/"):
            if part not in os.listdir(directory):
                return False
            directory = os.path.join(directory, part)
        return os.path.isfile(path)
    except (OSError, kernel.ClaimError):
        return False


def _shell_files(workspace, command):
    try:
        words = shlex.split(command)
    except ValueError:
        words = re.findall(r"[A-Za-z0-9_./-]+", command)
    return {word for word in words if _real_file(workspace, word)}


def _confine(workspace, name):
    path = _util.safe_path(workspace, name)
    if not _real_file(workspace, name):
        raise kernel.ClaimError("traced file is missing or not exactly named: " + name)
    kernel._hash_file(path)
    return path


def propose(workspace, outputs, name=None, *, claim=None, generated=None):
    workspace = os.path.abspath(workspace)
    events = _events(workspace)
    outputs = list(outputs)
    for output in outputs:
        _util.safe_path(workspace, output)
    writes = set()
    reads = set()
    commands = []
    for event in events:
        kind = event.get("event")
        path = event.get("path")
        if kind in ("write", "read") and isinstance(path, str):
            _util.safe_path(workspace, path)
            (writes if kind == "write" else reads).add(path)
        if kind == "bash" and isinstance(event.get("cmd"), str):
            commands.append(event["cmd"])
    if not commands:
        raise kernel.ClaimError("session has no gate command")
    declared_claim = set(claim or [])
    declared_generated = set(generated or [])
    for path in declared_claim | declared_generated | reads | writes:
        _confine(workspace, path)
    if declared_claim & declared_generated:
        raise kernel.ClaimError("claim and generated declarations overlap")
    if declared_claim & set(outputs) or declared_generated & set(outputs):
        raise kernel.ClaimError("a verdict cannot be an input or generated file")

    candidates = set(reads)
    for command in commands:
        candidates.update(_shell_files(workspace, command))
    candidates.difference_update(writes)
    candidates.difference_update(outputs)
    inputs = sorted((candidates | declared_claim) - declared_generated)
    generated_files = sorted((writes | declared_generated) - declared_claim - set(outputs))
    claim_doc = {"name": name or os.path.basename(workspace), "format": 3}
    if inputs:
        claim_doc["inputs"] = inputs
    steps = [{"kind": "produce", "output": path, "class": "generated",
              "guidance": f"regenerate {path} to pass the gate"}
             for path in generated_files]
    gate = commands[-1]
    steps.extend({"kind": "gate", "output": output, "class": "validated", "run": gate}
                 for output in outputs)
    return {"claim": claim_doc, "step": steps}


def build_claim(workspace, outputs, into, *, name=None, claim=None, generated=None):
    workspace = os.path.abspath(workspace)
    parsed = propose(workspace, outputs, name, claim=claim, generated=generated)
    if kernel.vacuous_gates(parsed):
        raise kernel.ClaimError("vacuous gate: all deciders are generated")
    for output in outputs:
        _confine(workspace, output)
    if os.path.exists(into):
        if os.listdir(into):
            raise kernel.ClaimError("claim target is not empty")
    else:
        os.makedirs(into)
    names = set(parsed["claim"].get("inputs", []))
    names.update(step["output"] for step in parsed["step"])
    for path in sorted(names):
        source = _confine(workspace, path)
        dest = _util.safe_path(into, path)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copyfile(source, dest)
    with open(os.path.join(into, kernel.RECIPE), "w", encoding="utf-8") as stream:
        stream.write(render.dump_recipe(parsed))

    # The trace may report a warm success. A new room must earn the same bytes.
    with tempfile.TemporaryDirectory(prefix="reticuli-cold-") as room:
        for path in sorted(names - set(outputs)):
            dest = _util.safe_path(room, path)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copyfile(_util.safe_path(into, path), dest)
        with open(os.path.join(room, kernel.RECIPE), "w", encoding="utf-8") as stream:
            stream.write(render.dump_recipe(parsed))
        for step in parsed["step"]:
            if step["kind"] != "gate":
                continue
            result = kernel.run_gate(step["run"], room, parsed)
            output = step["output"]
            if result["status"] != "ok" or not _real_file(room, output):
                raise kernel.ClaimError("cold gate did not reproduce: " + output)
            if kernel._hash_file(_util.safe_path(room, output)) != kernel._hash_file(_util.safe_path(into, output)):
                raise kernel.ClaimError("cold verdict differs: " + output)

    manifest = kernel.seal(into)
    events = _events(workspace)
    stamps = [event["ts"] for event in events if type(event.get("ts")) in (int, float)]
    calls = sum(event.get("event") == "prompt" for event in events)
    kernel.ledger(into, {"event": "producer", "calls": calls,
                         "seconds": max(stamps) - min(stamps) if len(stamps) > 1 else 0.0})
    verified = kernel.verify(into)
    if not verified["ok"]:
        raise kernel.ClaimError("claim identity mismatch")
    return {"ok": True, "root": manifest["root"], "path": into}
