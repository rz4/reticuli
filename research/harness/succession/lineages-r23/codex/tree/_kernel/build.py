"""Materialize claims, run producers, and re-earn gate verdicts."""

from __future__ import annotations

import json
import os
import shutil
import tempfile

from . import core, identity, recipe as recipe_module, run, seal


def _toml_value(value):
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if type(value) is bool:
        return "true" if value else "false"
    if type(value) in (int, float):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{_toml_key(key)} = {_toml_value(item)}"
                                 for key, item in value.items()) + " }"
    raise core.ClaimError(f"cannot write TOML value: {value!r}")


def _toml_key(key):
    import re
    return key if re.fullmatch(r"[A-Za-z0-9_-]+", key) else json.dumps(key)


def _room_recipe(recipe):
    """Render the identity-bearing recipe as parseable TOML."""
    preimage = identity._preimage_recipe(recipe)
    lines = []
    for key, value in preimage.items():
        if isinstance(value, dict):
            lines.append(f"[{_toml_key(key)}]")
            for field, item in value.items():
                lines.append(f"{_toml_key(field)} = {_toml_value(item)}")
            lines.append("")
        elif key == "step":
            for step in value:
                lines.append("[[step]]")
                for field, item in step.items():
                    lines.append(f"{_toml_key(field)} = {_toml_value(item)}")
                lines.append("")
        else:
            lines.append(f"{_toml_key(key)} = {_toml_value(value)}")
    return "\n".join(lines).rstrip() + "\n"


def _materialize(source, target, claim_recipe=None, *, generated=False,
                 produce_from=None, input_from=None):
    """Make a fresh judging room from declared bytes only."""
    claim_recipe = claim_recipe or recipe_module.load_recipe(source)
    os.makedirs(target, exist_ok=True)
    source_recipe = recipe_module.recipe_path(source)
    recipe_name = os.path.basename(source_recipe)
    destination = core._safe(target, recipe_name)
    if claim_recipe["claim"].get("format", 1) >= 3:
        with open(destination, "w", encoding="utf-8") as stream:
            stream.write(_room_recipe(claim_recipe))
    else:
        core._copy_into(source_recipe, destination)
    for name in recipe_module._inputs(claim_recipe, source):
        origin = input_from or source
        core._copy_into(core._safe(origin, name), core._safe(target, name))
    for step in recipe_module._steps(claim_recipe):
        name = step["output"]
        klass = step.get("class", "generated" if step["kind"] == "produce" else "pinned")
        if klass == "generated":
            if generated:
                origin = produce_from or source
                path = core._safe(origin, name)
                if os.path.isfile(path):
                    core._copy_into(path, core._safe(target, name))
        elif step["kind"] != "gate":
            core._copy_into(core._safe(source, name), core._safe(target, name))
    return target


def _step_guidance(step):
    return step.get("guidance", step.get("request", ""))


def _read_usage(directory):
    path = core._safe(directory, core.USAGE)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as stream:
            value = json.load(stream)
    except (OSError, ValueError) as exc:
        raise core.ClaimError(f"invalid producer usage: {exc}") from exc
    if not isinstance(value, dict):
        raise core.ClaimError("producer usage must be an object")
    return {key: number for key, number in value.items()
            if key in ("usd", "tokens", "calls")
            and type(number) in (int, float) and number >= 0}


def _produce(command, directory, claim_recipe, step, *, guidance=True,
             producer_env=None):
    outputs = recipe_module.generated_outputs(claim_recipe)
    extra = {
        core._ENV_CLAIM: claim_recipe["claim"]["name"],
        core._ENV_OUTPUT: core._safe(directory, step["output"]),
        core._ENV_OUTPUTS: json.dumps(outputs),
    }
    if guidance:
        extra[core._ENV_REQUEST] = _step_guidance(step)
    if producer_env:
        extra.update(producer_env)
    # The producer is the caller's oracle: preserve its HOME and ambient
    # reachability. Only gates acquire the kernel's sandbox.
    env = run._scrub_env(extra=extra)
    if "HOME" in os.environ:
        env["HOME"] = os.environ["HOME"]
    result = run._run(["/bin/sh", "-c", command], directory, env,
                      core.PRODUCER_TIMEOUT)
    event = {"kind": "producer", "output": step["output"],
             "status": result["status"], "seconds": result["seconds"],
             "calls": 1, "quarantine": run.sandbox_backend() if os.environ.get(core._JAILED) else "none"}
    event.update(_read_usage(directory))
    run.ledger(directory, event)
    return result


