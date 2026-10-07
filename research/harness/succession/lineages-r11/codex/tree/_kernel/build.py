"""Materialize, audit, and rebuild claims from their pinned criteria."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time

from . import core, identity, recipe, run, seal


sandbox_backend = run.sandbox_backend


def _step_guidance(step: dict, guidance: bool = True) -> str:
    if not guidance:
        return ""
    return step.get("guidance", step.get("request", ""))


def _authorized(directory: str) -> bool:
    """Whether the bytes still belong to the sealed identity."""
    try:
        return seal.verify(directory)["ok"]
    except core.ClaimError:
        return False


def _compare_pin(source: str, room: str, name: str) -> bool:
    """Compare one generated verdict with the source's pinned bytes."""
    try:
        return (core._hash_file(core._safe(source, name)) ==
                core._hash_file(core._safe(room, name)))
    except core.ClaimError:
        return False


def _materialize(source: str, room: str, parsed: dict, *,
                 generated: bool = False) -> None:
    """Copy the declared inputs into an isolated judging room."""
    os.makedirs(room, exist_ok=True)
    recipe_name = os.path.basename(recipe.recipe_path(source))
    source_recipe = core._safe(source, recipe_name)
    target_recipe = core._safe(room, recipe_name)
    if parsed["claim"].get("format", 1) >= 3:
        # The preimage excludes hints; a gate reading its recipe must see the
        # same acceptance boundary that the root identifies.
        with open(source_recipe, encoding="utf-8") as stream:
            lines = stream.readlines()
        lines = [line for line in lines if not line.lstrip().startswith(("guidance =", "request ="))]
        with open(target_recipe, "w", encoding="utf-8") as stream:
            stream.writelines(lines)
    else:
        core._copy_into(source_recipe, target_recipe)
    for name in recipe._inputs(parsed, source):
        core._copy_into(core._safe(source, name), core._safe(room, name))
    for step in parsed.get("step", []):
        if step.get("kind") != "produce":
            continue
        if generated or "from" in step:
            name = step["output"]
            src = core._safe(source, name)
            if os.path.isfile(src):
                core._copy_into(src, core._safe(room, name))


def _read_usage(room: str) -> dict:
    path = os.path.join(room, core.USAGE)
    try:
        with open(path, encoding="utf-8") as stream:
            data = json.load(stream)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {key: value for key in ("usd", "tokens", "calls")
            if (value := data.get(key)) is not None
            and isinstance(value, (int, float)) and not isinstance(value, bool)
            and value >= 0}


def _produce(command: str, room: str, output: str, outputs: list[str],
             request: str = "", producer_env: dict | None = None) -> dict:
    """Run the caller's producer with its HOME and access to its services."""
    env = run._scrub_env(room, "none")
    if "HOME" in os.environ:
        env["HOME"] = os.environ["HOME"]
    env.update(producer_env or {})
    env[core._ENV_CLAIM] = os.path.abspath(room)
    env[core._ENV_OUTPUT] = os.path.abspath(core._safe(room, output))
    env[core._ENV_OUTPUTS] = json.dumps(outputs)
    env[core._ENV_REQUEST] = request
    started = time.monotonic()
    result = run._run([core._SHELL, "-c", command], room, env,
                      core.PRODUCER_TIMEOUT)
    result["seconds"] = time.monotonic() - started
    result["quarantine"] = "inherited" if os.environ.get(core._JAILED) else "none"
    return result


def _ssh_verify(signature: str, message: bytes, allowed_signers: str,
                identity_name: str, namespace: str = core.SIGN_NAMESPACE) -> bool:
    """Check a detached SSH signature against the caller's trust anchor."""
    try:
        completed = subprocess.run(
            ["ssh-keygen", "-Y", "verify", "-f", allowed_signers,
             "-I", identity_name, "-n", namespace, "-s", signature],
            input=message, capture_output=True, check=False, timeout=15)
        return completed.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _judge(source: str, room: str, parsed: dict) -> list[dict]:
    rows = []
    missing = run.preflight(parsed)
    for step in recipe.gates(parsed):
        name = step["output"]
        if missing:
            row = {"output": name, "status": "environment",
                   "quarantine": sandbox_backend(), "missing": missing}
        else:
            outcome = run.run_gate(step["run"], room, parsed)
            status = outcome["status"]
            if status == "ok":
                status = "reproduced" if _compare_pin(source, room, name) else "mismatch"
            row = {"output": name, "status": status,
                   "quarantine": outcome["quarantine"],
                   "stderr": outcome.get("stderr", "")}
        rows.append(row)
    return rows


def audit(directory: str, *, shallow: bool = False) -> dict:
    """Re-earn every gate from current bytes in a fresh room."""
    try:
        verified = seal.verify(directory)
        if not verified["ok"]:
            return {"ok": False, "root": verified["root"],
                    "gates": [], "verdict": "identity mismatch"}
        parsed = recipe.load_recipe(directory)
        with tempfile.TemporaryDirectory(prefix="reticuli-audit-") as room:
            _materialize(directory, room, parsed, generated=True)
            rows = _judge(directory, room, parsed)
        ok = all(row["status"] in ("ok", "reproduced") for row in rows)
        return {"ok": ok, "root": verified["root"], "gates": rows,
                "verdict": "earned" if ok else "carried or broken"}
    except (core.ClaimError, OSError) as exc:
        return {"ok": False, "gates": [], "verdict": str(exc)}


def rebuild(directory: str, producer: str, into: str, *,
            produce_from: str | None = None, input_from: str | None = None,
            guidance: bool = True, producer_env: dict | None = None) -> dict:
    """Regrow generated outputs from pinned inputs and seal a passing room."""
    parsed = recipe.load_recipe(directory)
    source = input_from or directory
    if not _authorized(directory):
        raise core.ClaimError("source claim identity does not verify")
    os.makedirs(into, exist_ok=True)
    _materialize(source, into, parsed)
    outputs = recipe.generated_outputs(parsed)
    production = []
    for step in recipe.produces(parsed):
        if step["output"] not in outputs:
            continue
        outcome = _produce(producer, into, step["output"], outputs,
                           _step_guidance(step, guidance), producer_env)
        production.append(outcome)
        if outcome["status"] != "ok":
            raise core.ClaimError(
                f"producer failed for {step['output']}: {outcome.get('stderr', '')}")
    rows = _judge(directory, into, parsed)
    if any(row["status"] not in ("ok", "reproduced") for row in rows):
        raise core.ClaimError(f"rebuilt gates did not reproduce: {rows}")
    sealed = seal.seal(into)
    usage = _read_usage(into)
    run.ledger(into, {"when": core._now(), "seconds": sum(p["seconds"] for p in production),
                      "calls": len(production), "quarantine": sandbox_backend(), **usage})
    return {"root": sealed["root"], "gates": rows,
            "build_digest": identity.build_digest(into),
            "quarantine": "inherited" if os.environ.get(core._JAILED) else "none"}
