"""Build and audit a claim in a disposable judging directory.

Pinned bytes are checked against the sealed root before any command runs.  A
gate earns its verdict only when its freshly written output has the bytes
recorded by the claim.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import core, identity, recipe, run, seal


def _step_guidance(step: dict) -> str:
    """Return either spelling of a producer's optional instruction."""
    return step.get("guidance", step.get("request", ""))


def _compare_pin(original: os.PathLike[str] | str,
                 candidate: os.PathLike[str] | str) -> bool:
    """Compare two regular, singly linked files by content."""
    try:
        return core._hash_file(original) == core._hash_file(candidate)
    except core.ClaimError:
        return False


def _copy_declared(source: str, target: str, name: str) -> None:
    source_path = core._safe(source, name)
    core._hash_file(source_path)
    destination = core._safe(target, name)
    core._copy_into(source_path, destination)


def _materialize(directory: os.PathLike[str] | str,
                 into: os.PathLike[str] | str,
                 parsed: dict | None = None, *, generated: bool = True) -> str:
    """Copy declared criterion files into a fresh judging room.

    The room excludes carried gate outputs.  Present generated files are
    included for an audit, while a blind rebuild may omit them.
    """
    source, target = os.fspath(directory), os.fspath(into)
    parsed = parsed if parsed is not None else recipe.load_recipe(source)
    os.makedirs(target, exist_ok=True)
    recipe_name = os.path.basename(recipe.recipe_path(source))
    _copy_declared(source, target, recipe_name)
    for name in recipe._inputs(parsed, source):
        _copy_declared(source, target, name)
    for step in recipe._steps(parsed):
        name = step["output"]
        step_class = step.get("class", "generated" if step["kind"] == "produce" else "pinned")
        if step["kind"] == "produce" and (generated or step_class not in ("generated", "free")):
            path = core._safe(source, name)
            if os.path.lexists(path):
                _copy_declared(source, target, name)
    if parsed["claim"].get("format", 1) >= 3:
        # Guidance is outside a format-3 root, so it must also be absent from
        # the bytes that a gate can read in the judging room.
        path = core._safe(target, recipe_name)
        with open(path, encoding="utf-8") as stream:
            lines = stream.readlines()
        with open(path, "w", encoding="utf-8") as stream:
            for line in lines:
                if line.lstrip().startswith(("guidance =", "request =")):
                    continue
                stream.write(line)
    return target


def _read_usage(directory: os.PathLike[str] | str) -> dict:
    """Read optional producer cost reports, accepting only metered units."""
    path = os.path.join(directory, core.USAGE)
    try:
        with open(path, encoding="utf-8") as stream:
            value = json.load(stream)
    except (OSError, ValueError):
        return {}
    if not isinstance(value, dict):
        return {}
    return {key: number for key in ("usd", "tokens", "calls")
            if isinstance((number := value.get(key)), (int, float))
            and not isinstance(number, bool) and number >= 0}


def _produce(command: str, directory: os.PathLike[str] | str,
             output: str, request: str = "") -> dict:
    """Run a local producer command with the output and guidance identified."""
    env = run._scrub_env(os.fspath(directory), {
        core._ENV_OUTPUT: output, core._ENV_REQUEST: request,
        core._ENV_CLAIM: os.fspath(directory),
    })
    return run._run([core._SHELL, "-c", command], os.fspath(directory),
                    env, core.PRODUCER_TIMEOUT)


def _ssh_verify(message: bytes, signature: os.PathLike[str] | str,
                allowed_signers: os.PathLike[str] | str,
                principal: str, namespace: str = core.SIGN_NAMESPACE) -> bool:
    """Check a detached SSH signature against a caller supplied trust file."""
    try:
        result = subprocess.run(
            ["ssh-keygen", "-Y", "verify", "-f", os.fspath(allowed_signers),
             "-I", principal, "-n", namespace, "-s", os.fspath(signature)],
            input=message, capture_output=True, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _authorized(message: bytes, signature: os.PathLike[str] | str,
                allowed_signers: os.PathLike[str] | str,
                principal: str) -> bool:
    """Return whether a trusted signer authorized the supplied bytes."""
    return _ssh_verify(message, signature, allowed_signers, principal)


def audit(directory: os.PathLike[str] | str, *, shallow: bool = False) -> dict:
    """Re-run every gate on present generated bytes in a disposable room."""
    source = os.fspath(directory)
    result: dict = {"ok": False, "verdict": "carried or broken", "gates": []}
    try:
        checked = seal.verify(source)
        result["root"] = checked["root"]
        if not checked["ok"]:
            result["detail"] = "sealed identity does not match pinned bytes"
            return result
        parsed = recipe.load_recipe(source)
        with tempfile.TemporaryDirectory(prefix="reticuli-audit-") as room:
            _materialize(source, room, parsed)
            path_bin = run.furnish(room, parsed)
            env = {"PATH": path_bin + os.pathsep + os.environ.get("PATH", os.defpath)} if path_bin else None
            for step in recipe.gates(parsed):
                name = step["output"]
                outcome = run.run_gate(step["run"], room, parsed, env=env)
                gate = {"output": name, "status": outcome["status"],
                        "sandbox": outcome.get("quarantine", "none")}
                if outcome["status"] == "ok":
                    expected = core._safe(source, name)
                    actual = core._safe(room, name)
                    step_class = step.get("class", "pinned")
                    if step_class not in ("generated", "free") and not _compare_pin(expected, actual):
                        gate["status"] = "mismatch"
                result["gates"].append(gate)
                if gate["status"] != "ok":
                    result["detail"] = outcome.get("detail") or outcome.get("stderr", "")
                    return result
        result["ok"] = True
        result["verdict"] = "earned"
        return result
    except (core.ClaimError, OSError, ValueError) as exc:
        result["detail"] = str(exc)
        return result
