"""Sessions become claims: `propose` drafts, `build_claim` certifies cold.

A session is a workspace (`ws`) carrying a trace of what happened --
`.reticuli/draft.jsonl`, one JSON object per line: `prompt` (a human
instruction), `write`/`read` (a traced file access), `bash` (a command the
session ran). The trace has no authority of its own: it is read to find
CANDIDATE inputs and generated outputs, but declaration always wins over
provenance (`claim=`/`generated=` override what the trace would otherwise
suggest), and `build_claim` re-earns every gate COLD, in a fresh room, before
it will seal anything -- a verdict the bytes cannot reproduce never becomes a
claim.

Gates run only through `kernel.run_gate` (scrubbed, sandboxed, bounded) --
never `kernel.sandbox` directly, which would bypass the declared bound.

Stdlib only.
"""
import json
import os
import re
import shutil

from reticuli import kernel, render
from . import _util

TRACE = f"{kernel.STORE}/draft.jsonl"

_OPERATORS_RE = re.compile(r"&&|\|\||;|\||&|\n")
_STRIP_CHARS = "'\"(),;:"


# -- reading the trace ---------------------------------------------------------


def _read_trace(ws: str) -> list:
    path = os.path.join(ws, TRACE)
    if not os.path.isfile(path):
        return []
    events = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def _real_paths(ws: str) -> set:
    """Every real file under `ws`, named exactly as the directory holds it --
    never resolved through `os.path.isfile`, which folds case on a
    case-insensitive host (`spec/identity.md`)."""
    paths = set()
    for dirpath, dirnames, filenames in os.walk(ws):
        dirnames[:] = [d for d in dirnames if d != kernel.STORE]
        rel_dir = os.path.relpath(dirpath, ws)
        for fn in filenames:
            rel = fn if rel_dir in (".", "") else f"{rel_dir.replace(os.sep, '/')}/{fn}"
            paths.add(rel)
    return paths


def _command_tokens(cmd: str) -> list:
    tokens = []
    for segment in _OPERATORS_RE.split(cmd):
        for tok in segment.split():
            tok = tok.strip(_STRIP_CHARS)
            if tok:
                tokens.append(tok)
    return tokens


# -- classifying trace-derived candidates --------------------------------------


def _classify(ws: str, events: list, outputs: list, claim=None, generated=None):
    """Which paths a session's trace, plus any explicit override, names as
    pinned inputs versus generated outputs. Declaration always wins: an
    explicit `claim=`/`generated=` entry overrides whatever the trace alone
    would suggest; a declared verdict output is never a candidate either way."""
    outputs_set = set(outputs)
    write_paths = {e["path"] for e in events if e.get("event") == "write" and "path" in e}
    read_paths = {e["path"] for e in events if e.get("event") == "read" and "path" in e}
    bash_cmds = [e["cmd"] for e in events if e.get("event") == "bash" and "cmd" in e]

    real = _real_paths(ws)
    token_paths = set()
    for cmd in bash_cmds:
        token_paths |= {t for t in _command_tokens(cmd) if t in real}

    claimed = set(claim or [])
    generated_final = (write_paths | set(generated or [])) - claimed - outputs_set
    inputs_final = (read_paths | token_paths | claimed) - generated_final - outputs_set
    return sorted(inputs_final), sorted(generated_final)


def _cost(events: list) -> dict:
    """One oracle call per prompt, the trace's own span."""
    calls = sum(1 for e in events if e.get("event") == "prompt")
    stamps = [e["ts"] for e in events if "ts" in e]
    seconds = (max(stamps) - min(stamps)) if len(stamps) >= 2 else 0.0
    return {"calls": calls, "seconds": seconds}


# -- propose: a dry-run draft, no files touched --------------------------------


def propose(ws: str, outputs: list, name=None, *, claim=None, generated=None) -> dict:
    """What `build_claim` would declare, without building anything."""
    events = _read_trace(ws)
    inputs, gen = _classify(ws, events, outputs, claim=claim, generated=generated)
    return {"claim": {"name": name, "inputs": inputs}, "generated": gen}


# -- build_claim: cold certification -------------------------------------------


def build_claim(ws: str, outputs: list, dest: str, *, name=None,
                 claim=None, generated=None) -> dict:
    """Certify a session's claim cold: classify, confine, refuse the vacuous,
    then rebuild in a fresh room and require every gate to re-earn its
    verdict there before sealing."""
    events = _read_trace(ws)
    inputs, gen = _classify(ws, events, outputs, claim=claim, generated=generated)

    # confine every trace-derived path BEFORE copying anything
    for p in inputs + gen:
        _util.safe_path(ws, p)

    bash_cmds = [e["cmd"] for e in events if e.get("event") == "bash" and "cmd" in e]
    if not bash_cmds:
        raise kernel.ClaimError("build_claim: no gate command found in the trace")
    gate_cmd = bash_cmds[-1]

    generated_set = set(gen)
    deciders = kernel.gate_deciders(gate_cmd)
    if deciders and all(d in generated_set for d in deciders):
        raise kernel.ClaimError(
            f"build_claim: the gate is vacuous -- every decider is generated: {deciders}")

    produce_steps = [
        {"kind": "produce", "output": p, "class": "generated",
         "guidance": f"regenerate {p} to pass the gate"}
        for p in gen
    ]
    gate_steps = [{"kind": "gate", "output": o, "run": gate_cmd, "class": "validated"}
                  for o in outputs]
    claim_table = {
        "name": name or os.path.basename(os.path.normpath(dest)),
        "format": 3,
        "inputs": inputs,
    }
    recipe = {"claim": claim_table, "step": produce_steps + gate_steps}

    if os.path.isdir(dest) and os.listdir(dest):
        raise kernel.ClaimError(f"build_claim: destination is not empty: {dest!r}")
    os.makedirs(dest, exist_ok=True)

    for p in inputs:
        src = _util.safe_path(ws, p)
        dst = os.path.join(dest, p)
        os.makedirs(os.path.dirname(dst) or dest, exist_ok=True)
        shutil.copy2(src, dst)

    for p in gen:
        src = _util.safe_path(ws, p)
        dst = os.path.join(dest, p)
        os.makedirs(os.path.dirname(dst) or dest, exist_ok=True)
        shutil.copy2(src, dst)

    recipe_path = os.path.join(dest, kernel.RECIPE)
    with open(recipe_path, "w", encoding="utf-8") as f:
        f.write(render.dump_recipe(recipe))

    warm_bytes = {}
    for o in outputs:
        src = os.path.join(ws, o)
        if os.path.isfile(src):
            warm_bytes[o] = kernel._hash_file(_util.safe_path(ws, o))

    parsed = kernel.load_recipe(dest)
    outcome = kernel.run_gate(gate_cmd, dest, parsed)
    if outcome["status"] != "ok":
        raise kernel.ClaimError(
            f"build_claim: the gate did not reproduce cold: {outcome['status']}")
    for o in outputs:
        target = _util.safe_path(dest, o)
        if not os.path.isfile(target):
            raise kernel.ClaimError(f"build_claim: the gate did not produce {o!r} cold")
        fresh = kernel._hash_file(target)
        if o in warm_bytes and fresh != warm_bytes[o]:
            raise kernel.ClaimError(
                f"build_claim: verdict {o!r} does not reproduce cold "
                "(a nondeterministic gate cannot seal)")

    manifest = kernel.seal(dest)

    cost = _cost(events)
    kernel.ledger(dest, {"event": "author", "calls": cost["calls"], "seconds": cost["seconds"]})

    return {"ok": True, "root": manifest["root"], "name": manifest["name"]}
