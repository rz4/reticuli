"""Cold auditing and reconstruction of a sealed claim."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time

from . import core, identity, recipe, run, seal


def _authorized(directory: str) -> dict:
    """Require that the pinned bytes still name the sealed claim."""
    result = seal.verify(directory)
    if not result["ok"]:
        raise core.ClaimError("sealed claim identity does not match present bytes")
    return result


def _compare_pin(source: str, room: str, name: str) -> bool:
    try:
        return (core._hash_file(core._safe(source, name)) ==
                core._hash_file(core._safe(room, name)))
    except core.ClaimError:
        return False


def _toml_value(value: object) -> str:
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=True)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{key} = {_toml_value(item)}"
                                 for key, item in value.items()) + " }"
    raise core.ClaimError(f"cannot write recipe value: {value!r}")


def _room_recipe(parsed: dict) -> str:
    """Write the format-3+ preimage as parseable TOML."""
    preimage = identity._preimage_recipe(parsed)
    lines = ["[claim]"]
    for key, value in preimage["claim"].items():
        lines.append(f"{key} = {_toml_value(value)}")
    for step in preimage.get("step", []):
        lines.extend(("", "[[step]]"))
        for key, value in step.items():
            lines.append(f"{key} = {_toml_value(value)}")
    return "\n".join(lines) + "\n"


def _materialize(source: str, room: str, parsed: dict,
                 include_generated: bool = False) -> None:
    """Make a judging room from declared inputs and allowed outputs."""
    os.makedirs(room, exist_ok=True)
    recipe_name = os.path.basename(recipe.recipe_path(source))
    destination = core._safe(room, recipe_name)
    if parsed["claim"].get("format", 1) >= 3:
        with open(destination, "w", encoding="utf-8") as stream:
            stream.write(_room_recipe(parsed))
    else:
        core._copy_into(core._safe(source, recipe_name), destination)
    for name in recipe._inputs(parsed, source):
        core._copy_into(core._safe(source, name), core._safe(room, name))
    for step in recipe._steps(parsed):
        if step["kind"] == "gate":
            continue
        name = step["output"]
        generated = step.get("class", "generated") in ("generated", "free")
        if generated and not include_generated and "from" not in step:
            continue
        path = core._safe(source, name)
        if os.path.lexists(path):
            core._copy_into(path, core._safe(room, name))


def _step_guidance(step: dict) -> str:
    return str(step.get("guidance", step.get("request", "")))


def _read_usage(room: str) -> dict:
    path = core._safe(room, core.USAGE)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as stream:
            payload = json.load(stream)
        return payload if isinstance(payload, dict) else {}
    except (OSError, ValueError):
        return {}


def _produce(command: str, room: str, parsed: dict, step: dict,
             guidance: bool = True, producer_env: dict | None = None) -> dict:
    """Run the caller's producer with its own HOME and reachability."""
    env = {key: os.environ[key] for key in core._KEEP_ENV if key in os.environ}
    env.setdefault("PATH", os.defpath)
    env[core._ENV_CLAIM] = parsed["claim"]["name"]
    env[core._ENV_OUTPUT] = os.path.abspath(core._safe(room, step["output"]))
    env[core._ENV_OUTPUTS] = json.dumps(recipe.generated_outputs(parsed))
    if guidance:
        env[core._ENV_REQUEST] = _step_guidance(step)
    if producer_env:
        env.update({str(key): str(value) for key, value in producer_env.items()})
    result = run._run([core._SHELL, "-c", command], room, env,
                      core.PRODUCER_TIMEOUT)
    result["quarantine"] = "inherited" if os.environ.get(core._JAILED) else "none"
    return result


def _ssh_verify(data: bytes, signature: str, anchor: str,
                namespace: str = core.SIGN_NAMESPACE) -> bool:
    try:
        done = subprocess.run(["ssh-keygen", "-Y", "verify", "-f", anchor,
                               "-I", "reticuli", "-n", namespace,
                               "-s", signature], input=data,
                              capture_output=True, timeout=30)
        return done.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _judge(source: str, room: str, parsed: dict) -> list[dict]:
    results = []
    for step in recipe.gates(parsed):
        name = step["output"]
        output = core._safe(room, name)
        if os.path.lexists(output):
            os.unlink(output)
        outcome = run.run_gate(step["run"], room, parsed)
        row = {"output": name, "status": outcome["status"],
               "quarantine": outcome["quarantine"]}
        if outcome["status"] == "ok":
            row["status"] = "reproduced" if _compare_pin(source, room, name) else "mismatch"
        if outcome.get("stderr"):
            row["detail"] = outcome["stderr"][-500:]
        results.append(row)
    return results


def audit(directory: str, shallow: bool = False) -> dict:
    """Re-earn each gate against the present generated bytes."""
    try:
        verified = _authorized(directory)
        parsed = recipe.load_recipe(directory)
        with tempfile.TemporaryDirectory(prefix="reticuli-audit-") as room:
            _materialize(directory, room, parsed, include_generated=True)
            gates = _judge(directory, room, parsed)
        ok = all(g["status"] == "reproduced" for g in gates)
        return {"ok": ok, "root": verified["root"], "gates": gates,
                "verdict": "earned" if ok else "carried or broken"}
    except core.ClaimError as exc:
        return {"ok": False, "gates": [], "verdict": str(exc)}


def rebuild(directory: str, producer: str, into: str, *,
            produce_from: str | None = None, input_from: str | None = None,
            guidance: bool = True, producer_env: dict | None = None) -> dict:
    """Regrow generated outputs in a room and seal it after cold gates pass."""
    _authorized(directory)
    parsed = recipe.load_recipe(directory)
    if os.path.exists(into) and os.listdir(into):
        raise core.ClaimError(f"rebuild target is not empty: {into}")
    os.makedirs(into, exist_ok=True)
    _materialize(input_from or directory, into, parsed)
    outputs = recipe.generated_outputs(parsed)
    outcomes = []
    started = time.monotonic()
    for step in recipe.produces(parsed):
        if step["output"] not in outputs:
            continue
        outcome = _produce(producer, into, parsed, step, guidance, producer_env)
        outcomes.append(outcome)
        if outcome["status"] != "ok":
            raise core.ClaimError("producer failed: " +
                                  (outcome.get("stderr") or outcome["status"])[-500:])
        if not os.path.isfile(core._safe(into, step["output"])):
            raise core.ClaimError(f"producer did not write {step['output']}")
    gates = _judge(directory, into, parsed)
    if any(g["status"] != "reproduced" for g in gates):
        raise core.ClaimError(f"rebuild gates did not reproduce: {gates}")
    manifest = seal.seal(into)
    if manifest["root"] != seal.read_manifest(directory)["root"]:
        raise core.ClaimError("rebuilt root does not match source root")
    usage = _read_usage(into)
    event = {"kind": "producer", "seconds": time.monotonic() - started,
             "quarantine": outcomes[-1]["quarantine"] if outcomes else "none"}
    for key in ("usd", "tokens", "calls"):
        value = usage.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
            event[key] = value
    run.ledger(into, event)
    return {"root": manifest["root"], "gates": gates,
            "quarantine": event["quarantine"], "build_digest": identity.build_digest(into)}
