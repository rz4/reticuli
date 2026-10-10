"""authoring: turning a recorded session into a claim (spec/layers.md
"authoring"; v1: `condense`).

`propose` previews what a session's trace supports claiming, without
touching disk. `build_claim` certifies cold: it classifies the session's
traced files into a generated implementation and pinned inputs (declaration,
never provenance alone, decides which -- `claim=`/`generated=` override the
trace), confines every candidate path to the session before copying anything,
refuses a gate whose every decider is itself generated (vacuous), rebuilds
in a clean room and re-runs the gate there, and refuses to seal a verdict
that does not reproduce byte-for-byte on that cold run. Every gate runs
through `kernel.run_gate` alone -- never `kernel.sandbox` directly, which
would bypass the scrub and the bound this layer promises.
"""
import json
import os
import shlex
import shutil
import tempfile

from reticuli import _util, kernel, render

TRACE = ".reticuli/draft.jsonl"

_SHELL_TOKENS = frozenset({"&&", "||", "|", ";", "&", ">", ">>", "<", "2>", "2>>"})


# -- the session trace -------------------------------------------------------

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


def _bash_cmds(events: list) -> list:
    return [e["cmd"] for e in events
            if e.get("event") == "bash" and isinstance(e.get("cmd"), str)]


def _gate_command(events: list) -> str:
    cmds = _bash_cmds(events)
    if not cmds:
        raise kernel.ClaimError("refused: no gate command recorded in the session trace")
    return " && ".join(cmds)


def _cost_from_trace(events: list):
    ts_values = [e["ts"] for e in events
                 if isinstance(e.get("ts"), (int, float)) and not isinstance(e.get("ts"), bool)]
    if not ts_values:
        return None
    calls = sum(1 for e in events if e.get("event") == "prompt")
    return {"calls": calls, "seconds": max(ts_values) - min(ts_values)}


def _traced_paths(events: list, event_name: str) -> list:
    return [e["path"] for e in events
            if e.get("event") == event_name and isinstance(e.get("path"), str)]


# -- candidate inputs: a real directory entry, never a folded guess --------

def _exists_case_sensitive(base: str, rel: str) -> bool:
    cur = base
    for part in rel.split("/"):
        if not part or not os.path.isdir(cur):
            return False
        try:
            entries = os.listdir(cur)
        except OSError:
            return False
        if part not in entries:
            return False
        cur = os.path.join(cur, part)
    return os.path.isfile(cur)


def _scanned_inputs(ws: str, events: list, exclude: set) -> list:
    """Tokens of every traced bash command that name a real file in `ws`,
    case and all -- a candidate input a trace's prose never declared as a
    `read`, but the gate command text names (e.g. `grep`'s own argument)."""
    found, seen = [], set()
    for cmd in _bash_cmds(events):
        try:
            tokens = shlex.split(cmd)
        except ValueError:
            continue
        for tok in tokens:
            if tok in _SHELL_TOKENS or tok.startswith("-"):
                continue
            if tok in exclude or tok in seen:
                continue
            try:
                _util.safe_path(ws, tok)
            except ValueError:
                continue
            if _exists_case_sensitive(ws, tok):
                seen.add(tok)
                found.append(tok)
    return found


# -- classification: declaration, never provenance alone, decides class ----

def _classify(ws: str, events: list, outputs: list, claim=None, generated=None):
    outputs_set = set(outputs or [])
    generated_set = set(generated) if generated is not None else set(_traced_paths(events, "write"))
    if claim is not None:
        inputs_set = set(claim)
    else:
        read_paths = set(_traced_paths(events, "read"))
        scanned = set(_scanned_inputs(ws, events, outputs_set | generated_set))
        inputs_set = read_paths | scanned
    generated_set -= inputs_set
    generated_set -= outputs_set
    inputs_set -= outputs_set
    return generated_set, inputs_set


def _confine_all(ws: str, paths) -> None:
    for p in paths:
        try:
            _util.safe_path(ws, p)
        except ValueError as e:
            raise kernel.ClaimError(f"refused: declared path escapes the session: {p!r}") from e


