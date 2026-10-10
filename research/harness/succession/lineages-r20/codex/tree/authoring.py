"""Certify a traced session as a claim after a cold replay of its gates."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import tempfile

from . import kernel, render
from ._util import safe_path

TRACE = ".reticuli/draft.jsonl"


def _events(workspace):
    path = os.path.join(workspace, TRACE)
    try:
        with open(path, encoding="utf-8") as stream:
            return [json.loads(line) for line in stream if line.strip()]
    except (OSError, ValueError) as exc:
        raise kernel.ClaimError(f"cannot read session trace: {exc}") from exc


def _real_file(workspace, name):
    """Check each directory entry literally, even on case-folding hosts."""
    safe_path(workspace, name)
    here = workspace
    for part in name.split("/"):
        if not os.path.isdir(here) or part not in os.listdir(here):
            return False
        here = os.path.join(here, part)
    return os.path.isfile(here)


def _command_files(workspace, command):
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        tokens = command.split()
    found = set()
    for token in tokens:
        if token.startswith("./"):
            token = token[2:]
        if not token or token.startswith("-") or os.path.isabs(token):
            continue
        try:
            if _real_file(workspace, token):
                found.add(token)
        except kernel.ClaimError:
            pass
    return found


def propose(workspace, outputs, name, *, claim=None, generated=None):
    events = _events(workspace)
    written = {event["path"] for event in events
               if event.get("event") == "write" and isinstance(event.get("path"), str)}
    read = {event["path"] for event in events
            if event.get("event") == "read" and isinstance(event.get("path"), str)}
    commands = [event["cmd"] for event in events
                if event.get("event") == "bash" and isinstance(event.get("cmd"), str)]
    claimed = set(claim or [])
    made = (written | set(generated or [])) - claimed - set(outputs)
    candidates = set(read) | claimed
    for command in commands:
        candidates.update(_command_files(workspace, command))
    inputs = sorted(candidates - made - set(outputs))
    # Confine every trace-derived path before any copy can take place.
    for path in sorted(made | set(inputs) | set(outputs)):
        safe_path(workspace, path)
    for path in made | set(inputs):
        if not _real_file(workspace, path):
            raise kernel.ClaimError(f"session file is absent: {path}")
    steps = [{"kind": "produce", "output": path, "class": "generated",
              "guidance": f"regenerate {path} to pass the gate"}
             for path in sorted(made)]
    steps += [{"kind": "gate", "output": output, "class": "validated", "run": command}
              for output, command in zip(outputs, commands[-len(outputs):])]
    return {"claim": {"name": name, "format": 3, "inputs": inputs}, "step": steps}


def build_claim(workspace, outputs, destination, *, name=None, claim=None, generated=None):
    workspace = os.path.abspath(workspace)
    name = name or os.path.basename(os.path.abspath(destination))
    parsed = propose(workspace, outputs, name, claim=claim, generated=generated)
    if len([s for s in parsed["step"] if s["kind"] == "gate"]) != len(outputs):
        raise kernel.ClaimError("a gate is required for each verdict")
    if kernel.vacuous_gates(parsed):
        raise kernel.ClaimError("vacuous gate: every decider is generated")
    events = _events(workspace)
    with tempfile.TemporaryDirectory(prefix="reticuli-author-") as room:
        with open(os.path.join(room, kernel.RECIPE), "w", encoding="utf-8") as stream:
            stream.write(render.dump_recipe(parsed))
        for path in parsed["claim"]["inputs"] + [s["output"] for s in parsed["step"] if s["kind"] == "produce"]:
            source = safe_path(workspace, path)
            kernel._hash_file(source)
            target = safe_path(room, path)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copyfile(source, target)
        for step in parsed["step"]:
            if step["kind"] != "gate":
                continue
            output = step["output"]
            warm = safe_path(workspace, output)
            warm_digest = kernel._hash_file(warm)
            outcome = kernel.run_gate(step["run"], room, parsed)
            if outcome["status"] != "ok":
                raise kernel.ClaimError("cold gate failed: " + (outcome.get("stderr") or outcome["status"])[-500:])
            cold = safe_path(room, output)
            if kernel._hash_file(cold) != warm_digest:
                raise kernel.ClaimError(f"cold verdict differs from session: {output}")
        if os.path.exists(destination):
            if os.listdir(destination):
                raise kernel.ClaimError("claim destination is not empty")
            os.rmdir(destination)
        os.makedirs(os.path.dirname(os.path.abspath(destination)), exist_ok=True)
        shutil.copytree(room, destination)
    manifest = kernel.seal(destination)
    timestamps = [event["ts"] for event in events if type(event.get("ts")) in (int, float)]
    kernel.ledger(destination, {"event": "oracle", "kind": "producer",
                                "calls": sum(event.get("event") == "prompt" for event in events),
                                "seconds": max(timestamps) - min(timestamps) if timestamps else 0.0})
    return {"ok": kernel.verify(destination)["ok"], "root": manifest["root"]}
