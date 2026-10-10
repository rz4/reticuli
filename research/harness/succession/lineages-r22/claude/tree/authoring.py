"""Authoring: a coding session becomes a claim.

`propose` reads a session's trace and drafts a recipe from it -- a sketch,
never certified. `build_claim` does the real work: it reads the same
trace, confines every trace-derived path to the session BEFORE copying
anything, classifies each declared path as a pinned input or a generated
output (provenance suggests the class -- a traced write defaults to
generated -- but `claim=`/`generated=` always have the final word, since
the claim boundary is declared, not inferred), refuses a vacuous gate (one
whose every decider is itself generated), then certifies cold: it builds
the claim in a fresh room from exactly its declared bytes, runs every gate
there through `kernel.run_gate` (never `kernel.sandbox` directly), seals,
and re-audits once more to refuse any verdict that does not reproduce --
the session's say-so is not the claim's authority, re-earning it is. A
built claim's ledger carries the session's own cost as its C1: one oracle
call per prompt, the wall-clock span the trace covers.
"""
import json
import os
import shlex
import shutil

from . import kernel
from . import render

TRACE = ".reticuli/draft.jsonl"


def _read_trace(ws: str) -> list:
    path = os.path.join(ws, TRACE)
    if not os.path.isfile(path):
        return []
    events = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except ValueError:
                continue
    return events


def _confine(path) -> None:
    """Refuse a trace-derived path that escapes the session, lexically --
    no absolute path, no empty or `.`/`..` component -- before it is ever
    read or copied."""
    if not isinstance(path, str) or not path:
        raise kernel.ClaimError(f"refuses an empty trace-derived path: {path!r}")
    if os.path.isabs(path):
        raise kernel.ClaimError(f"trace-derived path escapes the session: {path!r}")
    parts = path.replace("\\", "/").split("/")
    if any(p in ("", ".", "..") for p in parts):
        raise kernel.ClaimError(f"trace-derived path escapes the session: {path!r}")


def _exists_exact(ws: str, rel: str) -> bool:
    """Does `rel` name a real file under `ws`, matching every path
    component's case exactly -- never folded by a case-insensitive
    filesystem (spec/identity.md: identity must not depend on the host
    filesystem)."""
    if not isinstance(rel, str) or not rel or os.path.isabs(rel):
        return False
    parts = rel.replace("\\", "/").split("/")
    if any(p in ("", ".", "..") for p in parts):
        return False
    cur = ws
    for part in parts:
        try:
            names = os.listdir(cur)
        except OSError:
            return False
        if part not in names:
            return False
        cur = os.path.join(cur, part)
    return os.path.isfile(cur) and not os.path.islink(cur)


def _candidate_tokens(cmd: str) -> set:
    """Every whitespace/quoting-delimited token of a traced gate command --
    a crude superset of the names it might reference. Filtered down to
    real inputs by `_exists_exact`, which is what actually decides."""
    try:
        return set(shlex.split(cmd))
    except ValueError:
        return set()


def _draft(ws: str, outputs, name: str, *, claim=None, generated=None):
    """Assemble a recipe dict from `ws`'s trace: the declared `claim`/
    `generated` overrides win; otherwise a traced write is generated and
    a token that names a real file (case exact) is a pinned input.
    Returns `(recipe, generated_set)`."""
    events = _read_trace(ws)
    bash_cmds = [e["cmd"] for e in events if e.get("event") == "bash" and e.get("cmd")]
    write_paths = {e["path"] for e in events if e.get("event") == "write" and e.get("path")}
    read_paths = {e["path"] for e in events if e.get("event") == "read" and e.get("path")}

    claim_set = set(claim or [])
    generated_set = (set(generated or []) | write_paths) - claim_set
    outputs_set = set(outputs)

    for p in write_paths | read_paths | claim_set | generated_set | outputs_set:
        _confine(p)

    candidates = set(read_paths)
    for cmd in bash_cmds:
        candidates |= _candidate_tokens(cmd)

    inputs = set(claim_set)
    for p in candidates:
        if p in outputs_set or p in generated_set:
            continue
        if _exists_exact(ws, p):
            inputs.add(p)

    recipe = {"claim": {"name": name, "inputs": sorted(inputs)}, "step": []}

    for g in sorted(generated_set):
        recipe["step"].append({
            "kind": "produce", "output": g, "class": "generated",
            "guidance": f"regenerate {g}",
        })

    run = " && ".join(bash_cmds)
    for o in outputs:
        recipe["step"].append({
            "kind": "gate", "output": o, "class": "validated", "run": run,
        })

    return recipe, generated_set


def propose(ws: str, outputs, name: str) -> dict:
    """Draft a recipe from `ws`'s trace -- a sketch, never certified."""
    recipe, _ = _draft(ws, outputs, name)
    return {"claim": recipe["claim"], "step": recipe["step"]}


def _stage(ws: str, rec: str, relpath: str, *, required: bool) -> None:
    src = os.path.join(ws, relpath)
    if not os.path.isfile(src):
        if required:
            raise kernel.ClaimError(f"declared path is gone: {relpath!r}")
        return
    dst = os.path.join(rec, relpath)
    os.makedirs(os.path.dirname(dst) or rec, exist_ok=True)
    shutil.copy2(src, dst)


def _session_cost(events: list):
    calls = sum(1 for e in events if e.get("event") == "prompt")
    stamps = [e["ts"] for e in events
              if isinstance(e.get("ts"), (int, float)) and not isinstance(e.get("ts"), bool)]
    seconds = (max(stamps) - min(stamps)) if len(stamps) >= 2 else 0.0
    return calls, seconds


def build_claim(ws: str, outputs, rec: str, *, name: str, claim=None, generated=None) -> dict:
    """Certify `ws`'s session into a claim at `rec`, cold: build the
    claim's room from exactly its declared bytes, re-run every gate
    there, seal, and re-audit once more so an unreproducible verdict
    (a nondeterministic gate) refuses rather than seals."""
    recipe, generated_set = _draft(ws, outputs, name, claim=claim, generated=generated)
    inputs = recipe["claim"]["inputs"]

    vacuous = kernel.vacuous_gates(recipe)
    if vacuous:
        raise kernel.ClaimError(
            f"build_claim refuses a vacuous gate (every decider is generated): {vacuous}")

    os.makedirs(rec, exist_ok=True)
    for p in inputs:
        _stage(ws, rec, p, required=True)
    for g in generated_set:
        _stage(ws, rec, g, required=False)

    with open(os.path.join(rec, kernel.RECIPE), "w", encoding="utf-8") as f:
        f.write(render.dump_recipe(recipe))

    for step in recipe["step"]:
        if step.get("kind") != "gate":
            continue
        output_path = os.path.join(rec, step["output"])
        if os.path.isfile(output_path):
            os.remove(output_path)
        result = kernel.run_gate(step["run"], rec, recipe)
        if result["status"] != "ok":
            raise kernel.ClaimError(
                f"build_claim: gate for {step['output']!r} did not earn its verdict "
                f"cold: {result}")
        if not os.path.isfile(output_path):
            raise kernel.ClaimError(
                f"build_claim: gate did not produce its declared verdict {step['output']!r}")

    manifest = kernel.seal(rec)
    audited = kernel.audit(rec)
    if not audited["ok"]:
        raise kernel.ClaimError(
            f"build_claim refuses a verdict that does not reproduce cold: {audited}")

    calls, seconds = _session_cost(_read_trace(ws))
    kernel.ledger(rec, {"event": "session", "calls": calls, "seconds": seconds})

    return {"ok": True, "root": manifest["root"], "name": manifest["name"]}
