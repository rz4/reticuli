"""authoring: sessions become claims (`spec/layers.md`).

`propose` reads a coding session's trace and previews the claim it would
make -- which files it would pin as inputs, which it would leave generated,
what gate it would certify -- without touching the filesystem beyond the
session itself. `build_claim` does the same derivation and then actually
seals it: it stages a fresh claim directory, and before trusting the
session's own verdict it re-earns it COLD, through `kernel.audit`, in a
room the session never touched. A verdict the bytes cannot reproduce --a
nondeterministic gate, chiefly-- refuses to become a claim.

Declaration decides step class, never provenance: a file the session wrote
defaults to `generated` (the implementation), but `claim=` pins it as an
input regardless (the README flow, where the agent writes both the solver
and its own check), and `generated=` marks a file no hook ever saw written
as the implementation anyway (a human driving the session by hand, with
only bash events in the trace). A gate every one of whose deciding files is
itself generated is refused as vacuous -- it would pin a verdict that no
claimed byte could ever fail.

Every trace-derived path is confined to the session directory before
anything is copied: a traced read or write outside the session is refused
at that boundary, never materialized first and refused only once a seal
is attempted.

Stdlib only.
"""
import json
import os
import shlex
import shutil

from . import kernel
from . import render
from . import _util

# the session's own record of what happened -- prompts, writes, reads, and
# the shell commands run, one JSON object per line.
TRACE = ".reticuli/draft.jsonl"

_GUIDANCE_FMT = "regenerate {output} to pass the gate"


def _confine(ws: str, path) -> None:
    """Refuse, before any copy, a trace-derived path that escapes the
    session directory -- the confinement boundary `finding 2` closed."""
    if not path:
        return
    try:
        _util.safe_path(ws, path)
    except ValueError as exc:
        raise kernel.ClaimError(
            f"a traced path escapes the session: {path!r}: {exc}") from exc


def _read_trace(ws: str) -> list:
    path = os.path.join(ws, TRACE)
    if not os.path.isfile(path):
        raise kernel.ClaimError(f"no session trace at {path!r}")
    events = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def _real_relpath(ws: str, token: str):
    """Whether `token` names a real file inside `ws`, matched component by
    component against the directory entries actually present -- case and
    all, never resolved through a case-folding filesystem call."""
    if not token or token.startswith(("-", "/")):
        return None
    parts = token.split("/")
    if not parts or any(p in ("", "..", ".") for p in parts):
        return None
    cur = os.path.realpath(ws)
    for part in parts:
        try:
            entries = os.listdir(cur)
        except OSError:
            return None
        if part not in entries:
            return None
        cur = os.path.join(cur, part)
    if not os.path.isfile(cur):
        return None
    return "/".join(parts)


def _derive(ws: str, outputs, name: str, *, claim=None, generated=None):
    """Read the session trace and compute the claim it proposes: the
    recipe dict, and the generated/input sets it was built from."""
    claim_override = set(claim or [])
    generated_override = set(generated or [])
    output_set = set(outputs)

    write_paths, read_paths, bash_cmds = set(), set(), []
    prompt_count = 0
    timestamps = []

    for event in _read_trace(ws):
        ts = event.get("ts")
        if isinstance(ts, (int, float)) and not isinstance(ts, bool):
            timestamps.append(ts)
        kind = event.get("event")
        if kind == "prompt":
            prompt_count += 1
        elif kind == "write":
            path = event.get("path")
            _confine(ws, path)
            if path:
                write_paths.add(path)
        elif kind == "read":
            path = event.get("path")
            _confine(ws, path)
            if path:
                read_paths.add(path)
        elif kind == "bash":
            cmd = event.get("cmd")
            if cmd:
                bash_cmds.append(cmd)

    combined_cmd = " && ".join(bash_cmds)

    generated_set = (write_paths | generated_override) - claim_override

    discovered = set()
    if combined_cmd:
        try:
            tokens = shlex.split(combined_cmd)
        except ValueError:
            tokens = []
        for token in tokens:
            rel = _real_relpath(ws, token)
            if rel and rel not in generated_set and rel not in output_set:
                discovered.add(rel)
    for path in read_paths:
        if path in generated_set or path in output_set:
            continue
        rel = _real_relpath(ws, path)
        if rel:
            discovered.add(rel)

    input_set = (discovered | claim_override) - generated_set - output_set

    produce_steps = []
    for path in sorted(generated_set):
        produce_steps.append({
            "kind": "produce",
            "output": path,
            "class": "generated",
            "guidance": _GUIDANCE_FMT.format(output=path),
        })

    gate_steps = [
        {"kind": "gate", "output": out, "class": "validated", "run": combined_cmd}
        for out in outputs
    ]

    claim_table = {"name": name, "inputs": sorted(input_set), "format": 3}
    recipe = {"claim": claim_table, "step": produce_steps + gate_steps}

    cost = None
    if timestamps:
        cost = {"calls": prompt_count, "seconds": max(timestamps) - min(timestamps)}

    return recipe, generated_set, input_set, cost


def propose(ws: str, outputs, name: str, *, claim=None, generated=None) -> dict:
    """Preview the claim a session's trace would make -- no filesystem
    change beyond reading the trace and probing which candidate paths are
    real directory entries."""
    recipe, _generated_set, _input_set, _cost = _derive(
        ws, outputs, name, claim=claim, generated=generated)
    return recipe


def build_claim(ws: str, outputs, dest: str, *, name: str, claim=None, generated=None) -> dict:
    """Derive a claim from a session's trace and seal it cold.

    Refuses, as a `kernel.ClaimError`: a trace-derived path that escapes
    the session; a gate whose every decider is a generated file (vacuous);
    and -- having staged the claim and sealed it -- a verdict that does not
    re-earn cold under `kernel.audit` (a nondeterministic gate).
    """
    recipe, generated_set, input_set, cost = _derive(
        ws, outputs, name, claim=claim, generated=generated)

    vacuous = kernel.vacuous_gates(recipe)
    if vacuous:
        raise kernel.ClaimError(
            f"refusing to seal a vacuous gate (every decider is generated): {vacuous!r}")

    os.makedirs(dest, exist_ok=True)
    try:
        recipe_path = os.path.join(dest, kernel.RECIPE)
        with open(recipe_path, "w", encoding="utf-8") as f:
            f.write(render.dump_recipe(recipe))

        names = sorted(input_set | generated_set | set(outputs))
        _util.copy_into(ws, dest, names=names)

        manifest = kernel.seal(dest)
        audited = kernel.audit(dest)
        if not audited["ok"]:
            raise kernel.ClaimError(
                "build_claim cannot certify cold: the session's verdict did not "
                f"re-earn under audit ({audited.get('verdict')})")

        if cost is not None:
            kernel.ledger(dest, {"event": "session", **cost})

        return {"ok": True, "root": manifest["root"], "name": manifest["name"], "claim": recipe}
    except BaseException:
        shutil.rmtree(dest, ignore_errors=True)
        raise
