"""Cold auditing and independent rebuilding of a sealed claim."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
import tomllib

from . import core, identity, recipe, run, seal


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
        return "{ " + ", ".join(f"{_toml_key(k)} = {_toml_value(v)}"
                                for k, v in value.items()) + " }"
    raise core.ClaimError(f"cannot write TOML value: {value!r}")


def _toml_key(key: str) -> str:
    import re
    return key if re.fullmatch(r"[A-Za-z0-9_-]+", key) else json.dumps(key)


def _toml_recipe(document: dict[str, object]) -> str:
    """Write parsed recipe tables as TOML, retaining their actual values."""
    lines: list[str] = []
    for key, value in document.items():
        if isinstance(value, dict):
            lines.append(f"[{_toml_key(key)}]")
            lines.extend(f"{_toml_key(k)} = {_toml_value(v)}" for k, v in value.items())
            lines.append("")
        elif isinstance(value, list) and all(isinstance(item, dict) for item in value):
            for item in value:
                lines.append(f"[[{_toml_key(key)}]]")
                lines.extend(f"{_toml_key(k)} = {_toml_value(v)}" for k, v in item.items())
                lines.append("")
        else:
            lines.append(f"{_toml_key(key)} = {_toml_value(value)}")
    result = "\n".join(lines).rstrip() + "\n"
    if tomllib.loads(result) != document:
        raise core.ClaimError("materialized recipe changed its parsed contents")
    return result


def _materialize(source: str, destination: str, document: dict[str, object],
                 *, generated: bool = False) -> None:
    """Create a room containing only recipe, inputs and permitted outputs."""
    os.makedirs(destination, exist_ok=True)
    version = document["claim"].get("format", 1)
    if version >= 3:
        preimage = identity._preimage_recipe(document)
        with open(os.path.join(destination, core.RECIPE), "w", encoding="utf-8") as target:
            target.write(_toml_recipe(preimage))
    else:
        source_recipe = recipe.recipe_path(source)
        core._copy_into(source_recipe,
                        os.path.join(destination, os.path.basename(source_recipe)))
    for name in recipe._inputs(document, source):
        core._copy_into(core._safe(source, name), core._safe(destination, name))
    for step in recipe._steps(document):
        name = step["output"]
        step_class = step.get("class", "generated" if step["kind"] == "produce" else "pinned")
        if step["kind"] == "gate":
            continue
        if generated and step_class == "generated" and "from" not in step:
            continue
        path = core._safe(source, name)
        if os.path.isfile(path):
            core._copy_into(path, core._safe(destination, name))


def _compare_pin(original: str, room: str, name: str) -> bool:
    try:
        return core._hash_file(core._safe(original, name)) == core._hash_file(core._safe(room, name))
    except core.ClaimError:
        return False


def _step_guidance(step: dict[str, object]) -> str:
    return str(step.get("guidance", step.get("request", "")))


def _read_usage(room: str) -> dict[str, object]:
    try:
        with open(os.path.join(room, core.USAGE), encoding="utf-8") as source:
            usage = json.load(source)
        return usage if isinstance(usage, dict) else {}
    except (OSError, ValueError):
        return {}


def _ssh_verify(*args: object, **kwargs: object) -> bool:
    """No signature is needed to audit locally present sealed bytes."""
    return False


def _authorized(*args: object, **kwargs: object) -> bool:
    """Authorization is separate from locally re-earning a gate."""
    return False


def _judge(source: str, room: str, document: dict[str, object]) -> list[dict[str, object]]:
    gates: list[dict[str, object]] = []
    missing = run.preflight(document)
    try:
        venv_bin = run.furnish(room, document) if not missing else None
    except core.ClaimError as exc:
        missing.append(str(exc))
        venv_bin = None
    for step in recipe.gates(document):
        name = step["output"]
        if missing:
            gates.append({"output": name, "status": "environment", "quarantine": "none",
                          "detail": ", ".join(missing)})
            continue
        extra = {}
        if venv_bin:
            extra["PATH"] = venv_bin + os.pathsep + os.environ.get("PATH", os.defpath)
        outcome = run.run_gate(step["run"], room, document, extra)
        status = outcome["status"]
        if status == "ok":
            status = "ok" if _compare_pin(source, room, name) else "mismatch"
        gates.append({"output": name, "status": status,
                      "quarantine": outcome["quarantine"],
                      "stdout": outcome.get("stdout", ""),
                      "stderr": outcome.get("stderr", "")})
    return gates


def audit(claim_dir: os.PathLike[str] | str, *, shallow: bool = False) -> dict[str, object]:
    """Re-earn every gate on present generated bytes in a fresh room."""
    source = os.fspath(claim_dir)
    checked = seal.verify(source)
    if not checked["ok"]:
        return {"ok": False, "root": checked["root"], "gates": [],
                "verdict": "identity mismatch"}
    document = recipe.load_recipe(source)
    with tempfile.TemporaryDirectory(prefix="reticuli-audit-") as room:
        _materialize(source, room, document)
        gates = _judge(source, room, document)
    ok = all(g["status"] in ("ok", "reproduced") for g in gates)
    return {"ok": ok, "root": checked["root"], "gates": gates,
            "verdict": "earned" if ok else "carried or broken"}


def _produce(command: str, room: str, document: dict[str, object],
             step: dict[str, object], outputs: list[str], *, guidance: bool = True,
             producer_env: dict[str, str] | None = None) -> dict[str, object]:
    """Invoke the caller's producer without adding a sandbox."""
    extra = {core._ENV_CLAIM: os.path.abspath(room),
             core._ENV_OUTPUT: os.path.abspath(core._safe(room, step["output"])),
             core._ENV_OUTPUTS: json.dumps(outputs),
             core._ENV_USAGE: os.path.abspath(os.path.join(room, core.USAGE))}
    if guidance:
        extra[core._ENV_REQUEST] = _step_guidance(step)
    if producer_env:
        extra.update(producer_env)
    env = run._scrub_env(extra=extra)
    # The producer keeps the caller's HOME and network reachability.
    if "HOME" in os.environ:
        env["HOME"] = os.environ["HOME"]
    return run._run([core._SHELL, "-c", command], room, core.PRODUCER_TIMEOUT, env)


