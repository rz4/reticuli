"""Materialize claims, regrow generated outputs, and re-earn gate verdicts."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time

from . import core, identity, recipe, run, seal


def _toml_value(value):
    """Write the small TOML value vocabulary accepted by the recipe reader."""
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{_toml_value(k)} = {_toml_value(v)}"
                                for k, v in value.items()) + " }"
    raise core.ClaimError(f"cannot write TOML value: {value!r}")


def _toml_recipe(parsed):
    lines = []
    for table, values in parsed.items():
        if table == "step":
            for step in values:
                lines.extend(("", "[[step]]"))
                lines.extend(f"{_toml_value(k)} = {_toml_value(v)}"
                             for k, v in step.items())
        elif isinstance(values, dict):
            lines.extend(("", f"[{table}]"))
            lines.extend(f"{_toml_value(k)} = {_toml_value(v)}"
                         for k, v in values.items())
        else:
            lines.append(f"{_toml_value(table)} = {_toml_value(values)}")
    return "\n".join(lines).lstrip("\n") + "\n"


def _materialize(source, destination, parsed=None, generated=False):
    """Make a judging room from declared inputs and, optionally, present outputs."""
    parsed = parsed or recipe.load_recipe(source)
    os.makedirs(destination, exist_ok=True)
    source_recipe = recipe.recipe_path(source)
    room_recipe = os.path.join(destination, os.path.basename(source_recipe))
    if identity._claim_format(parsed) >= 3:
        with open(room_recipe, "w", encoding="utf-8") as stream:
            stream.write(_toml_recipe(identity._preimage_recipe(parsed)))
    else:
        core._copy_into(source_recipe, room_recipe)
    for name in recipe._inputs(parsed, source):
        core._copy_into(core._safe(source, name), core._safe(destination, name))
    for step in recipe._steps(parsed):
        if step["kind"] == "gate":
            continue
        name = step["output"]
        klass = step.get("class", "generated")
        if klass not in ("generated", "free") or generated or "from" in step:
            path = core._safe(source, name)
            if os.path.isfile(path):
                core._copy_into(path, core._safe(destination, name))
    return destination


def _compare_pin(source, room, name):
    try:
        return core._hash_file(core._safe(source, name)) == core._hash_file(
            core._safe(room, name))
    except core.ClaimError:
        return False


def _step_guidance(step):
    return step.get("guidance", step.get("request", ""))


def _read_usage(directory):
    try:
        with open(os.path.join(directory, core.USAGE), encoding="utf-8") as stream:
            value = json.load(stream)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _authorized(directory):
    """Require the original room to match its recorded identity."""
    result = seal.verify(directory)
    if not result["ok"]:
        raise core.ClaimError("claim identity does not match its seal")
    return result


def _ssh_verify(*args, **kwargs):
    """Compatibility seam for optional signature verification."""
    try:
        return subprocess.run(["ssh-keygen", "-Y", "verify", *args],
                              **kwargs).returncode == 0
    except OSError:
        return False


def _produce(command, directory, step, parsed, guidance=True, producer_env=None):
    env = run._scrub_env()
    # Producers act with the caller's HOME and reachability. Only gates are jailed.
    if "HOME" in os.environ:
        env["HOME"] = os.environ["HOME"]
    outputs = recipe.generated_outputs(parsed)
    env[core._ENV_CLAIM] = os.path.realpath(directory)
    env[core._ENV_OUTPUT] = core._safe(directory, step["output"])
    env[core._ENV_OUTPUTS] = json.dumps(outputs)
    if guidance:
        env[core._ENV_REQUEST] = str(_step_guidance(step))
    if producer_env:
        env.update(producer_env)
    start = time.monotonic()
    result = run._run(["/bin/sh", "-c", command], directory,
                      core.PRODUCER_TIMEOUT, env)
    if result.get("timeout") or result["returncode"] != 0:
        detail = result.get("stderr", "").strip()[-500:]
        raise core.ClaimError(f"producer failed for {step['output']}: {detail}")
    return time.monotonic() - start


def _run_gates(source, room, parsed):
    gates = []
    for step in recipe.gates(parsed):
        name = step["output"]
        result = run.run_gate(step["run"], room, parsed)
        if result["status"] == "ok" and not _compare_pin(source, room, name):
            result["status"] = "mismatch"
        result["output"] = name
        gates.append(result)
    return gates


def audit(directory, *, shallow=False):
    """Re-run gates cold on the current generated bytes and compare pinned bytes."""
    try:
        verified = _authorized(directory)
        parsed = recipe.load_recipe(directory)
        with tempfile.TemporaryDirectory(prefix="reticuli-audit-") as room:
            _materialize(directory, room, parsed, generated=True)
            gates = _run_gates(directory, room, parsed)
        ok = all(g["status"] == "ok" for g in gates)
        return {"ok": ok, "root": verified["root"], "gates": gates,
                "verdict": "earned" if ok else "broken"}
    except (core.ClaimError, OSError) as exc:
        return {"ok": False, "gates": [], "verdict": str(exc)}


def rebuild(directory, producer, into, *, produce_from=None, input_from=None,
            guidance=True, producer_env=None):
    """Regrow generated outputs from pinned inputs and seal a matching room."""
    verified = _authorized(directory)
    parsed = recipe.load_recipe(directory)
    if os.path.exists(into) and os.listdir(into):
        raise core.ClaimError(f"rebuild destination is not empty: {into}")
    _materialize(directory, into, parsed, generated=False)
    duration = 0.0
    for step in recipe.produces(parsed):
        if step.get("class", "generated") in ("generated", "free") and "from" not in step:
            duration += _produce(producer, into, step, parsed, guidance, producer_env)
            if not os.path.isfile(core._safe(into, step["output"])):
                raise core.ClaimError(f"producer omitted {step['output']}")
    gates = _run_gates(directory, into, parsed)
    if any(g["status"] != "ok" for g in gates):
        raise core.ClaimError(f"rebuild gates did not reproduce: {gates!r}")
    root = identity.root(recipe.load_recipe(into), into)
    if root != verified["root"]:
        raise core.ClaimError("rebuild root does not match original")
    seal.seal(into)
    quarantine = gates[0]["quarantine"] if gates else run.sandbox_backend()
    run.ledger(into, {"seconds": duration, "calls": len(recipe.generated_outputs(parsed)),
                      "quarantine": quarantine})
    return {"root": root, "gates": gates, "quarantine": quarantine,
            "build_digest": identity.build_digest(into)}
