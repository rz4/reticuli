"""authoring: sessions become claims (spec/layers.md).

A session leaves a trace (`TRACE`, one JSON object per line: prompts,
traced reads/writes, bash commands) under the workspace it worked in.
`propose` reads that trace and drafts a recipe: what the session wrote is
generated, what it read or referenced from the shell -- and that still
exists on disk, case and all -- is a pinned input, unless the caller
overrides the classification with `claim=`/`generated=`. Declaration never
yields to inference: provenance (who wrote a byte) never decides its class.

`build_claim` takes that draft and CERTIFIES IT COLD: every declared path
is confined to the workspace before anything is copied, a gate whose every
decider is generated is refused as vacuous, and every gate is re-run in a
fresh room built from nothing but the pinned bytes -- a verdict that does
not reproduce there (a nondeterministic gate) never seals. Gates run only
through `kernel.run_gate`, never `kernel.sandbox` directly, so the scrub
and the bound always apply.
"""
import json
import os
import re
import shlex
import shutil
import tempfile

from reticuli import kernel, _util, render

TRACE = ".reticuli/draft.jsonl"

_REDIRECTS = ("2>>", "2>", ">>", "<", ">")


# -- reading a session's trace -----------------------------------------

def _read_trace(ws: str) -> list:
    path = os.path.join(ws, TRACE)
    if not os.path.isfile(path):
        raise kernel.ClaimError(f"no session trace found at {path!r}")
    events = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


# -- what a bash command references, exactly as the filesystem spells it
#    (spec/identity.md: identity must not follow the filesystem) ------------

def _split_subcommands(cmd: str) -> list:
    return [s for s in re.split(r"\|\||&&|[&|;]", cmd) if s.strip()]


def _candidate_tokens(sub: str) -> list:
    try:
        tokens = shlex.split(sub)
    except ValueError:
        return []
    out = []
    skip_next = False
    for tok in tokens:
        if skip_next:
            skip_next = False
            continue
        if tok in _REDIRECTS:
            skip_next = True
            continue
        if tok.startswith("-"):
            continue
        out.append(tok)
    return out


def _exists_exact(base: str, rel: str) -> bool:
    """Does `rel` name a real file under `base`, every path component
    matching a real directory entry exactly? `os.path.isfile` folds case
    on macOS and Windows; a shell token is no input unless it matches a
    real directory entry, case and all."""
    if not rel or os.path.isabs(rel):
        return False
    parts = rel.replace("\\", "/").split("/")
    if any(p in ("", "..", ".") for p in parts):
        return False
    cur = base
    for part in parts:
        try:
            entries = os.listdir(cur)
        except OSError:
            return False
        if part not in entries:
            return False
        cur = os.path.join(cur, part)
    return os.path.isfile(cur) and not os.path.islink(cur)


def _bash_candidates(ws: str, bash_cmds: list) -> set:
    found = set()
    for cmd in bash_cmds:
        for sub in _split_subcommands(cmd):
            for tok in _candidate_tokens(sub):
                if _exists_exact(ws, tok):
                    found.add(tok)
    return found


# -- drafting a claim from the trace -------------------------------------

def _classify(ws: str, outputs: list, name: str, claim=None, generated=None) -> dict:
    events = _read_trace(ws)
    written = {e["path"] for e in events
               if e.get("event") == "write" and isinstance(e.get("path"), str)}
    traced_reads = {e["path"] for e in events
                    if e.get("event") == "read" and isinstance(e.get("path"), str)}
    bash_cmds = [e["cmd"] for e in events
                 if e.get("event") == "bash" and isinstance(e.get("cmd"), str)]
    if not bash_cmds:
        raise kernel.ClaimError("no gate command recorded in the session trace")
    gate_cmd = bash_cmds[-1]

    claim_set = set(claim or [])
    generated_set = set(generated or [])
    output_set = set(outputs)

    candidate_inputs = traced_reads | _bash_candidates(ws, bash_cmds)

    final_generated = ((written - claim_set) | generated_set) - output_set
    final_inputs = ((candidate_inputs - final_generated) | claim_set) - output_set

    # the confinement boundary: validated before a single byte is copied
    for path in sorted(final_inputs | final_generated | output_set):
        _util.safe_path(ws, path)

    steps = [{"kind": "produce", "output": p, "class": "generated",
              "guidance": f"regenerate {p} to pass the gate"}
             for p in sorted(final_generated)]
    steps.extend({"kind": "gate", "output": o, "class": "validated", "run": gate_cmd}
                 for o in outputs)

    return {"claim": {"name": name, "format": 3, "inputs": sorted(final_inputs)},
            "step": steps}


def propose(ws: str, outputs: list, name: str, claim=None, generated=None) -> dict:
    """Draft a claim from `ws`'s session trace: what it wrote is generated,
    what it read or referenced that still exists (case and all) is a
    pinned input, `outputs` are the gate's own declared verdicts."""
    return _classify(ws, outputs, name, claim, generated)


# -- cold certification: the trace has no authority ----------------------

def build_claim(ws: str, outputs: list, into: str, name: str,
                 claim=None, generated=None) -> dict:
    """Certify `ws`'s session cold and materialize the sealed claim at
    `into`. Refuses a vacuous gate, refuses a traced path that escapes
    `ws` before copying anything, and refuses a verdict that does not
    reproduce in a fresh room built only from the pinned bytes."""
    recipe = _classify(ws, outputs, name, claim, generated)

    vacuous = kernel.vacuous_gates(recipe)
    bad = [o for o in outputs if o in vacuous]
    if bad:
        raise kernel.ClaimError(
            f"build_claim refuses a vacuous gate (every decider is generated): {bad}")

    events = _read_trace(ws)
    room = tempfile.mkdtemp(prefix="reticuli-build-")
    try:
        _util.copy_into(ws, room, recipe["claim"]["inputs"])
        produced = [s["output"] for s in recipe["step"] if s["kind"] == "produce"]
        _util.copy_into(ws, room, produced)
        with open(os.path.join(room, kernel.RECIPE), "w", encoding="utf-8") as f:
            f.write(render.dump_recipe(recipe))

        for step in recipe["step"]:
            if step["kind"] != "gate":
                continue
            res = kernel.run_gate(step["run"], room, recipe)
            if res["status"] != "ok":
                raise kernel.ClaimError(
                    f"build_claim refuses a gate that did not earn cold: "
                    f"{step['output']!r} ({res['status']})")
            warm = _util.safe_path(ws, step["output"])
            cold = _util.safe_path(room, step["output"])
            if not os.path.isfile(warm) or _util.hash_bytes(warm) != _util.hash_bytes(cold):
                raise kernel.ClaimError(
                    f"build_claim refuses a verdict that does not reproduce cold: "
                    f"{step['output']!r}")

        if os.path.exists(into):
            if os.listdir(into):
                raise kernel.ClaimError(f"refuses to build into a non-empty directory: {into!r}")
        else:
            os.makedirs(into)
        for entry in os.listdir(room):
            shutil.move(os.path.join(room, entry), os.path.join(into, entry))
    finally:
        shutil.rmtree(room, ignore_errors=True)

    prompts = sum(1 for e in events if e.get("event") == "prompt")
    timestamps = [e["ts"] for e in events if isinstance(e.get("ts"), (int, float))]
    if timestamps:
        _util.ledger_add(into, {"calls": prompts, "seconds": max(timestamps) - min(timestamps)})

    manifest = kernel.seal(into)
    return {"ok": True, "root": manifest["root"], "name": manifest["name"]}
