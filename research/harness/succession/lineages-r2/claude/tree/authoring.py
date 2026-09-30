"""authoring: sessions become claims (spec/layers.md).

`propose` reads a session's own trace (`TRACE`, `.reticuli/draft.jsonl`) and
drafts a recipe from it -- which traced writes are the implementation
(`generated`), which traced reads and gate-command tokens are the pinned
check (`inputs`), which traced bash commands are the gate. Candidate names
are matched against the REAL directory listing, case and all: identity must
never depend on a filesystem that folds case, so a shell token is a
candidate input only when it names an actual entry, not merely when
`os.path.isfile` says yes (`spec/identity.md`).

`build_claim` certifies that draft cold: it confines every trace-derived
path before copying anything (a path that escapes the session is refused at
the boundary, never copied out on the way to that refusal), refuses a gate
whose every decider is itself generated (`kernel.vacuous_gates` -- the
README flow where an agent writes both the solver and its own check), then
re-runs the gate in a fresh, scrubbed, sandboxed room and requires it to
reproduce the session's own verdict byte-for-byte before sealing. The trace
has no authority of its own; only a cold re-earning does. Every gate this
module runs goes through `kernel.run_gate` -- never `kernel.sandbox`
directly -- so the scrub, the bound, and the sandbox are never bypassed.

Stdlib only.
"""
import json
import os
import re
import shlex
import shutil
import tempfile

from . import _util, kernel, render

TRACE = ".reticuli/draft.jsonl"

_SPLIT_RE = re.compile(r'\|\||&&|[&|;\n]')
_PUNCTUATION = frozenset({">", "<", ">>", "2>", "2>>", "|", "&", ";"})


# ---------------------------------------------------------------------------
# reading a session's own trace
# ---------------------------------------------------------------------------

def _read_trace(ws: str) -> list:
    path = os.path.join(ws, TRACE)
    if not os.path.isfile(path):
        raise kernel.ClaimError(f"no session trace at {path!r}")
    events = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def _scan_events(events: list) -> tuple:
    """`(write_paths, read_paths, bash_cmds)` -- the trace's own vocabulary
    of what happened, each already given verbatim by the hook that recorded
    it (no guessing, unlike a shell command's tokens)."""
    write_paths, read_paths, bash_cmds = set(), set(), []
    for e in events:
        kind = e.get("event")
        if kind == "write" and isinstance(e.get("path"), str):
            write_paths.add(e["path"])
        elif kind == "read" and isinstance(e.get("path"), str):
            read_paths.add(e["path"])
        elif kind == "bash" and isinstance(e.get("cmd"), str):
            bash_cmds.append(e["cmd"])
    return write_paths, read_paths, bash_cmds


def _tokens_in(cmd: str) -> list:
    tokens = []
    for seg in _SPLIT_RE.split(cmd):
        seg = seg.strip()
        if not seg:
            continue
        try:
            tokens.extend(shlex.split(seg))
        except ValueError:
            continue
    return tokens


def _case_exact_file(base: str, relpath: str) -> bool:
    """Whether `relpath` names a real FILE under `base`, matching every
    path component's case exactly against the actual directory listing --
    never `os.path.isfile`, which folds case on macOS and Windows
    (`spec/identity.md`, "Identity must not depend on the host filesystem")."""
    parts = relpath.split("/")
    if any(p in ("", "..") for p in parts) or os.path.isabs(relpath):
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
    return os.path.isfile(cur)


def _token_matched_inputs(ws: str, bash_cmds: list) -> set:
    matched = set()
    for cmd in bash_cmds:
        for tok in _tokens_in(cmd):
            if tok.startswith("-") or tok in _PUNCTUATION:
                continue
            rel = tok[2:] if tok.startswith("./") else tok
            if _case_exact_file(ws, rel):
                matched.add(rel)
    return matched


def _guidance_for(events: list, path: str):
    write_idx = None
    for i, e in enumerate(events):
        if e.get("event") == "write" and e.get("path") == path:
            write_idx = i
    if write_idx is None:
        return None
    for i in range(write_idx, -1, -1):
        if events[i].get("event") == "prompt":
            return events[i].get("text")
    return None


def _cost_from_trace(events: list) -> tuple:
    """`(calls, seconds)`: one call per `prompt` event, each spanning from
    its own timestamp to the last event before the next prompt (or the end
    of the trace) -- the oracle's own span, not the session's whole
    duration."""
    prompt_idxs = [i for i, e in enumerate(events) if e.get("event") == "prompt"]
    seconds = 0.0
    for pos, i in enumerate(prompt_idxs):
        start_ts = events[i].get("ts")
        end_i = prompt_idxs[pos + 1] - 1 if pos + 1 < len(prompt_idxs) else len(events) - 1
        end_ts = events[end_i].get("ts")
        if isinstance(start_ts, (int, float)) and isinstance(end_ts, (int, float)):
            seconds += max(0.0, end_ts - start_ts)
    return len(prompt_idxs), seconds