def _compare_pin(source, room, name):
    try:
        return core._hash_file(core._safe(source, name)) == core._hash_file(core._safe(room, name))
    except core.ClaimError:
        return False


def _judge(source, room, claim_recipe):
    rows = []
    missing = run.preflight(claim_recipe)
    try:
        furnished = run.furnish(room, claim_recipe)
    except core.ClaimError as exc:
        furnished = None
        missing.append(str(exc))
    for step in recipe_module.gates(claim_recipe):
        name = step["output"]
        if missing:
            result = {"status": "environment", "stderr": ", ".join(missing),
                      "quarantine": run.sandbox_backend()}
        else:
            env = {}
            if furnished:
                env["PATH"] = os.path.join(furnished, "bin") + os.pathsep + os.environ.get("PATH", os.defpath)
            result = run.run_gate(step["run"], room, claim_recipe, env)
        status = result["status"]
        if status == "ok":
            status = "reproduced" if _compare_pin(source, room, name) else "mismatch"
        rows.append({"output": name, "status": status,
                     "quarantine": result["quarantine"],
                     "stderr": result.get("stderr", "")})
    return rows


def _authorized(directory, anchor=None):
    """Whether a local sealed identity is still present and intact."""
    try:
        return seal.verify(directory)["ok"]
    except core.ClaimError:
        return False


def _ssh_verify(data, signature, allowed_signers, identity_name="reticuli"):
    """Check a detached SSH signature against a caller-provided anchor."""
    import subprocess
    try:
        done = subprocess.run(
            ["ssh-keygen", "-Y", "verify", "-f", os.fspath(allowed_signers),
             "-I", identity_name, "-n", core.SIGN_NAMESPACE,
             "-s", os.fspath(signature)], input=data, capture_output=True,
            check=False, timeout=10)
        return done.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def audit(directory, *, deep=True, **_):
    """Re-run each gate cold and compare its verdict bytes to sealed pins."""
    try:
        verified = seal.verify(directory)
        claim_recipe = recipe_module.load_recipe(directory)
        if not verified["ok"]:
            return {"ok": False, "root": verified["root"], "gates": [],
                    "verdict": "identity mismatch"}
        with tempfile.TemporaryDirectory(prefix="reticuli-audit-") as room:
            _materialize(directory, room, claim_recipe, generated=True)
            rows = _judge(directory, room, claim_recipe)
        ok = all(row["status"] in ("ok", "reproduced") for row in rows)
        return {"ok": ok, "name": claim_recipe["claim"]["name"],
                "root": verified["root"], "gates": rows,
                "verdict": "earned" if ok else "carried or broken"}
    except core.ClaimError as exc:
        return {"ok": False, "gates": [], "verdict": str(exc)}


def rebuild(directory, producer, into, *, produce_from=None, input_from=None,
            guidance=True, producer_env=None):
    """Regrow generated outputs in a fresh room and seal if gates re-earn."""
    verified = seal.verify(directory)
    if not verified["ok"]:
        raise core.ClaimError("source claim identity mismatch")
    claim_recipe = recipe_module.load_recipe(directory)
    if os.path.exists(into) and os.listdir(into):
        raise core.ClaimError(f"rebuild target is not empty: {into}")
    _materialize(directory, into, claim_recipe, produce_from=produce_from,
                 input_from=input_from)
    produces = [step for step in recipe_module.produces(claim_recipe)
                if step.get("class", "generated") == "generated" and "from" not in step]
    for step in produces:
        result = _produce(producer, into, claim_recipe, step,
                          guidance=guidance, producer_env=producer_env)
        if result["status"] != "ok":
            raise core.ClaimError(f"producer failed for {step['output']}: {result['stderr']}")
    rows = _judge(directory, into, claim_recipe)
    if not all(row["status"] in ("ok", "reproduced") for row in rows):
        raise core.ClaimError(f"rebuild gates did not reproduce: {rows}")
    manifest = seal.seal(into)
    if manifest["root"] != verified["root"]:
        raise core.ClaimError("rebuild root mismatch")
    return {"root": manifest["root"], "name": manifest["name"],
            "gates": rows, "quarantine": rows[0]["quarantine"] if rows else run.sandbox_backend(),
            "build_digest": identity.build_digest(into)}
