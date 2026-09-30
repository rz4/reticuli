"""reticuli.authoring -- sessions become claims (`spec/layers.md`).

`propose` reads a session's trace (`TRACE`, under the workspace's store)
and drafts a recipe from it: a produce step for everything the trace
shows was written, a gate step over the declared verdict outputs, and
everything else the gate touches pinned as an input. `build_claim`
carries that draft to a seal, but trusts nothing in the trace to do it --
the trace has no authority (`spec/claim-format.md`). It confines every
trace-derived path before touching it, refuses a gate whose every decider
is generated (vacuous -- `claim=`/`generated=` let a caller declare the
boundary the trace cannot), and re-certifies every gate COLD in a fresh
room before sealing: a verdict that does not reproduce from the bytes
(a nondeterministic gate) is refused, never carried in. Gates run only
through `kernel.run_gate` -- scrubbed, sandboxed, bounded -- never
`kernel.sandbox` directly. The session's own cost (one oracle call per
prompt, the trace's timestamp span) becomes the claim's first ledger
entry, its C1.
"""
import json
import os
import re
import shlex
import shutil
import tempfile

from . import _util
from . import kernel
from . import render

TRACE = ".reticuli/draft.jsonl"

_REDIRECT_RE = re.compile(r'(?:>>|>)\s*(\S+)')


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


def _bash_events(events: list) -> list:
    return [e for e in events if e.get("event") == "bash" and "cmd" in e]


def _redirect_targets(cmd: str) -> list:
    return [m.group(1).strip("'\"") for m in _REDIRECT_RE.finditer(cmd)]


def _tokens(cmd: str) -> list:
    try:
        return shlex.split(cmd)
    except ValueError:
        return cmd.split()


def _exists_case_exact(base: str, rel: str) -> bool:
    """Whether `rel` names a real file under `base`, matched component by
    component against the directory's actual entries -- never folded by
    a case-insensitive filesystem (`spec/identity.md`)."""
    if not rel or os.path.isabs(rel) or ".." in rel.split("/"):
        return False
    cur = base
    for part in rel.split("/"):
        try:
            entries = os.listdir(cur)
        except OSError:
            return False
        if part not in entries:
            return False
        cur = os.path.join(cur, part)
    return os.path.isfile(cur)


def _check_confinement(ws: str, events: list) -> None:
    """Refuse any trace-derived path that escapes the session, before
    anything is copied anywhere."""
    for e in events:
        path = e.get("path")
        if path:
            _util.safe_path(ws, path)


def _assemble_recipe(ws: str, outputs, name: str, claim_names: set, generated_names: set):
    """A draft recipe from `ws`'s trace: a gate step per declared output,
    a produce step for everything the trace shows was written, and
    everything else the gate touches pinned as an input -- unless
    `claim_names` / `generated_names` declare otherwise. Declaration
    always wins over provenance: what a hook happened to observe is a
    default, not an authority."""
    events = _read_trace(ws)
    _check_confinement(ws, events)

    bashes = _bash_events(events)
    if not bashes:
        raise kernel.ClaimError(f"no traced command found to certify {list(outputs)!r}")
    run = bashes[-1]["cmd"]
    gate_steps = [{"kind": "gate", "output": o, "class": "validated", "run": run} for o in outputs]

    write_paths = {e["path"] for e in events if e.get("event") == "write" and "path" in e}
    candidates = set(write_paths)
    for tok in _tokens(run):
        if not tok or tok.startswith("-") or tok in outputs:
            continue
        if _exists_case_exact(ws, tok):
            candidates.add(tok)
    candidates |= claim_names | generated_names
    candidates -= set(outputs)

    inputs = []
    produce_steps = []
    for n in sorted(candidates):
        if n in generated_names:
            produce_steps.append({"kind": "produce", "output": n, "class": "generated"})
        elif n in claim_names:
            inputs.append(n)
        elif n in write_paths:
            produce_steps.append({"kind": "produce", "output": n, "class": "generated"})
        else:
            inputs.append(n)

    recipe = {"claim": {"name": name, "inputs": inputs}, "step": produce_steps + gate_steps}
    return recipe, events


