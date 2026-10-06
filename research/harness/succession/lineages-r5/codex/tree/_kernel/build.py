"""Materialize claims, rebuild generated outputs, and re-earn gate verdicts."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile

from . import core, identity, recipe as recipe_module, run, seal


def sandbox_backend() -> str:
    return run.sandbox_backend()


def _step_guidance(step: dict) -> str:
    return step.get("guidance", step.get("request", ""))


def _compare_pin(source: str, room: str, name: str) -> bool:
    """Compare a newly earned output with its pinned bytes."""
    try:
        return core._hash_file(core._safe(source, name)) == core._hash_file(core._safe(room, name))
    except core.ClaimError:
        return False


def _materialize(source: str, room: str, recipe: dict, *, generated: bool = False) -> None:
    """Make a judging room from declared files, without carrying verdicts."""
    os.makedirs(room, exist_ok=True)
    source_recipe = recipe_module.recipe_path(source)
    target_recipe = core._safe(room, os.path.basename(source_recipe))
    core._copy_into(source_recipe, target_recipe)
    if recipe["claim"].get("format", 1) >= 3:
        # The judging room must present the same hint-free recipe the root
        # names. Retain the source recipe for formats whose hints are pinned.
        data = open(source_recipe, "r", encoding="utf-8").read()
        lines = data.splitlines(keepends=True)
        filtered = []
        producing = False
        for line in lines:
            stripped = line.strip()
            if stripped == "[[step]]":
                producing = False
            elif stripped.startswith("kind") and "=" in stripped:
                producing = stripped.split("=", 1)[1].strip().strip('"\'') == "produce"
            if producing and any(stripped.startswith(key + " ") or stripped.startswith(key + "=")
                                 for key in core.GUIDANCE_KEYS):
                continue
            filtered.append(line)
        with open(target_recipe, "w", encoding="utf-8") as stream:
            stream.writelines(filtered)
    for name in recipe_module._inputs(recipe, source):
        core._copy_into(core._safe(source, name), core._safe(room, name))
    for step in recipe_module.produces(recipe):
        name = step["output"]
        if step.get("class", "generated") != "generated" or (generated and os.path.isfile(core._safe(source, name))):
            core._copy_into(core._safe(source, name), core._safe(room, name))


def _read_usage(directory: str) -> dict:
    path = core._safe(directory, core.USAGE)
    try:
        with open(path, encoding="utf-8") as stream:
            value = json.load(stream)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _authorized(*args, **kwargs) -> bool:
    """Authorization is outside this local build layer."""
    return False


def _ssh_verify(signature: str, data: bytes, allowed_signers: str,
                namespace: str = core.SIGN_NAMESPACE, identity_name: str = "reticuli") -> bool:
    try:
        result = subprocess.run(
            ["ssh-keygen", "-Y", "verify", "-f", allowed_signers,
             "-I", identity_name, "-n", namespace, "-s", signature],
            input=data, capture_output=True, timeout=15)
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _produce(command: str, directory: str, recipe: dict, step: dict,
             *, guidance: bool = True, producer_env: dict | None = None) -> dict:
    """Run the caller's producer with a scrubbed environment and no jail."""
    env = run._scrub_env(extra=producer_env)
    env[core._ENV_CLAIM] = recipe["claim"]["name"]
    env[core._ENV_OUTPUT] = step["output"]
    if guidance:
        env[core._ENV_REQUEST] = _step_guidance(step)
    return run._run([core._SHELL, "-c", command], directory,
                    core.PRODUCER_TIMEOUT, env)


def _judge(source: str, room: str, recipe: dict) -> list[dict]:
    missing = run.preflight(recipe)
    if missing:
        return [{"output": step["output"], "status": "environment",
                 "detail": "missing requirements: " + ", ".join(missing),
                 "quarantine": run.sandbox_backend()}
                for step in recipe_module.gates(recipe)]
    try:
        venv_bin = run.furnish(room, recipe)
    except core.ClaimError as exc:
        return [{"output": step["output"], "status": "environment",
                 "detail": str(exc), "quarantine": run.sandbox_backend()}
                for step in recipe_module.gates(recipe)]
    rows = []
    for step in recipe_module.gates(recipe):
        extra = {"PATH": venv_bin + os.pathsep + os.environ.get("PATH", os.defpath)} if venv_bin else None
        result = run.run_gate(step["run"], room, recipe, extra)
        status = result["status"]
        if status == "ok" and not _compare_pin(source, room, step["output"]):
            status = "mismatch"
        rows.append({"output": step["output"], "status": status,
                     "quarantine": result["quarantine"],
                     "sandbox": result["quarantine"],
                     "detail": result.get("stderr", "")})
    return rows


def audit(directory: str, *, deep: bool = True) -> dict:
    """Check identity, then run every gate cold against present generated bytes."""
    try:
        verified = seal.verify(directory)
        if not verified["ok"]:
            return {"ok": False, "root": verified["root"], "gates": [],
                    "verdict": "identity mismatch"}
        recipe = recipe_module.load_recipe(directory)
        with tempfile.TemporaryDirectory(prefix="reticuli-audit-") as room:
            _materialize(directory, room, recipe, generated=True)
            rows = _judge(directory, room, recipe)
        ok = all(row["status"] == "ok" for row in rows)
        return {"ok": ok, "root": verified["root"], "gates": rows,
                "verdict": "earned" if ok else "carried or broken"}
    except core.ClaimError as exc:
        return {"ok": False, "gates": [], "verdict": str(exc)}


def rebuild(directory: str, producer: str, into: str, *,
            produce_from: str | None = None, input_from: str | None = None,
            guidance: bool = True, producer_env: dict | None = None) -> dict:
    """Regrow generated outputs and seal a claim after its gates re-earn."""
    source = input_from or directory
    recipe = recipe_module.load_recipe(source)
    if os.path.exists(into) and os.listdir(into):
        raise core.ClaimError(f"rebuild target is not empty: {into}")
    _materialize(source, into, recipe)
    production = []
    for step in recipe_module.produces(recipe):
        if "from" in step:
            if produce_from:
                core._copy_into(core._safe(produce_from, step["output"]),
                                core._safe(into, step["output"]))
            continue
        result = _produce(producer, into, recipe, step, guidance=guidance,
                          producer_env=producer_env)
        production.append(result)
        if result["status"] != "ok":
            raise core.ClaimError(f"producer failed: {result.get('stderr', '')}")
    rows = _judge(source, into, recipe)
    if not all(row["status"] == "ok" for row in rows):
        raise core.ClaimError(f"rebuild gates did not re-earn: {rows!r}")
    manifest = seal.seal(into)
    run.ledger(into, {"kind": "producer", "seconds": sum(r["seconds"] for r in production),
                      "quarantine": run.sandbox_backend()})
    return {"root": manifest["root"], "name": manifest["name"], "gates": rows,
            "build_digest": identity.build_digest(into),
            "quarantine": run.sandbox_backend()}
