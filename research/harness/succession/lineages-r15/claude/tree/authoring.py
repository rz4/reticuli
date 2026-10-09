"""authoring: sessions become claims (`spec/layers.md`).

`propose` reads a session's trace and the workspace it ran in, and drafts a
recipe -- read-only, nothing copied or sealed. Declaration always wins over
inference: a file the session traced `write`-ing defaults to `generated`
(regrowable), a file it traced `read`-ing or a gate command visibly names
defaults to a pinned input, and either default is overridden by the
explicit `claim=`/`generated=` lists a caller passes (needed for a hookless
session, whose trace carries only `bash` events and no `read`/`write`
provenance at all). A name is never inferred by asking the filesystem
whether it exists under a folded case -- `spec/identity.md`'s rule that
identity must not depend on the host filesystem applies here first, since
this is where candidate names are born.

`build_claim` is the authority: it certifies `propose`'s draft *cold*, in a
scratch room holding nothing but the declared bytes, refusing a vacuous
gate outright and refusing to seal a verdict that does not re-earn under a
fresh, independent run of the same gates (`kernel.audit`). Trace-derived
paths are confined before anything is copied, so an escaping candidate
refuses at the boundary rather than leaking out through a half-built room.

Every gate here runs through `kernel.run_gate` -- scrubbed, sandboxed,
bounded -- never `kernel.sandbox` directly.

Stdlib only.
"""
import json
import os
import re
import shlex
import shutil
import tempfile

from reticuli import _util, kernel, render

TRACE = ".reticuli/draft.jsonl"

_SHELL_OPERATORS = frozenset({"&&", "||", ";", "|", "&", ">", ">>", "<", "<<"})
_PATH_SPLIT = re.compile(r"[\\/]+")


def _dedup(seq) -> list:
    out = []
    for x in seq:
        if x not in out:
            out.append(x)
    return out


def _read_trace(ws: str) -> list:
    path = os.path.join(ws, TRACE)
    if not os.path.isfile(path):
        return []
    events = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def _validate_declared(ws: str, paths: list) -> None:
    """Confine every explicitly declared (read/write-traced) path before
    anything is copied -- a trace-derived path that escapes the session
    refuses outright, not silently.
    """
    for p in paths:
        _util.safe_path(ws, p)


def _bash_tokens(cmd: str) -> list:
    """The non-flag, non-operator words of a shell command -- candidates to
    test against the workspace, not a parse of what the command does.
    """
    try:
        words = shlex.split(cmd)
    except ValueError:
        return []
    return [w for w in words if w not in _SHELL_OPERATORS and not w.startswith("-")]


def _exact_match(ws: str, rel_path: str) -> bool:
    """Does `rel_path` name a real file under `ws`, matching case exactly at
    every path component? Identity must not depend on the host
    filesystem's case-folding (`spec/identity.md`): a candidate is accepted
    only when it matches a real directory entry, case and all.
    """
    if not rel_path or rel_path.startswith(("/", "\\")):
        return False
    parts = _PATH_SPLIT.split(rel_path)
    if any(p in ("", "..", ".") for p in parts):
        return False
    current = ws
    for part in parts:
        try:
            entries = os.listdir(current)
        except OSError:
            return False
        if part not in entries:
            return False
        current = os.path.join(current, part)
    return os.path.isfile(current)


def _gather(ws: str, outputs: list, claim=None, generated=None):
    """Classify one session's trace into (generated outputs, pinned
    inputs, gate commands)."""
    events = _read_trace(ws)
    written, read_paths, bash_cmds = [], [], []
    for e in events:
        kind = e.get("event")
        if kind == "write" and e.get("path"):
            written.append(e["path"])
        elif kind == "read" and e.get("path"):
            read_paths.append(e["path"])
        elif kind == "bash" and e.get("cmd"):
            bash_cmds.append(e["cmd"])

    _validate_declared(ws, written + read_paths)

    explicit_claim = list(claim or [])
    explicit_generated = list(generated or [])
    out_set = set(outputs or [])

    generated_set = [p for p in _dedup(written + explicit_generated)
                     if p not in explicit_claim]

    token_candidates = _dedup(
        read_paths + [tok for cmd in bash_cmds for tok in _bash_tokens(cmd)])

    input_set = []
    for p in token_candidates:
        if p in out_set or p in generated_set or p in input_set:
            continue
        if p in explicit_claim or _exact_match(ws, p):
            input_set.append(p)
    for p in explicit_claim:
        if p not in out_set and p not in generated_set and p not in input_set:
            input_set.append(p)

    return generated_set, sorted(input_set), bash_cmds


