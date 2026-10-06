"""Turn a recorded working session into a cold certified claim."""
from __future__ import annotations

import json
import os
import shlex
import shutil
import tempfile
from pathlib import Path
from typing import Any

from . import kernel, render
from ._util import copy_into

TRACE = ".reticuli/draft.jsonl"


def _events(workspace: str) -> list[dict[str, Any]]:
    path = kernel._safe(workspace, TRACE)
    try:
        with open(path, encoding="utf-8") as stream:
            return [json.loads(line) for line in stream if line.strip()]
    except (OSError, ValueError) as exc:
        raise kernel.ClaimError(f"cannot read session trace: {exc}") from exc


def _exact_file(workspace: str, name: str) -> bool:
    """Check spelling against directory entries, independent of case folding."""
    try:
        kernel._safe(workspace, name)
        current = workspace
        for part in name.split("/"):
            if part not in os.listdir(current):
                return False
            current = os.path.join(current, part)
        return os.path.isfile(current)
    except (kernel.ClaimError, OSError):
        return False


def _candidates(command: str) -> list[str]:
    try:
        words = shlex.split(command.replace("&&", " ").replace("||", " ").replace(";", " "))
    except ValueError:
        return []
    return [word.removeprefix("./") for word in words if word and not word.startswith("-")]


def propose(workspace: str, outputs: list[str], name: str,
            *, claim: list[str] | None = None,
            generated: list[str] | None = None) -> dict[str, Any]:
    events = _events(workspace)
    commands = [e["cmd"] for e in events if e.get("event") == "bash" and isinstance(e.get("cmd"), str)]
    if not commands:
        raise kernel.ClaimError("session has no gate command")
    written = [e["path"] for e in events if e.get("event") == "write" and isinstance(e.get("path"), str)]
    read = [e["path"] for e in events if e.get("event") == "read" and isinstance(e.get("path"), str)]
    explicit_inputs = list(claim or [])
    produced = list(dict.fromkeys([*written, *(generated or [])]))
    produced = [p for p in produced if p not in explicit_inputs and p not in outputs]
    candidate_inputs = [*read, *explicit_inputs]
    for command in commands:
        candidate_inputs.extend(_candidates(command))
    inputs = []
    for path in candidate_inputs:
        # Explicit trace paths must be confined even when absent.
        if path in read or path in explicit_inputs:
            kernel._safe(workspace, path)
        if path not in produced and path not in outputs and _exact_file(workspace, path):
            inputs.append(path)
    inputs = list(dict.fromkeys(inputs))
    steps = [{"kind": "produce", "output": path, "class": "generated",
              "guidance": f"regenerate {path} to pass the gate"} for path in produced]
    if len(outputs) != len(commands):
        if len(commands) == 1:
            commands = commands * len(outputs)
        else:
            raise kernel.ClaimError("gate commands and verdict outputs do not match")
    steps.extend({"kind": "gate", "output": out, "class": "validated", "run": command}
                 for out, command in zip(outputs, commands))
    return {"claim": {"name": name, "format": 3, "inputs": inputs}, "step": steps}


def build_claim(workspace: str, outputs: list[str], into: str, *, name: str | None = None,
                claim: list[str] | None = None, generated: list[str] | None = None) -> dict[str, Any]:
    workspace = os.path.realpath(workspace)
    into = os.path.realpath(into)
    parsed = propose(workspace, outputs, name or os.path.basename(into),
                     claim=claim, generated=generated)
    # Validate all declared source paths before copying any file.
    names = [*parsed["claim"]["inputs"],
             *(step["output"] for step in parsed["step"])]
    for item in names:
        kernel._safe(workspace, item)
    if kernel.vacuous_gates(parsed):
        raise kernel.ClaimError("vacuous gate: every decider is generated")
    with tempfile.TemporaryDirectory(prefix="reticuli-authoring-") as room:
        Path(os.path.join(room, kernel.RECIPE)).write_text(render.dump_recipe(parsed), encoding="utf-8")
        for item in parsed["claim"]["inputs"]:
            copy_into(kernel._safe(workspace, item), kernel._safe(room, item))
        for step in parsed["step"]:
            if step["kind"] == "produce":
                copy_into(kernel._safe(workspace, step["output"]), kernel._safe(room, step["output"]))
        for step in parsed["step"]:
            if step["kind"] != "gate":
                continue
            verdict = step["output"]
            warm = kernel._hash_file(kernel._safe(workspace, verdict))
            outcome = kernel.run_gate(step["run"], room, parsed)
            if outcome["status"] != "ok" or kernel._hash_file(kernel._safe(room, verdict)) != warm:
                raise kernel.ClaimError(f"gate cannot re-earn verdict cold: {verdict}")
        if os.path.exists(into):
            if not os.path.isdir(into) or os.listdir(into):
                raise kernel.ClaimError("claim target is not empty")
            os.rmdir(into)
        os.makedirs(os.path.dirname(into), exist_ok=True)
        shutil.copytree(room, into)
    sealed = kernel.seal(into)
    events = _events(workspace)
    times = [float(e["ts"]) for e in events if isinstance(e.get("ts"), (int, float))]
    calls = sum(e.get("event") == "prompt" for e in events)
    kernel.ledger(into, {"event": "oracle", "kind": "producer", "calls": calls,
                         "seconds": max(times) - min(times) if times else 0.0})
    return {"ok": True, **sealed}