def _gate_specs(bash_cmds: list, outputs: list) -> list:
    """`[(run, output), ...]` -- each traced bash command paired with the
    verdict file(s) it is declared to pin."""
    if len(bash_cmds) == 1:
        return [(bash_cmds[0], o) for o in outputs]
    if len(bash_cmds) == len(outputs):
        return list(zip(bash_cmds, outputs))
    combined = " && ".join(bash_cmds)
    return [(combined, o) for o in outputs]


# ---------------------------------------------------------------------------
# propose: draft a recipe from the trace, no certification
# ---------------------------------------------------------------------------

def propose(ws: str, outputs: list, name: str, *, claim: list = None,
            generated: list = None) -> dict:
    """Draft a recipe from `ws`'s own trace (`TRACE`): which traced writes
    are the implementation, which traced reads and gate-command tokens are
    the pinned check, which traced bash commands are the gate.

    `claim` names paths to pin as inputs regardless of how they were
    traced (the check, when provenance alone would call it generated);
    `generated` names paths to treat as the untraced implementation (a
    hookless, bash-only session, where nothing recorded what was written).
    `claim` wins over both auto-detection and `generated` for any path
    named in both.
    """
    events = _read_trace(ws)
    write_paths, read_paths, bash_cmds = _scan_events(events)
    token_matched = _token_matched_inputs(ws, bash_cmds)

    claim_set = set(claim or [])
    force_generated = set(generated or [])
    outputs_set = set(outputs)

    generated_set = (write_paths | force_generated) - claim_set - outputs_set
    input_set = (read_paths | token_matched | claim_set) - generated_set - outputs_set

    produce_order = []
    seen = set()
    for p in list(write_paths) + list(force_generated):
        if p in generated_set and p not in seen:
            produce_order.append(p)
            seen.add(p)

    steps = []
    for p in produce_order:
        step = {"kind": "produce", "output": p, "class": "generated"}
        guidance = _guidance_for(events, p)
        if guidance is not None:
            step["guidance"] = guidance
        steps.append(step)
    for cmd, output in _gate_specs(bash_cmds, outputs):
        steps.append({"kind": "gate", "output": output, "run": cmd, "class": "validated"})

    return {"claim": {"name": name, "inputs": sorted(input_set)}, "step": steps}


# ---------------------------------------------------------------------------
# build_claim: certify a proposal cold, then seal it
# ---------------------------------------------------------------------------

def build_claim(ws: str, outputs: list, rec: str, *, name: str, claim: list = None,
                 generated: list = None) -> dict:
    """Certify `ws`'s session cold and seal the result at `rec`.

    Confines every trace-derived path BEFORE copying anything; refuses a
    gate whose every decider is generated (`kernel.vacuous_gates`); then
    re-runs the gate in a fresh room and requires it to reproduce the
    session's own verdict byte-for-byte -- the trace has no authority on
    its own.
    """
    parsed = propose(ws, outputs, name, claim=claim, generated=generated)

    declared_paths = list(parsed["claim"]["inputs"])
    declared_paths.extend(step["output"] for step in parsed["step"])
    for p in declared_paths:
        _util.safe_path(ws, p)  # refuse an escaping path before any copy

    vacuous = kernel.vacuous_gates(parsed)
    if vacuous:
        raise kernel.ClaimError(
            f"gate(s) {vacuous} are vacuous: every decider is a generated "
            "output; declare claim= to pin the real check")

    room = tempfile.mkdtemp(prefix="certify-")
    try:
        for p in parsed["claim"]["inputs"]:
            _util.copy_into(os.path.join(ws, p), os.path.join(room, p))
        for step in parsed["step"]:
            if step["kind"] == "produce":
                _util.copy_into(os.path.join(ws, step["output"]),
                                 os.path.join(room, step["output"]))
        for step in parsed["step"]:
            if step["kind"] != "gate":
                continue
            result = kernel.run_gate(step["run"], room, parsed)
            cold_path = os.path.join(room, step["output"])
            orig_path = os.path.join(ws, step["output"])
            reproduced = (
                result["status"] == "ok"
                and os.path.isfile(cold_path) and os.path.isfile(orig_path)
                and kernel._hash_file(cold_path) == kernel._hash_file(orig_path)
            )
            if not reproduced:
                raise kernel.ClaimError(
                    f"gate {step['output']!r} does not reproduce cold: the "
                    "trace's verdict has no authority on its own")
    finally:
        shutil.rmtree(room, ignore_errors=True)

    os.makedirs(rec, exist_ok=True)
    with open(os.path.join(rec, kernel.RECIPE), "w", encoding="utf-8") as f:
        f.write(render.toml(parsed))
    for p in parsed["claim"]["inputs"]:
        _util.copy_into(os.path.join(ws, p), os.path.join(rec, p))
    for step in parsed["step"]:
        _util.copy_into(os.path.join(ws, step["output"]), os.path.join(rec, step["output"]))

    manifest = kernel.seal(rec)

    events = _read_trace(ws)
    calls, seconds = _cost_from_trace(events)
    if calls > 0:
        kernel.ledger(rec, {"event": "oracle", "calls": calls, "seconds": seconds})

    return {"ok": True, **manifest}