def _produce_steps(generated_set: list) -> list:
    return [{"kind": "produce", "output": p, "class": "generated",
             "guidance": f"regenerate {p} to pass the gate"} for p in generated_set]


def _gate_steps(outputs: list, bash_cmds: list) -> list:
    if not bash_cmds:
        return []
    if len(bash_cmds) == len(outputs):
        pairs = list(zip(bash_cmds, outputs))
    else:
        pairs = [(bash_cmds[-1], o) for o in outputs]
    return [{"kind": "gate", "output": output, "class": "validated", "run": cmd}
            for cmd, output in pairs]


def propose(ws: str, outputs: list, name: str, claim=None, generated=None) -> dict:
    """A draft recipe for session `ws`: read-only, nothing copied or
    sealed. See the module docstring for the classification rule.
    """
    generated_set, input_set, bash_cmds = _gather(ws, outputs, claim=claim, generated=generated)
    return {
        "claim": {"name": name, "format": 3, "inputs": input_set},
        "step": _produce_steps(generated_set) + _gate_steps(list(outputs or []), bash_cmds),
    }


def _check_vacuous(doc: dict) -> None:
    vacuous = kernel.vacuous_gates(doc)
    if vacuous:
        raise kernel.ClaimError(
            f"gate(s) {vacuous} are vacuous: every decider is generated code, "
            "so no pinned byte can reject a realization")


def _materialize_candidate(ws: str, scratch: str, doc: dict) -> None:
    os.makedirs(scratch, exist_ok=True)
    for p in doc["claim"].get("inputs", []):
        _util.copy_into(ws, scratch, p)
    for step in doc["step"]:
        if step.get("kind") == "produce" and step.get("class") == "generated":
            if os.path.isfile(os.path.join(ws, step["output"])):
                _util.copy_into(ws, scratch, step["output"])


def build_claim(ws: str, outputs: list, rec: str, name=None, claim=None, generated=None) -> dict:
    """Cold-certify session `ws` into a sealed claim at `rec`: draft a
    recipe via `propose`, refuse a vacuous gate outright, then rebuild it
    from nothing but the declared bytes in a scratch room -- run the gates
    there, seal, and re-earn via a cold `kernel.audit` before the room ever
    becomes `rec`. A verdict that cannot be re-earned on its own bytes (a
    nondeterministic gate) never becomes a claim.
    """
    doc = propose(ws, outputs, name, claim=claim, generated=generated)
    _check_vacuous(doc)

    events = _read_trace(ws)
    calls = sum(1 for e in events if e.get("event") == "prompt")
    stamps = [e["ts"] for e in events if isinstance(e.get("ts"), (int, float))]
    seconds = (max(stamps) - min(stamps)) if stamps else 0.0

    scratch = tempfile.mkdtemp(prefix="reticuli-building-")
    moved = False
    try:
        _materialize_candidate(ws, scratch, doc)
        with open(os.path.join(scratch, kernel.RECIPE), "w", encoding="utf-8") as f:
            f.write(render.dump_recipe(doc))

        for step in doc["step"]:
            if step["kind"] != "gate":
                continue
            result = kernel.run_gate(step["run"], scratch, doc)
            if result["status"] != "ok" or \
                    not os.path.isfile(os.path.join(scratch, step["output"])):
                raise kernel.ClaimError(
                    f"gate {step['output']!r} did not earn a verdict cold: {result['status']}")

        kernel.seal(scratch)
        audited = kernel.audit(scratch)
        if not audited.get("ok"):
            raise kernel.ClaimError(
                f"claim does not re-earn cold ({audited.get('verdict')}): a pinned "
                "verdict must reproduce from the bytes alone, not from the trace")

        kernel.ledger(scratch, {"calls": calls, "seconds": seconds})

        parent = os.path.dirname(rec)
        if parent:
            os.makedirs(parent, exist_ok=True)
        if os.path.exists(rec):
            shutil.rmtree(rec)
        shutil.move(scratch, rec)
        moved = True
    finally:
        if not moved:
            shutil.rmtree(scratch, ignore_errors=True)

    return {"ok": True, "root": kernel.verify(rec)["root"]}
