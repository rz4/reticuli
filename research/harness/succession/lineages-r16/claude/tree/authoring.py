"""authoring: sessions become claims (`spec/layers.md`).

`propose` senses a candidate claim from a traced session: which files the
session's own bash commands and reads name, matched against what the
filesystem actually holds -- by walking the tree into a plain set of
relative paths and testing membership in it, never by asking the
filesystem whether a NAME exists (`os.path.isfile` folds case on macOS and
Windows, and `spec/identity.md` records the session that got burned by it).

`build_claim` certifies cold: it confines every trace-derived path to the
session BEFORE copying anything (a read that escaped the workspace must
never reach the claim it is refused from), classifies each file as
`generated` (written by the session, or named by the caller's own
`generated=`) or pinned `inputs` (sensed by `propose`, read by the session,
or named by the caller's own `claim=`), refuses a gate whose every decider
is itself generated (the vacuous-gate rule, `spec/claim-format.md`), seals,
and then re-earns every gate fresh in a cold judging room
(`kernel.audit`) -- a verdict the bytes cannot reproduce right now is not a
claim. Only once that holds does it account the session's own cost as the
claim's C1: one oracle call per traced prompt, over the trace's own
timestamp span.
"""
import json
import os
import shutil

from reticuli import kernel
from reticuli import render
from reticuli import _util

TRACE = ".reticuli/draft.jsonl"


def _read_trace(ws: str) -> list:
    """Every event appended to `ws`'s own session trace, in order."""
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


def _real_files(ws: str) -> set:
    """Every ordinary file under `ws`, as a forward-slash relative path,
    found by walking the filesystem -- the set a candidate name is tested
    against, never a filesystem call that can fold its case."""
    out = set()
    for dirpath, dirnames, filenames in os.walk(ws):
        dirnames[:] = [d for d in dirnames if d != kernel.STORE]
        rel_dir = os.path.relpath(dirpath, ws)
        for fname in filenames:
            rel = fname if rel_dir in (".", "") else f"{rel_dir}/{fname}"
            out.add(rel.replace(os.sep, "/"))
    return out


def _command_tokens(cmd: str) -> list:
    import shlex
    try:
        return shlex.split(cmd)
    except ValueError:
        return cmd.split()


def propose(ws: str, outputs: list, name: str) -> dict:
    """Sense a proposed claim from `ws`'s traced session: every file the
    trace's reads and bash commands name, that the filesystem actually
    holds under that exact name, excluding whatever the session itself
    wrote and the declared `outputs`."""
    events = _read_trace(ws)
    written = {e["path"] for e in events if e.get("event") == "write"}
    read_paths = {e["path"] for e in events if e.get("event") == "read"}
    real = _real_files(ws)

    candidates = set(read_paths)
    for event in events:
        if event.get("event") == "bash":
            for token in _command_tokens(event.get("cmd", "")):
                if token in real:
                    candidates.add(token)

    candidates -= written
    candidates -= set(outputs)

    return {"claim": {"name": name, "inputs": sorted(candidates)}}


def build_claim(ws: str, outputs: list, into: str, *, name: str = None,
                 claim: list = None, generated: list = None) -> dict:
    """Certify `ws`'s traced session cold into a fresh claim at `into`."""
    ws = os.path.abspath(ws)
    into = os.path.abspath(into)
    events = _read_trace(ws)

    # Finding 2: confine every trace-derived path BEFORE any byte moves.
    for event in events:
        if event.get("event") in ("read", "write"):
            _util.safe_path(ws, event["path"])

    claim_name = name or os.path.basename(into)
    proposal = propose(ws, outputs, claim_name)

    written = {e["path"] for e in events if e.get("event") == "write"}
    claimed = set(claim or [])
    forced_generated = set(generated or [])

    generated_files = sorted((written | forced_generated) - claimed)
    inputs = sorted((set(proposal["claim"]["inputs"]) | claimed)
                     - set(generated_files))

    bash_cmds = [e["cmd"] for e in events if e.get("event") == "bash"]
    run_cmd = " && ".join(bash_cmds)
    if not run_cmd:
        raise kernel.ClaimError("build_claim needs at least one traced bash command")

    steps = [
        {"kind": "produce", "output": g, "class": "generated",
         "guidance": f"regenerate {g} to pass the gate"}
        for g in generated_files
    ]
    for out in outputs:
        steps.append({"kind": "gate", "output": out, "class": "validated",
                       "run": run_cmd})

    recipe = {"claim": {"name": claim_name, "format": 3, "inputs": inputs},
               "step": steps}

    vacuous = kernel.vacuous_gates(recipe)
    if vacuous:
        raise kernel.ClaimError(
            f"refused vacuous gate(s) whose every decider is generated: {vacuous!r}")

    if os.path.exists(into) and os.listdir(into):
        raise kernel.ClaimError(f"refused non-empty claim target: {into!r}")
    os.makedirs(into, exist_ok=True)

    with open(os.path.join(into, kernel.RECIPE), "w", encoding="utf-8") as f:
        f.write(render.dump_recipe(recipe))

    for path in inputs:
        _util.copy_into(_util.safe_path(ws, path), os.path.join(into, path))
    for path in generated_files:
        source = _util.safe_path(ws, path)
        if os.path.isfile(source):
            _util.copy_into(source, os.path.join(into, path))
    for out in outputs:
        source = _util.safe_path(ws, out)
        if os.path.isfile(source):
            _util.copy_into(source, os.path.join(into, out))

    kernel.seal(into)

    aud = kernel.audit(into)
    if not aud["ok"]:
        shutil.rmtree(into, ignore_errors=True)
        raise kernel.ClaimError(
            f"build_claim must refuse a verdict it cannot re-earn cold: {aud!r}")

    prompts = sum(1 for e in events if e.get("event") == "prompt")
    timestamps = [e["ts"] for e in events if "ts" in e]
    seconds = (max(timestamps) - min(timestamps)) if timestamps else 0.0
    kernel.ledger(into, {"event": "oracle", "calls": prompts, "seconds": seconds})

    manifest = kernel.read_manifest(into)
    return {"ok": True, "root": manifest["root"], "name": manifest["name"]}
