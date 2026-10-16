"""Turn an observed coding session into a cold-certified claim."""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import tempfile

from . import kernel
from .render import dump_recipe

TRACE = ".reticuli/draft.jsonl"
_WORD_PATH = re.compile(r"^[A-Za-z0-9_.@+/-]+$")


def _events(ws):
    path = os.path.join(ws, TRACE)
    events = []
    try:
        with open(path, encoding="utf-8") as stream:
            for line in stream:
                try: value = json.loads(line)
                except (ValueError, TypeError): continue
                if isinstance(value, dict): events.append(value)
    except OSError as exc:
        raise kernel.ClaimError("session has no trace") from None
    return events


def _confined(name):
    if not isinstance(name, str) or not name or os.path.isabs(name) or "\0" in name:
        raise kernel.ClaimError("unsafe trace path")
    if ".." in name.replace("\\", "/").split("/"):
        raise kernel.ClaimError("trace path escapes workspace")
    return name.replace("\\", "/")


def _exact_file(ws, name):
    """True only when every path component has exactly this spelling."""
    try: name = _confined(name)
    except kernel.ClaimError: return False
    current = os.path.abspath(ws)
    bits = [x for x in name.split("/") if x not in ("", ".")]
    for index, bit in enumerate(bits):
        try: entries = os.listdir(current)
        except OSError: return False
        if bit not in entries: return False
        current = os.path.join(current, bit)
        if index < len(bits)-1 and not os.path.isdir(current): return False
    return bool(bits) and os.path.isfile(current)


def _command_files(ws, command):
    try: words = shlex.split(command)
    except ValueError: words = command.split()
    result = []
    # Shell words include literals (e.g. printf's "ok"). Exact directory
    # spelling plus regular-file existence prevents host case-folding drift.
    for word in words:
        candidate = word[2:] if word.startswith("./") else word
        candidate = candidate.rstrip(";,|&")
        if _WORD_PATH.fullmatch(candidate or "") and _exact_file(ws, candidate):
            if candidate not in result: result.append(candidate)
    return result


def _trace_shape(ws, events, claimed=None, extra_generated=None):
    written = []
    read = []
    commands = []
    for event in events:
        kind = event.get("event")
        if kind in ("write", "read") and isinstance(event.get("path"), str):
            path = _confined(event["path"])  # refusal precedes every copy
            (written if kind == "write" else read).append(path)
        if kind in ("bash", "gate"):
            command = event.get("cmd") or event.get("run")
            if isinstance(command, str): commands.append(command)
    claimed = [_confined(x) for x in (claimed or [])]
    generated = [_confined(x) for x in (extra_generated or [])]
    for path in written:
        if path not in claimed and path not in generated: generated.append(path)
    inputs = []
    for path in read + claimed:
        if path not in generated and path not in inputs: inputs.append(path)
    for command in commands:
        for path in _command_files(ws, command):
            if path not in generated and path not in inputs: inputs.append(path)
    return generated, inputs, commands


def propose(ws, outputs, name=None, claim=None, generated=None):
    """Infer a draft recipe from a trace without sealing it."""
    ws = os.path.abspath(os.fspath(ws)); events = _events(ws)
    generated_files, inputs, commands = _trace_shape(ws, events, claim, generated)
    verdicts = [_confined(x) for x in outputs]
    # A verdict is output, not an input, even if a command token names it.
    inputs = [x for x in inputs if x not in verdicts]
    command = commands[-1] if commands else None
    if not command:
        raise kernel.ClaimError("session trace contains no gate")
    claim_table = {"name": name or os.path.basename(ws), "format": 3,
                   "inputs": inputs}
    steps = [{"kind": "produce", "output": path, "class": "generated",
              "guidance": f"regenerate {path} to pass the gate"}
             for path in generated_files if path not in verdicts]
    for output in verdicts:
        steps.append({"kind": "gate", "output": output,
                      "class": "validated", "run": command})
    recipe = {"claim": claim_table, "step": steps}
    if kernel.vacuous_gates(recipe):
        raise kernel.ClaimError("vacuous gate: every decider is generated")
    return {"claim": claim_table, "step": steps, "recipe": recipe,
            "events": events}


def _copy(source, target, names):
    for name in names:
        _confined(name)
        src = os.path.join(source, name); dst = os.path.join(target, name)
        if not os.path.isfile(src): raise kernel.ClaimError("declared file absent: " + name)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)


def build_claim(ws, outputs, into, name=None, claim=None, generated=None):
    """Build and cold-certify a claim from a traced session.

    The warm trace proposes structure only. Verdict bytes are removed and
    re-earned in a clean copy before the claim is sealed.
    """
    ws = os.path.abspath(os.fspath(ws)); into = os.path.abspath(os.fspath(into))
    draft = propose(ws, outputs, name=name, claim=claim, generated=generated)
    recipe = draft["recipe"]
    if os.path.exists(into):
        if not os.path.isdir(into) or os.listdir(into):
            raise kernel.ClaimError("claim target is not empty")
    else: os.makedirs(into)
    building = tempfile.mkdtemp(prefix="reticuli-authoring-")
    room = os.path.join(building, "claim"); os.makedirs(room)
    try:
        input_names = list(recipe["claim"].get("inputs", []))
        generated_names = [s["output"] for s in recipe["step"] if s["kind"] == "produce"]
        _copy(ws, room, input_names + generated_names)
        with open(os.path.join(room, kernel.RECIPE), "w", encoding="utf-8", newline="\n") as stream:
            stream.write(dump_recipe(recipe))
        gate_rows = []
        for step in (s for s in recipe["step"] if s["kind"] == "gate"):
            path = os.path.join(room, step["output"])
            if os.path.lexists(path): os.unlink(path)
            result = kernel.run_gate(step["run"], room, recipe)
            if result.get("status") != "ok" or not os.path.isfile(path):
                raise kernel.ClaimError("cold gate failed")
            warm = os.path.join(ws, step["output"])
            if not os.path.isfile(warm) or open(warm, "rb").read() != open(path, "rb").read():
                raise kernel.ClaimError("cold verdict does not reproduce")
            gate_rows.append(result)
        # Move only after every cold test succeeds, leaving no partial target.
        for entry in os.listdir(room):
            shutil.move(os.path.join(room, entry), os.path.join(into, entry))
        man = kernel.seal(into)
        prompts = [e for e in draft["events"] if e.get("event") == "prompt"]
        numeric = [float(e["ts"]) for e in draft["events"]
                   if isinstance(e.get("ts"), (int, float))]
        seconds = max(numeric)-min(numeric) if len(numeric) >= 2 else 0.0
        kernel.ledger(into, {"event": "oracle", "kind": "authoring",
                             "calls": len(prompts), "seconds": seconds})
        return {"ok": True, "root": man["root"], "name": man["name"],
                "gates": gate_rows}
    except Exception:
        shutil.rmtree(into, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(building, ignore_errors=True)


__all__ = ["TRACE", "build_claim", "propose"]