def rebuild(claim_dir: os.PathLike[str] | str, producer: str,
            into: os.PathLike[str] | str, *, produce_from: object = None,
            input_from: object = None, guidance: bool = True,
            producer_env: dict[str, str] | None = None) -> dict[str, object]:
    """Regrow generated outputs from pinned inputs and re-earn the root."""
    source, room = os.fspath(claim_dir), os.fspath(into)
    checked = seal.verify(source)
    if not checked["ok"]:
        raise core.ClaimError("source claim identity mismatch")
    if os.path.exists(room) and os.listdir(room):
        raise core.ClaimError(f"rebuild target is not empty: {room}")
    document = recipe.load_recipe(source)
    _materialize(source, room, document, generated=True)
    outputs = recipe.generated_outputs(document)
    produces = [s for s in recipe.produces(document)
                if s.get("class", "generated") == "generated" and "from" not in s]
    production = []
    for step in produces:
        result = _produce(producer, room, document, step, outputs,
                          guidance=guidance, producer_env=producer_env)
        production.append(result)
        if result["status"] != "ok":
            return {"ok": False, "root": None, "gates": [],
                    "quarantine": "inherited" if os.environ.get(core._JAILED) else "none",
                    "verdict": result}
    gates = _judge(source, room, document)
    ok = all(g["status"] in ("ok", "reproduced") for g in gates)
    if not ok:
        return {"ok": False, "root": None, "gates": gates,
                "quarantine": "inherited" if os.environ.get(core._JAILED) else "none",
                "verdict": "gates failed"}
    manifest = seal.seal(room)
    if manifest["root"] != checked["root"]:
        return {"ok": False, "root": manifest["root"], "gates": gates,
                "quarantine": "inherited" if os.environ.get(core._JAILED) else "none",
                "verdict": "root mismatch"}
    usage = _read_usage(room)
    for result in production:
        event = {"kind": "producer", "seconds": result["seconds"]}
        event.update({key: usage[key] for key in ("usd", "tokens", "calls")
                      if isinstance(usage.get(key), (int, float)) and not isinstance(usage[key], bool)})
        run.ledger(room, event)
    return {"ok": True, "root": manifest["root"], "gates": gates,
            "build_digest": identity.build_digest(room),
            "quarantine": "inherited" if os.environ.get(core._JAILED) else "none"}