def _recipe(name: str, generated_set: set, inputs_set: set, outputs: list, gate_cmd: str) -> dict:
    steps = [{"kind": "produce", "output": g, "class": "generated"} for g in sorted(generated_set)]
    for o in outputs:
        steps.append({"kind": "gate", "output": o, "class": "validated", "run": gate_cmd})
    claim = {"name": name, "format": 3, "inputs": sorted(inputs_set)}
    return {"claim": claim, "step": steps}


def _refuse_if_vacuous(parsed: dict, outputs: list) -> None:
    vacuous = kernel.vacuous_gates(parsed)
    for o in outputs:
        if o in vacuous:
            raise kernel.ClaimError(
                f"refused: gate {o!r} is vacuous (every decider is generated); "
                "claim the deciding file or declare it generated explicitly")


# -- the public surface ------------------------------------------------------

def propose(ws: str, outputs: list, name: str) -> dict:
    """What a session's trace alone supports claiming, without touching
    disk: a candidate recipe (v1: `draft`)."""
    events = _read_trace(ws)
    generated_set, inputs_set = _classify(ws, events, outputs)
    try:
        gate_cmd = _gate_command(events)
    except kernel.ClaimError:
        gate_cmd = None
    recipe = _recipe(name, generated_set, inputs_set, outputs if gate_cmd else [],
                      gate_cmd or "")
    return {"claim": recipe["claim"], "step": recipe["step"],
            "generated": sorted(generated_set), "inputs": sorted(inputs_set)}


def build_claim(ws: str, outputs: list, rec: str, name: str = None,
                 claim: list = None, generated: list = None) -> dict:
    """Certify a session cold: classify, confine, refuse the vacuous, rebuild
    in a clean room, and refuse a verdict that does not reproduce there."""
    events = _read_trace(ws)
    generated_set, inputs_set = _classify(ws, events, outputs, claim=claim, generated=generated)
    _confine_all(ws, generated_set | inputs_set)

    gate_cmd = _gate_command(events)
    parsed = _recipe(name, generated_set, inputs_set, outputs, gate_cmd)
    _refuse_if_vacuous(parsed, outputs)

    scratch = tempfile.mkdtemp(prefix="reticuli-build-")
    try:
        for p in sorted(generated_set | inputs_set):
            src = os.path.join(ws, p)
            if not os.path.isfile(src):
                raise kernel.ClaimError(f"refused: declared path not found in the session: {p!r}")
            _util.copy_into(src, os.path.join(scratch, p))
        with open(os.path.join(scratch, kernel.RECIPE), "w", encoding="utf-8") as f:
            f.write(render.dump_recipe(parsed))

        res = kernel.run_gate(gate_cmd, scratch, recipe=parsed)
        if res["status"] != "ok":
            raise kernel.ClaimError(f"refused: the gate did not pass cold: {res['status']}")

        for o in outputs:
            cold_path = os.path.join(scratch, o)
            warm_path = os.path.join(ws, o)
            if not os.path.isfile(cold_path):
                raise kernel.ClaimError(f"refused: the gate did not produce {o!r} cold")
            if not os.path.isfile(warm_path):
                raise kernel.ClaimError(f"refused: no warm verdict to certify {o!r} against")
            with open(cold_path, "rb") as f1, open(warm_path, "rb") as f2:
                if f1.read() != f2.read():
                    raise kernel.ClaimError(
                        f"refused: verdict {o!r} did not reproduce cold "
                        "(the gate is not deterministic)")

        if os.path.isdir(rec) and os.listdir(rec):
            raise kernel.ClaimError(f"refused: {rec!r} already holds bytes")
        os.makedirs(rec, exist_ok=True)
        for entry in os.listdir(scratch):
            _util.copy_into(os.path.join(scratch, entry), os.path.join(rec, entry))
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    cost = _cost_from_trace(events)
    if cost is not None:
        kernel.ledger(rec, cost)

    manifest = kernel.seal(rec)
    return {"ok": True, "root": manifest["root"], "name": manifest["name"]}
