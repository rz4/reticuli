"""Make a cold-certified claim from a recorded work session."""

import json
import os
import re
import shlex
import shutil
import tempfile

from . import kernel, render
from ._util import copy_into, safe_path

TRACE = ".reticuli/draft.jsonl"


def _events(directory):
    try:
        with open(os.path.join(directory, TRACE), encoding="utf-8") as stream:
            return [json.loads(line) for line in stream if line.strip()]
    except (OSError, ValueError) as exc:
        raise kernel.ClaimError("cannot read authoring trace") from exc


def _exact_file(directory, name):
    """Require a real entry with the same case in every path component."""
    try:
        safe_path(directory, name)
        current = directory
        for part in name.split("/"):
            if part not in os.listdir(current):
                return False
            current = os.path.join(current, part)
        return os.path.isfile(current)
    except (OSError, kernel.ClaimError):
        return False


def _tokens(command):
    try:
        words = shlex.split(command)
    except ValueError:
        return []
    return [w for w in words if re.fullmatch(r"[\w./-]+", w) and not w.startswith("-")]


def propose(directory, outputs, name="claim", *, claim=None, generated=None):
    directory = os.path.abspath(directory)
    events = _events(directory)
    writes = set()
    reads = set()
    commands = []
    for event in events:
        if event.get("event") == "write":
            writes.add(event.get("path"))
        elif event.get("event") == "read":
            reads.add(event.get("path"))
        elif event.get("event") == "bash":
            commands.append(event.get("cmd", ""))
    claimed = set(claim or [])
    produced = (writes | set(generated or [])) - claimed
    # Trace reads are declarations, even when they point outside the room.
    for path in reads | writes | claimed | produced | set(outputs):
        safe_path(directory, path)
    candidates = set(reads) | claimed
    for command in commands:
        for token in _tokens(command):
            if _exact_file(directory, token) and token not in outputs and token not in produced:
                candidates.add(token)
    inputs = sorted(candidates - produced - set(outputs))
    for path in inputs | set() if False else inputs:
        if not _exact_file(directory, path):
            raise kernel.ClaimError("input missing: " + path)
    steps = [{"kind": "produce", "output": path, "class": "generated",
              "guidance": f"regenerate {path} to pass the gate"}
             for path in sorted(produced)]
    command = commands[-1] if commands else ""
    if not command:
        raise kernel.ClaimError("no gate in session trace")
    steps.extend({"kind": "gate", "output": path, "class": "validated", "run": command}
                 for path in outputs)
    return {"claim": {"name": name, "format": 3, "inputs": inputs}, "step": steps}


def build_claim(directory, outputs, into, name="claim", *, claim=None, generated=None):
    directory = os.path.abspath(directory)
    into = os.path.abspath(into)
    parsed = propose(directory, outputs, name, claim=claim, generated=generated)
    bad = kernel.vacuous_gates(parsed)
    if bad:
        raise kernel.ClaimError("vacuous gate: " + ", ".join(bad))
    # The cold room receives only declared bytes; warm verdicts are compared,
    # never copied into it as proof.
    with tempfile.TemporaryDirectory(prefix="reticuli-author-") as cold:
        with open(os.path.join(cold, kernel.RECIPE), "w", encoding="utf-8") as stream:
            stream.write(render.dump_recipe(parsed))
        for path in parsed["claim"]["inputs"] + [s["output"] for s in parsed["step"] if s["kind"] == "produce"]:
            copy_into(safe_path(directory, path), safe_path(cold, path))
        for step in parsed["step"]:
            if step["kind"] != "gate":
                continue
            path = step["output"]
            warm = kernel._hash_file(safe_path(directory, path))
            result = kernel.run_gate(step["run"], cold, parsed)
            if result["status"] != "ok" or not os.path.isfile(safe_path(cold, path)):
                raise kernel.ClaimError("cold gate failed: " + result.get("stderr", result["status"]))
            if kernel._hash_file(safe_path(cold, path)) != warm:
                raise kernel.ClaimError("cold verdict mismatch: " + path)
        if os.path.exists(into):
            if not os.path.isdir(into) or os.listdir(into):
                raise kernel.ClaimError("claim target contains bytes")
        shutil.copytree(cold, into, dirs_exist_ok=True)
    sealed = kernel.seal(into)
    events = _events(directory)
    prompts = [e for e in events if e.get("event") == "prompt"]
    timestamps = [e["ts"] for e in events if isinstance(e.get("ts"), (int, float))]
    cost = {"event": "oracle", "calls": len(prompts)}
    if timestamps:
        cost["seconds"] = max(timestamps) - min(timestamps)
    kernel.ledger(into, cost)
    return {"ok": True, "root": sealed["root"], "name": name}