def propose(ws: str, outputs, name: str, *, claim=None, generated=None) -> dict:
    """Draft a recipe from `ws`'s trace -- no cold certification, no
    seal, just a sensing of what the session's claim would look like."""
    recipe, _events = _assemble_recipe(ws, outputs, name, set(claim or []), set(generated or []))
    return recipe


def _write_recipe(d: str, recipe: dict) -> None:
    path = os.path.join(d, kernel.RECIPE)
    with open(path, "w", encoding="utf-8") as f:
        f.write(render.dump_recipe(recipe))


def build_claim(ws: str, outputs, rec: str, *, name: str, claim=None, generated=None) -> dict:
    """Certify `ws`'s session cold and seal it at `rec`.

    The trace names candidates; it authorizes nothing. Every gate is
    re-run in a fresh room, cold, and every declared verdict must
    reproduce byte-for-byte before anything is sealed -- a gate whose
    output does not reproduce (a nondeterministic gate) is refused.
    A gate whose every decider is generated bytes is refused as vacuous
    before any of that runs.
    """
    claim_names = set(claim or [])
    generated_names = set(generated or [])
    recipe, events = _assemble_recipe(ws, outputs, name, claim_names, generated_names)

    gate_steps = [s for s in recipe["step"] if s["kind"] == "gate"]
    produce_steps = [s for s in recipe["step"] if s["kind"] == "produce"]
    inputs = recipe["claim"]["inputs"]

    vacuous = set(kernel.vacuous_gates(recipe))
    hit = [s["output"] for s in gate_steps if s["output"] in vacuous]
    if hit:
        raise kernel.ClaimError(
            f"gate(s) {hit} are vacuous: every decider is generated, unclaimed bytes -- "
            "declare the check with claim=, or the implementation with generated=")

    room = tempfile.mkdtemp(prefix="reticuli-build-")
    try:
        for n in inputs:
            _util.copy_into(room, n, _util.safe_path(ws, n))
        for step in produce_steps:
            _util.copy_into(room, step["output"], _util.safe_path(ws, step["output"]))

        for step in gate_steps:
            result = kernel.run_gate(step["run"], room, recipe)
            if result["status"] != "ok":
                raise kernel.ClaimError(
                    f"gate {step['output']!r} did not run clean cold: {result['status']}")
            original = _util.safe_path(ws, step["output"])
            candidate = os.path.join(room, step["output"])
            reproduced = (
                os.path.isfile(original) and os.path.isfile(candidate)
                and _util.hash_bytes(open(original, "rb").read())
                == _util.hash_bytes(open(candidate, "rb").read())
            )
            if not reproduced:
                raise kernel.ClaimError(
                    f"gate {step['output']!r} did not reproduce cold: a verdict that cannot "
                    "be re-earned from the bytes cannot be sealed")

        os.makedirs(rec, exist_ok=True)
        for n in inputs:
            _util.copy_into(rec, n, os.path.join(room, n))
        for step in produce_steps:
            _util.copy_into(rec, step["output"], os.path.join(room, step["output"]))
        for step in gate_steps:
            _util.copy_into(rec, step["output"], os.path.join(room, step["output"]))
        _write_recipe(rec, recipe)
        manifest = kernel.seal(rec)
    finally:
        shutil.rmtree(room, ignore_errors=True)

    event = {"event": "oracle", "calls": sum(1 for e in events if e.get("event") == "prompt")}
    timestamps = [e["ts"] for e in events if isinstance(e.get("ts"), (int, float))]
    if len(timestamps) >= 2:
        event["seconds"] = max(timestamps) - min(timestamps)
    kernel.ledger(rec, event)

    return {"ok": True, **manifest}
