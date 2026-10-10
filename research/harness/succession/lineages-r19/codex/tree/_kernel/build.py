"""Materialize a claim, re-earn its gates, and rebuild its generated files."""

from __future__ import annotations

import json
import os
import shutil
import tempfile

from . import core, identity, recipe, run, seal


def _toml_value(value):
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{key} = {_toml_value(item)}" for key, item in value.items()) + " }"
    raise core.ClaimError(f"cannot serialize recipe value: {value!r}")


def _room_recipe(parsed: dict) -> str:
    preimage = identity._preimage_recipe(parsed)
    lines = ["[claim]"]
    for key, value in preimage["claim"].items():
        lines.append(f"{key} = {_toml_value(value)}")
    for step in preimage.get("step", []):
        lines.extend(("", "[[step]]"))
        for key, value in step.items():
            lines.append(f"{key} = {_toml_value(value)}")
    return "\n".join(lines) + "\n"


def _materialize(source, into, parsed=None, *, generated=False):
    """Copy precisely the claim's declared room contents."""
    parsed = parsed or recipe.load_recipe(source)
    os.makedirs(into, exist_ok=True)
    source_recipe = recipe.recipe_path(source)
    if parsed["claim"].get("format", 1) >= 3:
        target_recipe = os.path.join(into, core.RECIPE)
        with open(target_recipe, "w", encoding="utf-8") as stream:
            stream.write(_room_recipe(parsed))
    else:
        core._copy_into(source_recipe, os.path.join(into, os.path.basename(source_recipe)))

    names = set(recipe._inputs(parsed, source))
    environment = parsed["claim"].get("environment")
    if environment:
        names.add(environment)
    for step in recipe.produces(parsed):
        if step.get("class", "generated") != "generated" or "from" in step or generated:
            names.add(step["output"])
    for name in sorted(names):
        core._copy_into(core._safe(source, name), core._safe(into, name))
    return into


def _step_guidance(step):
    return step.get("guidance", step.get("request", ""))


def _read_usage(directory):
    path = core._safe(directory, core.USAGE)
    try:
        with open(path, encoding="utf-8") as stream:
            payload = json.load(stream)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        raise core.ClaimError(f"cannot read usage: {exc}") from exc
    if not isinstance(payload, dict):
        raise core.ClaimError("usage must be a JSON object")
    return {key: value for key, value in payload.items()
            if key in ("usd", "tokens", "calls") and
            type(value) in (int, float) and value >= 0}


def _produce(command, directory, step, parsed, *, guidance=True, producer_env=None):
    """A producer inherits the caller's reachability and HOME."""
    outputs = recipe.generated_outputs(parsed)
    environment = {key: os.environ[key] for key in core._KEEP_ENV if key in os.environ}
    environment.setdefault("PATH", os.defpath)
    environment[core._ENV_OUTPUT] = core._safe(directory, step["output"])
    environment[core._ENV_OUTPUTS] = json.dumps(outputs)
    environment[core._ENV_CLAIM] = parsed["claim"]["name"]
    if guidance:
        environment[core._ENV_REQUEST] = _step_guidance(step)
    if producer_env:
        environment.update({str(key): str(value) for key, value in producer_env.items()})
    result = run._run(["/bin/sh", "-c", command], cwd=os.path.abspath(directory),
                      env=environment, timeout=core.PRODUCER_TIMEOUT)
    result["quarantine"] = run.sandbox_backend() if os.environ.get(core._JAILED) else "none"
    return result


def _compare_pin(source, room, name):
    try:
        return core._hash_file(core._safe(source, name)) == core._hash_file(core._safe(room, name))
    except core.ClaimError:
        return False


def _authorized(directory):
    return seal.verify(directory)["ok"]


def _ssh_verify(*args, **kwargs):
    """Signature verification belongs to the signing layer."""
    return False


def _judge(source, room, parsed):
    missing = run.preflight(parsed)
    furnished = None
    if not missing:
        try:
            furnished = run.furnish(room, parsed)
        except core.ClaimError as exc:
            missing = [str(exc)]
    gates = []
    for step in recipe.gates(parsed):
        name = step["output"]
        if missing:
            gates.append({"output": name, "status": "environment",
                          "quarantine": run.sandbox_backend(), "detail": missing})
            continue
        path = core._safe(room, name)
        if os.path.lexists(path):
            os.unlink(path)
        extra = {}
        if furnished:
            extra["PATH"] = os.path.join(furnished, "bin") + os.pathsep + os.environ.get("PATH", os.defpath)
        result = run.run_gate(step["run"], room, parsed, env=extra)
        status = result["status"]
        if status == "ok" and not _compare_pin(source, room, name):
            status = "mismatch"
        gates.append({"output": name, "status": status,
                      "quarantine": result["quarantine"],
                      "stdout": result["stdout"], "stderr": result["stderr"]})
    return gates


def audit(directory, *, shallow=False):
    """Run the gates on a fresh copy of the current generated bytes."""
    try:
        verification = seal.verify(directory)
        if not verification["ok"]:
            return {"ok": False, "root": verification["root"], "gates": [],
                    "verdict": "identity mismatch"}
        parsed = recipe.load_recipe(directory)
        with tempfile.TemporaryDirectory(prefix="reticuli-audit-") as room:
            _materialize(directory, room, parsed, generated=True)
            gates = _judge(directory, room, parsed)
        ok = all(row["status"] == "ok" for row in gates)
        return {"ok": ok, "root": verification["root"], "gates": gates,
                "verdict": "earned" if ok else "broken"}
    except core.ClaimError as exc:
        return {"ok": False, "gates": [], "verdict": str(exc)}


def rebuild(directory, producer, into, *, produce_from=None, input_from=None,
            guidance=True, producer_env=None):
    """Build generated outputs in a fresh room and seal on matching pins."""
    verification = seal.verify(directory)
    if not verification["ok"]:
        raise core.ClaimError("source identity mismatch")
    parsed = recipe.load_recipe(directory)
    if os.path.exists(into) and os.listdir(into):
        raise core.ClaimError(f"rebuild target is not empty: {into}")
    _materialize(directory, into, parsed)
    if input_from:
        for name in recipe._inputs(parsed, directory):
            core._copy_into(core._safe(input_from, name), core._safe(into, name))
    if produce_from:
        for name in recipe.generated_outputs(parsed):
            source_path = core._safe(produce_from, name)
            if os.path.lexists(source_path):
                core._copy_into(source_path, core._safe(into, name))
    produced = []
    for step in recipe.produces(parsed):
        if step.get("class", "generated") != "generated" or "from" in step:
            continue
        result = _produce(producer, into, step, parsed, guidance=guidance,
                          producer_env=producer_env)
        produced.append(result)
        event = {"kind": "producer", "seconds": result["seconds"],
                 "quarantine": result["quarantine"]}
        event.update(_read_usage(into))
        run.ledger(into, event)
        if result["status"] != "ok":
            return {"ok": False, "root": None, "gates": [], "producer": produced,
                    "quarantine": result["quarantine"], "verdict": result["status"]}
    gates = _judge(directory, into, parsed)
    if any(row["status"] != "ok" for row in gates):
        return {"ok": False, "root": None, "gates": gates,
                "quarantine": gates[-1]["quarantine"] if gates else "none",
                "verdict": "broken"}
    manifest = seal.seal(into)
    ok = manifest["root"] == verification["root"]
    return {"ok": ok, "root": manifest["root"], "gates": gates,
            "quarantine": produced[-1]["quarantine"] if produced else "none",
            "verdict": "earned" if ok else "identity mismatch"}
