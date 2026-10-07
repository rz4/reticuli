"""Materialize claims, run producers, and re-earn gate verdicts."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

from . import core, identity, recipe, run, seal


def sandbox_backend() -> str:
    return run.sandbox_backend()


def _authorized(directory: str, output: str) -> bool:
    """Whether a declared output is an ordinary file in this claim."""
    try:
        core._hash_file(core._safe(directory, output))
        return True
    except core.ClaimError:
        return False


def _compare_pin(original: str, room: str, output: str) -> bool:
    """Compare a freshly earned output with the claim's pinned bytes."""
    return core._hash_file(core._safe(original, output)) == core._hash_file(
        core._safe(room, output))


def _materialize(source: str, destination: str, *, generated: bool = False) -> dict:
    """Create a judging room from the declared inputs and pinned outputs."""
    claim_recipe = recipe.load_recipe(source)
    os.makedirs(destination, exist_ok=True)
    source_recipe = recipe.recipe_path(source)
    core._copy_into(source_recipe, core._safe(destination, os.path.basename(source_recipe)))

    names = recipe._inputs(claim_recipe, source)
    environment = claim_recipe["claim"].get("environment")
    if environment is not None:
        names.append(environment)
    for step in recipe._steps(claim_recipe):
        step_class = step.get("class", "generated" if step["kind"] == "produce" else "pinned")
        if step["kind"] == "produce" and (step_class not in ("generated", "free") or generated):
            names.append(step["output"])
    for name in dict.fromkeys(names):
        source_path = core._safe(source, name)
        if os.path.lexists(source_path):
            core._copy_into(source_path, core._safe(destination, name))
        else:
            raise core.ClaimError(f"missing declared file: {name}")
    return claim_recipe


def _step_guidance(step: dict, guidance: bool = True) -> str:
    if not guidance:
        return ""
    return str(step.get("guidance", step.get("request", "")))


def _read_usage(directory: str) -> dict:
    """Read the producer's optional usage report, excluding measured time."""
    path = core._safe(directory, core.USAGE)
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(value, dict):
        return {}
    return {key: value[key] for key in ("usd", "tokens", "calls")
            if isinstance(value.get(key), (int, float)) and not isinstance(value[key], bool)
            and value[key] >= 0}


def _produce(directory: str, command: str, claim_recipe: dict,
             *, guidance: bool = True, producer_env: dict | None = None) -> dict:
    """Run the caller's producer without a gate sandbox."""
    env = run._scrub_env(directory, "none")
    # Credentials commonly live under HOME; a producer acts with its caller's
    # standing, while gates use the separately scrubbed judging environment.
    if "HOME" in os.environ:
        env["HOME"] = os.environ["HOME"]
    outputs = [s["output"] for s in recipe.produces(claim_recipe)
               if s.get("class", "generated") in ("generated", "free")
               and "from" not in s]
    env[core._ENV_OUTPUTS] = json.dumps(outputs)
    if len(outputs) == 1:
        env[core._ENV_OUTPUT] = outputs[0]
    hints = [_step_guidance(s, guidance) for s in recipe.produces(claim_recipe)
             if s["output"] in outputs]
    if guidance and any(hints):
        env[core._ENV_REQUEST] = "\n".join(hints)
    else:
        env.pop(core._ENV_REQUEST, None)
    if producer_env:
        env.update({str(key): str(value) for key, value in producer_env.items()})
    result = run._run([core._SHELL, "-c", command], directory, env,
                      core.PRODUCER_TIMEOUT)
    event = {"kind": "producer", "when": core._now(),
             "seconds": result["seconds"], "status": result["status"],
             "quarantine": "none", **_read_usage(directory)}
    run.ledger(directory, event)
    return result


def _ssh_verify(*args, **kwargs) -> bool:
    """Signature verification is optional for a local, unsigned rebuild."""
    return False


def _judge(source: str, room: str, claim_recipe: dict) -> list[dict]:
    gates = []
    missing = run.preflight(claim_recipe)
    furnished = run.furnish(room, claim_recipe) if not missing else {"status": "environment"}
    for step in recipe.gates(claim_recipe):
        output = step["output"]
        if missing or furnished["status"] != "ok":
            gates.append({"output": output, "status": "environment",
                          "quarantine": run.sandbox_backend(),
                          "detail": missing or furnished.get("detail")})
            continue
        environment = None
        if furnished.get("path"):
            environment = {"PATH": os.path.join(furnished["path"], "bin")
                           + os.pathsep + os.environ.get("PATH", os.defpath)}
        result = run.run_gate(step["run"], room, claim_recipe, environment)
        status = result["status"]
        if status == "ok":
            try:
                status = "ok" if _compare_pin(source, room, output) else "mismatch"
            except core.ClaimError:
                status = "mismatch"
        gates.append({"output": output, "status": status,
                      "quarantine": result["quarantine"],
                      "seconds": result["seconds"],
                      "stderr": result["stderr"]})
    return gates


def audit(directory: str, *, deep: bool = True) -> dict:
    """Run the gates cold against the present generated bytes."""
    try:
        verified = seal.verify(directory)
        if not verified["ok"]:
            return {"ok": False, "verdict": "identity mismatch", "gates": [],
                    "root": verified["root"]}
        with tempfile.TemporaryDirectory(prefix="reticuli-audit-") as room:
            claim_recipe = _materialize(directory, room, generated=True)
            gates = _judge(directory, room, claim_recipe)
        ok = all(g["status"] in ("ok", "reproduced") for g in gates)
        return {"ok": ok, "verdict": "earned" if ok else "carried or broken",
                "gates": gates, "root": verified["root"]}
    except core.ClaimError as exc:
        return {"ok": False, "verdict": str(exc), "gates": []}


def rebuild(directory: str, producer: str, into: str, *, produce_from: str | None = None,
            input_from: str | None = None, guidance: bool = True,
            producer_env: dict | None = None) -> dict:
    """Build generated outputs in a fresh room and seal a successful result."""
    verified = seal.verify(directory)
    if not verified["ok"]:
        raise core.ClaimError("source identity mismatch")
    source = input_from or directory
    if os.path.exists(into) and os.listdir(into):
        raise core.ClaimError(f"rebuild destination is not empty: {into}")
    claim_recipe = _materialize(source, into)
    if produce_from:
        for step in recipe.produces(claim_recipe):
            if step.get("class", "generated") in ("generated", "free") and "from" not in step:
                name = step["output"]
                core._copy_into(core._safe(produce_from, name), core._safe(into, name))
        produced = {"status": "ok", "seconds": 0.0}
    else:
        produced = _produce(into, producer, claim_recipe, guidance=guidance,
                            producer_env=producer_env)
    if produced["status"] != "ok":
        raise core.ClaimError(f"producer {produced['status']}: {produced.get('stderr', '')}")
    gates = _judge(directory, into, claim_recipe)
    if any(g["status"] not in ("ok", "reproduced") for g in gates):
        raise core.ClaimError(f"rebuild gates failed: {gates}")
    manifest = seal.seal(into)
    if manifest["root"] != verified["root"]:
        raise core.ClaimError("rebuilt identity differs from source")
    return {"ok": True, "root": manifest["root"], "gates": gates,
            "build_digest": identity.build_digest(into),
            "quarantine": gates[0]["quarantine"] if gates else run.sandbox_backend()}
