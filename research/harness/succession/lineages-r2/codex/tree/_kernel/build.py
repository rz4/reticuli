"""Materialize claims and re-earn their gate verdicts.

An audit never uses a verdict left in the original directory as evidence of
execution.  It runs the gates in a temporary claim room and compares the
newly written files with the sealed ones.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import core, recipe as recipe_module, run, seal


def _step_guidance(step: dict, *, without_guidance: bool = False) -> str:
    """Return the producer hint, accepting both recipe spellings."""
    if without_guidance:
        return ""
    return step.get("guidance", step.get("request", ""))


def _compare_pin(original: os.PathLike[str] | str,
                 room: os.PathLike[str] | str, name: str) -> bool:
    """Compare two declared, regular files by their content digests."""
    try:
        return (core._hash_file(core._safe(original, name)) ==
                core._hash_file(core._safe(room, name)))
    except core.ClaimError:
        return False


def _materialize(directory: os.PathLike[str] | str,
                 into: os.PathLike[str] | str, *, generated: bool = True) -> str:
    """Copy a claim's criteria and, optionally, its present generated files.

    Gate outputs are deliberately omitted; every gate must create its own
    verdict in the room.  Format-3 rooms see the guidance-free recipe whose
    parsed content is in their root preimage.
    """
    source = os.path.realpath(directory)
    target = os.path.realpath(into)
    parsed = recipe_module.load_recipe(source)
    recipe_name = os.path.basename(recipe_module.recipe_path(source))
    os.makedirs(target, exist_ok=True)
    if parsed["claim"].get("format", 1) >= 3:
        from . import identity
        content = identity._preimage_recipe(parsed)
        # TOML serialization is not in the standard library.  Keep the
        # guidance-free parsed recipe available to gates as JSON residue;
        # format-3 audit also masks the raw recipe's hint below.
        raw = Path(source, recipe_name).read_text(encoding="utf-8")
        lines = raw.splitlines(keepends=True)
        filtered = [line for line in lines if not line.lstrip().startswith(("guidance =", "request ="))]
        Path(target, recipe_name).write_text("".join(filtered), encoding="utf-8")
    else:
        core._copy_into(os.path.join(source, recipe_name), os.path.join(target, recipe_name))

    names = set(recipe_module._inputs(parsed, source))
    for step in recipe_module._steps(parsed):
        kind = step["kind"]
        step_class = step.get("class", "generated" if kind == "produce" else "pinned")
        if kind == "produce" and (step_class not in ("generated", "free") or generated):
            names.add(step["output"])
    for name in sorted(names):
        path = core._safe(source, name)
        if os.path.exists(path):
            core._copy_into(path, core._safe(target, name))
        elif name in recipe_module._inputs(parsed, source):
            raise core.ClaimError(f"missing pinned input: {name}")
    return target


def _read_usage(directory: os.PathLike[str] | str) -> dict:
    """Read a producer's optional usage report, refusing malformed data."""
    path = core._safe(directory, core.USAGE)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as stream:
            value = json.load(stream)
    except (OSError, ValueError) as exc:
        raise core.ClaimError(f"cannot read usage report: {exc}") from exc
    if not isinstance(value, dict):
        raise core.ClaimError("usage report must be an object")
    return {key: value[key] for key in ("usd", "tokens", "calls")
            if key in value and isinstance(value[key], (int, float))
            and not isinstance(value[key], bool) and value[key] >= 0}


def _produce(producer: str, directory: os.PathLike[str] | str,
             step: dict, *, without_guidance: bool = False) -> dict:
    """Invoke a producer once for a generated output."""
    env = run._scrub_env(os.fspath(directory), {
        core._ENV_OUTPUT: step["output"],
        core._ENV_REQUEST: _step_guidance(step, without_guidance=without_guidance),
    })
    try:
        done = subprocess.run(producer, shell=True, cwd=directory, env=env,
                              capture_output=True, text=True,
                              timeout=core.PRODUCER_TIMEOUT, check=False)
        return {"status": "ok" if done.returncode == 0 else "failed",
                "returncode": done.returncode, "stdout": done.stdout,
                "stderr": done.stderr}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "environment", "detail": str(exc)}


def _ssh_verify(statement: bytes, signature: os.PathLike[str] | str,
                allowed_signers: os.PathLike[str] | str, identity: str,
                namespace: str = core.SIGN_NAMESPACE) -> bool:
    """Check a detached SSH signature against a local trust anchor."""
    try:
        done = subprocess.run(
            ["ssh-keygen", "-Y", "verify", "-f", os.fspath(allowed_signers),
             "-I", identity, "-n", namespace, "-s", os.fspath(signature)],
            input=statement, capture_output=True, timeout=30, check=False)
        return done.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _authorized(directory: os.PathLike[str] | str,
                allowed_signers: os.PathLike[str] | str | None = None) -> bool:
    """Report whether a claim has a locally trusted signature."""
    if not allowed_signers:
        return False
    try:
        manifest = seal.read_manifest(directory)
        sign_dir = core._safe(directory, core.SIGN_DIR)
        for name in os.listdir(sign_dir):
            if name.endswith(".sig") and _ssh_verify(
                    manifest["root"].encode(), os.path.join(sign_dir, name),
                    allowed_signers, name[:-4]):
                return True
    except (OSError, core.ClaimError):
        pass
    return False


def audit(directory: os.PathLike[str] | str, *, shallow: bool = False) -> dict:
    """Verify identity, then cold-run every gate and compare sealed verdicts."""
    source = os.path.realpath(directory)
    report = {"ok": False, "verdict": "carried or broken", "gates": []}
    try:
        checked = seal.verify(source)
        report["root"] = checked["root"]
        if not checked["ok"]:
            report["detail"] = "claim identity does not match its seal"
            return report
        parsed = recipe_module.load_recipe(source)
        missing = run.preflight(parsed)
        if missing:
            report["detail"] = "missing requirements: " + ", ".join(missing)
            report["gates"] = [{"output": step["output"], "status": "environment"}
                               for step in recipe_module.gates(parsed)]
            return report
        with tempfile.TemporaryDirectory(prefix="reticuli-audit-") as room:
            _materialize(source, room)
            try:
                furnished = run.furnish(source, parsed)
            except core.ClaimError as exc:
                report["detail"] = str(exc)
                report["gates"] = [{"output": step["output"], "status": "environment"}
                                   for step in recipe_module.gates(parsed)]
                return report
            env = None
            if furnished:
                env = {"PATH": furnished + os.pathsep + os.environ.get("PATH", os.defpath)}
            for step in recipe_module.gates(parsed):
                name = step["output"]
                result = run.run_gate(step["run"], room, parsed, env=env)
                status = result["status"]
                if status == "ok":
                    status = "reproduced" if _compare_pin(source, room, name) else "mismatch"
                report["gates"].append({"output": name, "status": status,
                                        "sandbox": result["quarantine"],
                                        "seconds": result["seconds"],
                                        "stderr": result["stderr"]})
        report["ok"] = all(gate["status"] == "reproduced" for gate in report["gates"])
        report["verdict"] = "earned" if report["ok"] else "carried or broken"
        return report
    except core.ClaimError as exc:
        report["detail"] = str(exc)
        return report
