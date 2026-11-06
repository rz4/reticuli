"""Materialize a room, re-earn a verdict in it, regrow an implementation.

`audit` deletes nothing but trusts nothing: it builds a fresh room from the
claim's declared content, re-runs every gate sandboxed, and requires every
pinned byte to reproduce. A stored "passed" is never carried in.

`rebuild` hands a producer a room holding only what the claim pins -- the
criteria, the fixtures, the recipe the ROOT was computed from -- and keeps
regrowing until the gates pass. The producer is the caller's oracle, so it
runs with the caller's standing and the caller's HOME; the gate it feeds is
confined, as always.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

from . import identity as _identity
from . import recipe as _recipe
from . import run as _run_layer
from . import seal as _seal
from .core import (MANIFEST, PRODUCER_TIMEOUT, SIGN_DIR, STORE, USAGE,
                   ClaimError, COST_KEYS, _ENV_CLAIM, _ENV_OUTPUT,
                   _ENV_OUTPUTS, _ENV_REQUEST, _ENV_SIGNERS, _ENV_USAGE,
                   _KEEP_ENV, _copy_into, _finite, _hash_file,
                   _judging_host, _now, _read_json, _safe)

_step_guidance = _recipe.step_guidance


# -- writing a recipe back out --------------------------------------------
def _toml_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value)            # JSON escaping is TOML-basic
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{json.dumps(k)} = {_toml_value(v)}"
                                for k, v in value.items()) + " }"
    raise ClaimError(f"a recipe cannot carry {type(value).__name__}")


def _toml_dump(parsed: dict) -> str:
    """The recipe as TOML again.

    At format 3 and above a room receives the recipe the ROOT was computed
    from, and that file must still BE a recipe: TOML that parses back to the
    preimage tables. Writing the preimage's JSON into a file named
    `reticuli.toml` makes a kernel refuse its own room.
    """
    lines = []
    table = parsed.get("claim") or {}
    lines.append("[claim]")
    for key, value in table.items():
        lines.append(f"{key} = {_toml_value(value)}")
    for step in parsed.get("step") or []:
        lines.append("")
        lines.append("[[step]]")
        for key, value in step.items():
            lines.append(f"{key} = {_toml_value(value)}")
    return "\n".join(lines) + "\n"


# -- the room --------------------------------------------------------------
def _materialize(claim: str, into: str, parsed: dict,
                 produce_from: dict | None = None,
                 input_from: dict | None = None,
                 with_generated: bool = True) -> dict:
    """Lay out a judging room: the recipe, the pinned inputs, the outputs
    that are copied rather than earned, and any component's bytes.

    Gate verdicts are NEVER copied in: a verdict is earned by running the
    gate, and a room that arrived holding one would let a carried verdict
    pass for a present fact.
    """
    produce_from = produce_from or {}
    input_from = input_from or {}
    os.makedirs(into, exist_ok=True)
    fmt = _recipe._claim_format(parsed)
    if fmt >= 3:
        preimage = _identity._preimage_recipe(parsed)
        with open(os.path.join(into, _recipe.RECIPE), "w",
                  encoding="utf-8") as handle:
            handle.write(_toml_dump(preimage))
    else:
        source = _recipe.recipe_path(claim)
        _copy_into(source, os.path.join(into, os.path.basename(source)))

    supplied = {}
    for declared in _recipe._inputs(parsed, claim):
        target = _safe(into, declared)
        source = input_from.get(declared) or _safe(claim, declared)
        _copy_into(source, target)
    for step in _recipe.produces(parsed):
        output = step["output"]
        klass = _recipe.step_class(step)
        target = _safe(into, output)
        if klass != "generated":
            _copy_into(_safe(claim, output), target)
            continue
        if output in produce_from:
            _copy_into(produce_from[output], target)
            supplied[output] = produce_from[output]
            continue
        if with_generated:
            source = _safe(claim, output)
            if os.path.isfile(source):
                _copy_into(source, target)
    return supplied


def _members(parsed: dict) -> list:
    table = parsed.get("claim") or {}
    entries = []
    for entry in table.get("assembles") or []:
        name, _, root = entry.rpartition("@")
        entries.append((name, root))
    return entries


def _fold_members(claim: str, into: str, parsed: dict) -> None:
    """An assembly's members must RECOMPUTE to their declared roots before
    any gate runs: a member whose bytes have drifted is a different
    composition, and judging it would judge something the assembly never
    declared. One level only."""
    for name, declared in _members(parsed):
        member = os.path.join(claim, STORE, "sealed", name)
        if not os.path.isdir(member):
            raise ClaimError(
                f"the assembly declares the member {name!r}, which is not in "
                f"this claim's drawer ({STORE}/sealed/{name})")
        member_recipe = _recipe.load_recipe(member)
        found = _identity.root(member_recipe, member)
        if found != declared:
            raise ClaimError(
                f"the member {name!r} recomputes to {found[:12]}..., not the "
                f"declared {declared[:12]}...: a moved member is a different "
                f"composition, so the fold refuses")
        for step in _recipe.produces(member_recipe):
            source = _safe(member, step["output"])
            if not os.path.isfile(source):
                continue
            target = _safe(into, step["output"])
            if os.path.exists(target):
                raise ClaimError(
                    f"path collision on {step['output']!r} while folding the "
                    f"member {name!r}: one path, one owner")
            _copy_into(source, target)
        drawer = os.path.join(into, STORE, "sealed", name)
        if not os.path.exists(drawer):
            shutil.copytree(member, drawer, symlinks=False,
                            ignore=shutil.ignore_patterns("scratch"))


def _compare_pin(room: str, claim: str, output: str) -> bool:
    """Did the gate reproduce the pinned bytes, byte for byte?"""
    here = os.path.join(room, output)
    there = os.path.join(claim, output)
    if not os.path.isfile(here) or not os.path.isfile(there):
        return False
    with open(here, "rb") as a, open(there, "rb") as b:
        return a.read() == b.read()


# -- audit -----------------------------------------------------------------
def audit(claim: str, produce_from: dict | None = None, strict: bool = True,
          mutants: int | None = None) -> dict:
    """Re-earn every verdict, cold, on the bytes present.

    The verdict is `earned` when every gate re-ran clean and every pinned
    byte reproduced; otherwise it names what happened in the one vocabulary:
    `broken` is identity damage (the bytes are not this claim any more),
    `mismatch` is a gate that ran clean and produced the wrong bytes,
    `failed` is a gate that said no, `timeout` is one that ran past its
    window, and `environment` is a host that could not judge.
    """
    started = time.monotonic()
    parsed = _recipe.load_recipe(claim)
    manifest = _seal.read_manifest(claim)
    recomputed = _identity.root(parsed, claim)
    host = _judging_host()
    result = {"name": manifest["name"], "root": manifest["root"],
              "recomputed": recomputed, "ok": False, "verdict": "broken",
              "gates": [], "environment": [], "layers": [],
              "host": host, "elapsed": 0.0}
    if recomputed != manifest["root"]:
        result["verdict"] = "broken"
        result["changed"] = _seal._changed_parts(claim, parsed)
        result["elapsed"] = round(time.monotonic() - started, 4)
        return result

    missing = _run_layer.preflight(parsed)
    if missing:
        result["environment"] = missing
        result["verdict"] = "environment"
        result["gates"] = [{"output": g["output"], "status": "environment",
                            "quarantine": None,
                            "detail": f"missing on this host: "
                                      f"{', '.join(missing)}"}
                           for g in _recipe.gates(parsed)]
        result["elapsed"] = round(time.monotonic() - started, 4)
        return result

    room = tempfile.mkdtemp(prefix="reticuli-audit-")
    try:
        _materialize(claim, room, parsed, produce_from=produce_from)
        _fold_members(claim, room, parsed)
        extra_env = None
        furnished = _run_layer.furnish(room, parsed)
        if not furnished["ok"]:
            result["verdict"] = "environment"
            result["environment"] = [str(furnished["reason"])]
            result["gates"] = [{"output": g["output"],
                                "status": "environment",
                                "quarantine": None,
                                "detail": str(furnished["reason"])}
                               for g in _recipe.gates(parsed)]
            result["elapsed"] = round(time.monotonic() - started, 4)
            return result
        if furnished["bin"]:
            extra_env = {"PATH": furnished["bin"] + os.pathsep +
                         os.environ.get("PATH", os.defpath),
                         "VIRTUAL_ENV": os.path.dirname(furnished["bin"])}

        rows = []
        for gate in _recipe.gates(parsed):
            outcome = _run_layer.run_gate(gate["run"], room, parsed,
                                          extra_env=extra_env, strict=strict)
            status = outcome["status"]
            if status == "ok" and \
                    _recipe.step_class(gate) != "generated" and \
                    not _compare_pin(room, claim, gate["output"]):
                status = "mismatch"
            rows.append({"output": gate["output"], "status": status,
                         "quarantine": outcome["quarantine"],
                         "detail": (outcome["stderr"] or
                                    outcome["stdout"])[-400:]})
        result["gates"] = rows
        result["ok"] = bool(rows) and all(r["status"] == "ok" for r in rows)
        if not rows:
            result["ok"] = True
        if result["ok"]:
            result["verdict"] = "earned"
        else:
            order = ("broken", "environment", "timeout", "mismatch", "failed")
            found = {r["status"] for r in rows}
            result["verdict"] = next(
                (w for w in order if w in found), "failed")
    finally:
        shutil.rmtree(room, ignore_errors=True)

    result["elapsed"] = round(time.monotonic() - started, 4)
    if mutants:
        from . import crosscheck as _cross
        result["mutation_score"] = _cross.mutation_score(
            claim, max_mutants=mutants)
    _receipt(claim, result)
    return result


def _receipt(claim: str, result: dict) -> None:
    """A dated audit receipt, as residue: what this machine last earned."""
    from .core import RECEIPT
    try:
        from .core import _write_json
        _write_json(os.path.join(claim, RECEIPT),
                    {"when": _now(), "root": result.get("recomputed"),
                     "verdict": result.get("verdict"),
                     "ok": bool(result.get("ok")),
                     "gates": [{"output": g["output"], "status": g["status"],
                                "quarantine": g.get("quarantine")}
                               for g in result.get("gates") or []]})
    except OSError:
        pass


# -- rebuild ---------------------------------------------------------------
def _read_usage(path: str) -> dict:
    """A producer's self-report, taken as testimony and nothing more.

    A payload that is not a table of measurements pollutes nothing: the
    rebuild completes and its ledger simply carries no cost. `seconds` is
    never accepted here -- wall-clock is the kernel's own measurement, and a
    cost envelope must not be handed a number the producer chose for it.
    """
    payload = None
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            payload = None
    if not isinstance(payload, dict):
        return {}
    told = {}
    for key in COST_KEYS:
        if key == "seconds":
            continue
        value = payload.get(key)
        if _finite(value) and value >= 0:
            told[key] = value
    return told


def _producer_env(room: str, parsed: dict, step, work: list,
                  guidance: bool, producer_env: dict | None) -> dict:
    env = {key: os.environ[key] for key in _KEEP_ENV if key in os.environ}
    env.setdefault("PATH", os.environ.get("PATH", os.defpath))
    env[_ENV_CLAIM] = os.path.realpath(room)
    env[_ENV_OUTPUTS] = json.dumps(work)
    env[_ENV_USAGE] = os.path.join(os.path.realpath(room), USAGE)
    if step is not None:
        env[_ENV_OUTPUT] = _safe(room, step["output"])
        hint = _step_guidance(step)
        if guidance and hint:
            env[_ENV_REQUEST] = hint
    for key, value in (producer_env or {}).items():
        if value is not None:
            env[key] = str(value)
    return env


def _produce(room: str, parsed: dict, producer: str, work: list,
             guidance: bool, producer_env: dict | None) -> int:
    """Ask the producer for each output the room does not already hold.

    The producer is told WHICH output to write (absolutely) and what the
    whole work list is, whether the claim has one output or twenty. It is
    scrubbed but never confined: it needs the network and a real process
    environment, and its output faces the jailed gate regardless.
    """
    calls = 0
    steps = {s["output"]: s for s in _recipe.produces(parsed)}
    os.makedirs(os.path.join(room, STORE), exist_ok=True)
    for output in work:
        target = _safe(room, output)
        if os.path.isfile(target):
            continue
        env = _producer_env(room, parsed, steps.get(output), work,
                            guidance, producer_env)
        calls += 1
        try:
            done = subprocess.run(producer, shell=True, cwd=room, env=env,
                                  capture_output=True, text=True,
                                  timeout=PRODUCER_TIMEOUT, check=False)
        except subprocess.TimeoutExpired:
            raise ClaimError(
                f"the producer ran past its window while writing "
                f"{output!r}") from None
        if not os.path.isfile(target):
            raise ClaimError(
                f"the producer wrote no {output!r} (exit {done.returncode}): "
                f"{(done.stderr or done.stdout)[-300:]}")
    return calls


def _snapshot(room: str, parsed: dict) -> dict:
    """The question, as the producer received it: the recipe, the pinned
    inputs, and every output that is copied rather than earned."""
    taken = {}
    source = _recipe.recipe_path(room)
    taken[os.path.basename(source)] = _hash_file(source)
    for declared in _recipe._inputs(parsed, room):
        taken[declared] = _hash_file(_safe(room, declared))
    for step in _recipe.produces(parsed):
        if _recipe.step_class(step) in ("pinned", "carried"):
            path = _safe(room, step["output"])
            if os.path.isfile(path):
                taken[step["output"]] = _hash_file(path)
    return taken


def rebuild(claim: str, producer: str, into: str,
            produce_from: dict | None = None, input_from: dict | None = None,
            guidance: bool = True, producer_env: dict | None = None,
            strict: bool = True) -> dict:
    """Regrow the generated outputs in a fresh room until the gates pass."""
    parsed = _recipe.load_recipe(claim)
    missing = _run_layer.preflight(parsed)
    if missing:
        raise ClaimError(
            f"environment: this host cannot test {parsed['claim']['name']!r} "
            f"-- missing {', '.join(missing)}")
    if os.path.exists(into) and os.listdir(into):
        raise ClaimError(
            f"the rebuild target already holds bytes: {into}. A partially "
            f"built chain is a refusal with a reason, never a silent "
            f"resumption onto bytes nobody re-earned")
    os.makedirs(into, exist_ok=True)

    started = time.monotonic()
    supplied = _materialize(claim, into, parsed, produce_from=produce_from,
                            input_from=input_from, with_generated=False)
    _fold_members(claim, into, parsed)
    backend = _run_layer.sandbox_backend()
    _run_layer.environment_event(into, backend)
    for output, source in sorted(supplied.items()):
        _run_layer.ledger(into, {"event": "reuse", "output": output,
                                 "source": os.path.basename(source)})

    before = _snapshot(into, parsed)
    work = [o for o in _recipe.generated_outputs(parsed)
            if not os.path.isfile(_safe(into, o))]
    calls = _produce(into, parsed, producer, work, guidance, producer_env)
    after = _snapshot(into, parsed)
    for name, digest in before.items():
        if after.get(name) != digest:
            raise ClaimError(
                f"the producer rewrote {name!r}, which this claim pins: a "
                f"producer cannot change the question it was asked")

    told = _read_usage(os.path.join(into, USAGE))
    declared = _run_layer.producer_declaration()
    _run_layer.ledger(into, dict(
        {"event": "producer", "calls": calls,
         "seconds": round(time.monotonic() - started, 4),
         "blind": not supplied, "vendor": declared["vendor"],
         "model": declared["model"]}, **told))

    for gate in _recipe.gates(parsed):
        outcome = _run_layer.run_gate(gate["run"], into, parsed,
                                      strict=strict)
        _run_layer.ledger(into, {"event": "gate", "output": gate["output"],
                                 "status": outcome["status"],
                                 "quarantine": outcome["quarantine"],
                                 "seconds": None})
        if outcome["status"] != "ok":
            raise ClaimError(
                f"{outcome['status']}: the gate {gate['output']!r} did not "
                f"earn its verdict in the rebuilt room: "
                f"{(outcome['stderr'] or outcome['stdout'])[-300:]}")

    manifest = dict(_seal.seal(into))
    manifest["quarantine"] = backend
    manifest["calls"] = calls
    return manifest


# -- the signed phase ------------------------------------------------------
def _ssh_verify(statement: str, identity: str, namespace: str,
                signers: str) -> bool:
    if not shutil.which("ssh-keygen") or not signers or \
            not os.path.isfile(signers) or not identity:
        return False
    signature = statement + ".sig"
    if not os.path.isfile(signature):
        return False
    try:
        with open(statement, "rb") as handle:
            data = handle.read()
        done = subprocess.run(
            ["ssh-keygen", "-Y", "verify", "-f", signers, "-I", identity,
             "-n", namespace, "-s", signature],
            input=data, capture_output=True, timeout=60, check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0


def _anchor(signers: str | None = None):
    return signers or os.environ.get(_ENV_SIGNERS)


def _authorized(claim: str, signers: str | None = None) -> list:
    """Every authorization statement in the claim's drawer, judged.

    Trust is verifier-relative: with no reachable anchor a signature can at
    most be shown self-consistent, which says a statement was signed and not
    whose it is. Unanchored is never authorization.
    """
    drawer = os.path.join(claim, SIGN_DIR)
    if not os.path.isdir(drawer):
        return []
    anchor = _anchor(signers)
    try:
        current_root = _seal.verify(claim)["recomputed"]
        current_digest = _identity.build_digest(claim)
    except ClaimError:
        current_root, current_digest = None, None
    rows = []
    for name in sorted(os.listdir(drawer)):
        if not name.endswith(".sign.json"):
            continue
        path = os.path.join(drawer, name)
        statement = _read_json(path)
        if not isinstance(statement, dict):
            continue
        identity_name = statement.get("identity")
        packet_path = path[:-len(".sign.json")] + ".packet.json"
        packet_holds = False
        packet = None
        if os.path.isfile(packet_path):
            with open(packet_path, "rb") as handle:
                raw = handle.read()
            packet_holds = hashlib.sha256(raw).hexdigest() == \
                statement.get("packet_digest")
            try:
                packet = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                packet = None
        drifted = True
        if isinstance(packet, dict) and current_digest is not None:
            drifted = packet.get("build_digest") != current_digest
        intact = os.path.isfile(path + ".sig")
        anchored = bool(anchor) and _ssh_verify(
            path, identity_name, _recipe_sign_namespace(), anchor)
        verdict = "authorized" if anchored else (
            "intact" if intact else "unsigned")
        rows.append({"identity": identity_name,
                     "statement": os.path.relpath(path, claim),
                     "verdict": verdict,
                     "anchored": bool(anchor),
                     "packet_holds": packet_holds,
                     "drifted": drifted,
                     "names_this_root": statement.get("root") == current_root,
                     "proof_recorded": bool(statement.get("proof_recorded"))})
    return rows


def _recipe_sign_namespace() -> str:
    from .core import SIGN_NAMESPACE
    return SIGN_NAMESPACE


def phase(claim: str) -> str:
    """`draft` / `sealed` / `signed`.

    SIGNED means AUTHORIZED (a signature from a key in the verifier's own
    anchor, over a packet that still matches what is on disk and the bytes
    present) AND PROVEN (a recorded crosscheck). A recorded proof alone never
    advances phase, and neither does a signature from an untrusted key.
    """
    if not os.path.isfile(os.path.join(claim, MANIFEST)):
        _recipe.recipe_path(claim)                  # refuse a non-claim
        return "draft"
    manifest = _seal.read_manifest(claim)
    checked = _seal.verify(claim)
    if not manifest.get("proof"):
        return "sealed"
    for row in _authorized(claim):
        if row["verdict"] == "authorized" and row["proof_recorded"] \
                and row["packet_holds"] and not row["drifted"] \
                and row["names_this_root"] and checked["ok"]:
            return "signed"
    return "sealed"
