"""Authoring: turning a traced session into a claim (spec/layers.md's
authoring layer).

`propose` reads a session's trace (`TRACE`, under the workspace's store) and
drafts a recipe from it: a path the trace recorded as written is a
candidate `generated` output; any other path the trace or its bash commands
referenced is a candidate `pinned` input -- always matched against the
REAL directory entries present, case and all, never through a filesystem
call that folds case (`spec/identity.md`: identity must not depend on the
host filesystem). `build_claim` takes that draft further: it refuses a
vacuous gate, confines every candidate path to the session before copying
anything, and certifies the draft COLD -- sealing a scratch room and
auditing it (`kernel.audit`) so a verdict that does not re-earn itself
(a nondeterministic gate) never becomes a claim. Session cost becomes the
claim's own C1: one oracle call per prompt, the trace's own time span.

Gates run only through `kernel.audit`, which itself runs only through
`kernel.run_gate` -- never `kernel.sandbox` directly.
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

_OPSPLIT = re.compile(r'\|\||&&|[;&|\n]')
_REDIRECTS = ("<", ">", ">>", "2>", "2>>", "&>")


# --------------------------------------------------------------- trace --

def _read_trace(ws: str) -> list:
    path = os.path.join(ws, TRACE)
    events = []
    if not os.path.isfile(path):
        return events
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def _real_entries(ws: str) -> set:
    """Every real file under `ws`, named exactly as the directory holds it
    -- case included -- excluding the store. A candidate must match one of
    these entries by plain string equality, never by a filesystem call
    that folds case on this host."""
    entries = set()
    for root, dirs, files in os.walk(ws):
        dirs[:] = [d for d in dirs if d != ".reticuli"]
        for fn in files:
            rel = os.path.relpath(os.path.join(root, fn), ws)
            entries.add(rel.replace(os.sep, "/"))
    return entries


def _referenced_tokens(cmd: str) -> list:
    """The bare-word arguments of a bash command -- not the command name
    itself, not a flag, not a flag's own redirection target -- that might
    name a real file."""
    out = []
    for sub in _OPSPLIT.split(cmd):
        sub = sub.strip()
        if not sub:
            continue
        try:
            tokens = shlex.split(sub)
        except ValueError:
            continue
        skip_next = False
        for i, tok in enumerate(tokens):
            if skip_next:
                skip_next = False
                continue
            if tok in _REDIRECTS:
                skip_next = True
                continue
            if i == 0:
                continue
            if tok.startswith("-"):
                continue
            out.append(tok)
    return out


# -------------------------------------------------------------- drafting --

def _confine(ws: str, path: str) -> None:
    try:
        _util.safe_path(ws, path)
    except ValueError as exc:
        raise kernel.ClaimError(
            f"refuses a path that escapes the session: {path!r}: {exc}") from exc


def _draft_recipe(ws: str, outputs: list, name: str, *,
                   claim: list = None, generated: list = None) -> dict:
    events = _read_trace(ws)
    written = {e.get("path") for e in events if e.get("event") == "write" and e.get("path")}
    read_paths = {e.get("path") for e in events if e.get("event") == "read" and e.get("path")}
    bash_cmds = [e.get("cmd") for e in events if e.get("event") == "bash" and e.get("cmd")]

    real_entries = _real_entries(ws)
    token_candidates = set()
    for cmd in bash_cmds:
        token_candidates |= set(_referenced_tokens(cmd))
    token_candidates &= real_entries

    claim_set = set(claim or [])
    generated_set = set(generated or [])

    candidates = written | token_candidates | read_paths | claim_set | generated_set
    candidates -= set(outputs or [])

    for p in candidates:
        _confine(ws, p)

    classes = {}
    for p in candidates:
        if p in generated_set:
            classes[p] = "generated"
        elif p in claim_set:
            classes[p] = "pinned"
        elif p in written:
            classes[p] = "generated"
        else:
            classes[p] = "pinned"

    pinned_inputs = sorted(p for p, c in classes.items() if c == "pinned")
    generated_outputs = sorted(p for p, c in classes.items() if c == "generated")

    if not bash_cmds:
        raise kernel.ClaimError("build_claim refuses a session with no bash gate event")
    gate_cmd = bash_cmds[-1]

    steps = []
    for p in generated_outputs:
        steps.append({"kind": "produce", "output": p, "class": "generated",
                      "guidance": f"regenerate {p} to pass the gate"})
    for out_name in (outputs or []):
        steps.append({"kind": "gate", "output": out_name, "class": "validated", "run": gate_cmd})

    claim_tbl = {"name": name, "format": 3, "inputs": pinned_inputs}
    return {"claim": claim_tbl, "step": steps}


def propose(ws: str, outputs: list, name: str, *,
            claim: list = None, generated: list = None) -> dict:
    """Draft a recipe from a traced session -- never built, never sealed."""
    return _draft_recipe(ws, outputs, name, claim=claim, generated=generated)


# ------------------------------------------------------------ certifying --

def _populate(ws: str, scratch: str, recipe: dict) -> None:
    for p in recipe["claim"].get("inputs", []):
        src = os.path.join(ws, p)
        if os.path.isfile(src) or os.path.isdir(src):
            _util.copy_into(src, os.path.join(scratch, p))
    for step in recipe["step"]:
        if step["kind"] not in ("produce", "gate"):
            continue
        src = os.path.join(ws, step["output"])
        if os.path.isfile(src):
            _util.copy_into(src, os.path.join(scratch, step["output"]))


def _trace_cost(ws: str) -> dict:
    events = _read_trace(ws)
    n_prompts = sum(1 for e in events if e.get("event") == "prompt")
    tss = [e["ts"] for e in events
           if isinstance(e.get("ts"), (int, float)) and not isinstance(e.get("ts"), bool)]
    entry = {"calls": n_prompts}
    if len(tss) >= 2:
        entry["seconds"] = max(tss) - min(tss)
    return entry


def build_claim(ws: str, outputs: list, rec: str, *, name: str,
                 claim: list = None, generated: list = None) -> dict:
    """Propose a recipe from the session at `ws`, then certify it COLD: a
    scratch room is sealed from the declared bytes and audited
    (`kernel.audit`), so only a verdict that re-earns itself becomes `rec`."""
    recipe = _draft_recipe(ws, outputs, name, claim=claim, generated=generated)

    vacuous = kernel.vacuous_gates(recipe)
    if vacuous:
        raise kernel.ClaimError(
            f"build_claim refuses a vacuous gate (every decider is generated): {vacuous}")

    scratch = tempfile.mkdtemp(prefix="reticuli-build-")
    try:
        _populate(ws, scratch, recipe)
        with open(os.path.join(scratch, kernel.RECIPE), "w", encoding="utf-8") as f:
            f.write(render.dump_recipe(recipe))

        kernel.seal(scratch)

        audited = kernel.audit(scratch)
        if not audited["ok"]:
            raise kernel.ClaimError(
                "build_claim refuses: the session's verdict does not re-earn "
                f"cold: {audited.get('verdict')}")

        kernel.ledger(scratch, _trace_cost(ws))

        if os.path.exists(rec):
            raise kernel.ClaimError(f"build_claim refuses a non-empty destination: {rec!r}")
        os.makedirs(os.path.dirname(rec) or ".", exist_ok=True)
        shutil.copytree(scratch, rec)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    verified = kernel.verify(rec)
    return {"ok": verified["ok"], "root": verified["root"]}
