"""Materialize claims, re-earn their gates, and rebuild generated files."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from . import core, identity, recipe, run, seal


sandbox_backend = run.sandbox_backend


def _toml_value(value: Any) -> str:
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=True)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{json.dumps(k)} = {_toml_value(v)}"
                                  for k, v in value.items()) + " }"
    raise core.ClaimError(f"cannot materialize recipe value: {value!r}")


def _toml_recipe(parsed: dict[str, Any]) -> str:
    lines: list[str] = []
    for table, values in parsed.items():
        if table == "step":
            for step in values:
                lines.append("[[step]]")
                lines.extend(f"{json.dumps(k)} = {_toml_value(v)}" for k, v in step.items())
                lines.append("")
        elif isinstance(values, dict):
            lines.append(f"[{json.dumps(table)}]")
            lines.extend(f"{json.dumps(k)} = {_toml_value(v)}" for k, v in values.items())
            lines.append("")
        else:
            lines.append(f"{json.dumps(table)} = {_toml_value(values)}")
    return "\n".join(lines) + "\n"


def _materialize(source: os.PathLike[str] | str, destination: os.PathLike[str] | str,
                 *, generated: bool = True) -> dict[str, Any]:
    """Copy the declared judging inputs into an isolated room."""
    parsed = recipe.load_recipe(source)
    os.makedirs(destination, exist_ok=True)
    source_recipe = recipe.recipe_path(source)
    recipe_name = os.path.basename(source_recipe)
    target_recipe = core._safe(destination, recipe_name)
    if identity._claim_format(parsed) >= 3:
        Path(target_recipe).write_text(_toml_recipe(identity._preimage_recipe(parsed)),
                                       encoding="utf-8")
    else:
        core._copy_into(source_recipe, target_recipe)
    for name in recipe._inputs(parsed, source):
        core._copy_into(core._safe(source, name), core._safe(destination, name))
    for step in recipe._steps(parsed):
        if step["kind"] == "gate":
            continue
        name = step["output"]
        classification = step.get("class", "generated")
        if generated or classification not in ("generated", "free") or "from" in step:
            path = core._safe(source, name)
            if os.path.exists(path):
                core._copy_into(path, core._safe(destination, name))
    return parsed


def _compare_pin(source: os.PathLike[str] | str,
                 destination: os.PathLike[str] | str, name: str) -> bool:
    try:
        return core._hash_file(core._safe(source, name)) == core._hash_file(
            core._safe(destination, name))
    except core.ClaimError:
        return False


def _step_guidance(step: dict[str, Any]) -> str:
    return step.get("guidance", step.get("request", ""))


def _read_usage(directory: os.PathLike[str] | str) -> dict[str, Any]:
    path = core._safe(directory, core.USAGE)
    try:
        with open(path, encoding="utf-8") as stream:
            data = json.load(stream)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _ssh_verify(*args: Any, **kwargs: Any) -> bool:
    """Optional trust hook; a missing authorization never conveys trust."""
    return False


def _authorized(*args: Any, **kwargs: Any) -> bool:
    return _ssh_verify(*args, **kwargs)


def _produce(command: str, directory: os.PathLike[str] | str,
             parsed: dict[str, Any], *, guidance: bool = True,
             producer_env: dict[str, str] | None = None) -> dict[str, Any]:
    room = os.path.realpath(directory)
    hints = "\n".join(_step_guidance(step) for step in recipe.produces(parsed)) if guidance else ""
    outputs = [step["output"] for step in recipe.produces(parsed) if "from" not in step]
    extra = {core._ENV_REQUEST: hints, core._ENV_CLAIM: room,
             core._ENV_OUTPUT: outputs[0] if outputs else "",
             core._ENV_OUTPUTS: json.dumps(outputs)}
    if producer_env:
        extra.update(producer_env)
    env = run._scrub_env(room, "none", extra)
    # The producer is the caller's oracle. Only gates use the quarantine.
    env.pop(core._JAILED, None)
    result = run._run([core._SHELL, "-c", command], room, env,
                      core.PRODUCER_TIMEOUT)
    result["quarantine"] = "none"
    return result


def _judge(source: str, room: str, parsed: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    missing = run.preflight(parsed)
    furnished = None
    if not missing:
        try:
            furnished = run.furnish(parsed, room)
        except core.ClaimError as exc:
            missing = [str(exc)]
    gate_env = None
    if furnished:
        path = os.path.join(furnished, "Scripts" if os.name == "nt" else "bin")
        gate_env = {"PATH": path + os.pathsep + os.environ.get("PATH", os.defpath)}
    for step in recipe.gates(parsed):
        name = step["output"]
        if missing:
            row = {"output": name, "status": "environment", "detail": ", ".join(missing),
                   "quarantine": run.sandbox_backend()}
        else:
            target = core._safe(room, name)
            if os.path.exists(target):
                os.unlink(target)
            outcome = run.run_gate(step["run"], room, parsed, gate_env)
            status = outcome["status"]
            if status == "ok":
                status = "reproduced" if _compare_pin(source, room, name) else "mismatch"
            row = {"output": name, "status": status,
                   "quarantine": outcome["quarantine"],
                   "stdout": outcome.get("stdout", ""),
                   "stderr": outcome.get("stderr", "")}
        rows.append(row)
    return rows


def audit(directory: os.PathLike[str] | str, *args: Any,
          **kwargs: Any) -> dict[str, Any]:
    """Recheck identity and run every gate against present generated bytes."""
    source = os.path.realpath(directory)
    try:
        verified = seal.verify(source)
        if not verified["ok"]:
            return {"ok": False, "root": verified["root"], "gates": [],
                    "verdict": "identity mismatch"}
        with tempfile.TemporaryDirectory(prefix="reticuli-audit-") as room:
            parsed = _materialize(source, room)
            rows = _judge(source, room, parsed)
        ok = all(row["status"] == "reproduced" for row in rows)
        return {"ok": ok, "root": verified["root"], "gates": rows,
                "verdict": "earned" if ok else "carried or broken"}
    except (core.ClaimError, OSError) as exc:
        return {"ok": False, "gates": [], "verdict": str(exc)}


def rebuild(directory: os.PathLike[str] | str, producer: str,
            into: os.PathLike[str] | str, *, produce_from: Any = None,
            input_from: Any = None, guidance: bool = True,
            producer_env: dict[str, str] | None = None) -> dict[str, Any]:
    """Regrow generated files freely, then earn the original pinned gates."""
    source, target = os.path.realpath(directory), os.path.realpath(into)
    verified = seal.verify(source)
    if not verified["ok"]:
        raise core.ClaimError("source identity mismatch")
    if os.path.isdir(target) and os.listdir(target):
        raise core.ClaimError(f"rebuild target is not empty: {target}")
    parsed = _materialize(source, target, generated=False)
    produced = _produce(producer, target, parsed, guidance=guidance,
                        producer_env=producer_env)
    if produced["status"] != "ok":
        raise core.ClaimError(f"producer {produced['status']}: {produced.get('stderr', '')}")
    rows = _judge(source, target, parsed)
    if any(row["status"] != "reproduced" for row in rows):
        raise core.ClaimError(f"rebuild gates did not reproduce: {rows}")
    manifest = seal.seal(target)
    if manifest["root"] != verified["root"]:
        raise core.ClaimError("rebuild root differs from source")
    run.ledger(target, {"kind": "producer", "seconds": produced["seconds"],
                        "when": core._now(), "quarantine": produced["quarantine"]})
    return {"root": manifest["root"], "name": manifest["name"],
            "gates": rows, "quarantine": rows[0]["quarantine"] if rows else "none"}
