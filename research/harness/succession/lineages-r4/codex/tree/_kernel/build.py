"""Materialize claim rooms, re-earn gates, and rebuild generated files."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import core, identity, recipe, run, seal


def _compare_pin(left: os.PathLike[str] | str, right: os.PathLike[str] | str) -> bool:
    """Compare two declared regular files by their content digests."""
    try:
        return core._hash_file(left) == core._hash_file(right)
    except core.ClaimError:
        return False


def _step_guidance(step: dict) -> str:
    return step.get("guidance", step.get("request", ""))


def _read_usage(directory: os.PathLike[str] | str) -> dict:
    """Read a producer's optional metering report, ignoring invalid units."""
    path = os.path.join(directory, core.USAGE)
    try:
        with open(path, encoding="utf-8") as stream:
            report = json.load(stream)
    except (OSError, ValueError):
        return {}
    if not isinstance(report, dict):
        return {}
    return {key: value for key, value in report.items()
            if key in ("usd", "tokens", "calls") and type(value) in (int, float)
            and value >= 0}


def _ssh_verify(message: bytes, signature: os.PathLike[str] | str,
                signers: os.PathLike[str] | str, principal: str,
                namespace: str = core.SIGN_NAMESPACE) -> bool:
    """Verify a detached SSH signature against an allowed-signers file."""
    try:
        with open(signature, "rb") as stream:
            result = subprocess.run(
                ["ssh-keygen", "-Y", "verify", "-f", os.fspath(signers),
                 "-I", principal, "-n", namespace, "-s", "/dev/stdin"],
                input=message, capture_output=True, check=False)
        return result.returncode == 0
    except OSError:
        return False


def _authorized(directory: os.PathLike[str] | str, root: str | None = None,
                signers: os.PathLike[str] | str | None = None) -> bool:
    """Whether a local trusted signature authorizes this sealed root."""
    if not signers:
        return False
    try:
        manifest = seal.read_manifest(directory)
        if root is not None and root != manifest["root"]:
            return False
        folder = Path(directory) / core.SIGN_DIR
        for packet in folder.glob("*.sign.json"):
            data = json.loads(packet.read_text(encoding="utf-8"))
            if data.get("root") != manifest["root"]:
                continue
            signature = data.get("signature")
            principal = data.get("principal")
            if isinstance(signature, str) and isinstance(principal, str):
                if _ssh_verify(manifest["root"].encode(), folder / signature,
                               signers, principal):
                    return True
    except (OSError, ValueError, core.ClaimError):
        pass
    return False


def _materialize(source: os.PathLike[str] | str, destination: os.PathLike[str] | str,
                 parsed: dict | None = None, *, generated: bool = False) -> dict:
    """Copy only declared claim bytes into a fresh judging or producing room."""
    parsed = parsed or recipe.load_recipe(source)
    os.makedirs(destination, exist_ok=True)
    recipe_name = os.path.basename(recipe.recipe_path(source))
    core._copy_into(core._safe(source, recipe_name), core._safe(destination, recipe_name))
    for name in recipe._inputs(parsed, source):
        core._copy_into(core._safe(source, name), core._safe(destination, name))
    for step in recipe._steps(parsed):
        name = step["output"]
        step_class = step.get("class", "generated" if step["kind"] == "produce" else "pinned")
        if step["kind"] == "produce" and (generated or step_class != "generated"):
            src = core._safe(source, name)
            if os.path.isfile(src):
                core._copy_into(src, core._safe(destination, name))
    return parsed


def _produce(command: str, directory: os.PathLike[str] | str, parsed: dict,
             *, guidance: bool = True, producer_env: dict[str, str] | None = None) -> dict:
    """Run the producer in the claim room and record its actual backend."""
    directory = os.path.abspath(os.fspath(directory))
    backend = run.sandbox_backend()
    store = os.path.join(directory, core.STORE)
    os.makedirs(store, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="producer-", dir=store) as scratch:
        extra = dict(producer_env or {})
        extra[core._ENV_CLAIM] = directory
        outputs = recipe.generated_outputs(parsed)
        extra[core._ENV_OUTPUTS] = json.dumps(outputs)
        if outputs:
            extra[core._ENV_OUTPUT] = outputs[0]
        if guidance:
            hints = [_step_guidance(step) for step in recipe.produces(parsed)]
            extra[core._ENV_REQUEST] = "\n".join(x for x in hints if x)
        env = run._scrub_env(directory, scratch, backend, extra)
        result = run._run(run._sandbox_argv(command, directory, backend, scratch),
                          directory, env, core.PRODUCER_TIMEOUT)
    result["quarantine"] = backend
    return result


def _earn_gates(room: str, original: str, parsed: dict) -> list[dict]:
    rows = []
    for step in recipe.gates(parsed):
        output = step["output"]
        path = core._safe(room, output)
        if os.path.isfile(path):
            os.unlink(path)
        try:
            furnished = run.furnish(room, parsed)
            extra = None
            if furnished:
                extra = {"PATH": furnished + os.pathsep + os.environ.get("PATH", os.defpath)}
            result = run.run_gate(step["run"], room, parsed, extra_env=extra)
        except core.ClaimError as exc:
            result = {"status": "environment", "error": str(exc),
                      "quarantine": run.sandbox_backend()}
        status = result["status"]
        if status == "ok":
            status = "ok" if _compare_pin(path, core._safe(original, output)) else "mismatch"
        rows.append({"output": output, "status": status,
                     "quarantine": result.get("quarantine", "none"),
                     **({"error": result["error"]} if "error" in result else {})})
    return rows


def audit(directory: os.PathLike[str] | str, *, shallow: bool = False) -> dict:
    """Check identity, then earn every gate again against present generated bytes."""
    directory = os.path.abspath(os.fspath(directory))
    try:
        verified = seal.verify(directory)
        if not verified["ok"]:
            return {"ok": False, "verdict": "mismatch", "gates": [],
                    "root": verified["root"]}
        parsed = recipe.load_recipe(directory)
        with tempfile.TemporaryDirectory(prefix="reticuli-audit-") as room:
            _materialize(directory, room, parsed, generated=True)
            gates = _earn_gates(room, directory, parsed)
        ok = all(row["status"] == "ok" for row in gates)
        return {"ok": ok, "verdict": "earned" if ok else "carried or broken",
                "root": verified["root"], "gates": gates}
    except core.ClaimError as exc:
        return {"ok": False, "verdict": str(exc), "gates": []}


def rebuild(directory: os.PathLike[str] | str, producer: str,
            into: os.PathLike[str] | str, *, produce_from: str | None = None,
            input_from: str | None = None, guidance: bool = True,
            producer_env: dict[str, str] | None = None) -> dict:
    """Regrow generated outputs from declared inputs and re-earn the gates."""
    source = os.path.abspath(os.fspath(directory))
    target = os.path.abspath(os.fspath(into))
    verified = seal.verify(source)
    if not verified["ok"]:
        raise core.ClaimError("source identity mismatch")
    if os.path.exists(target) and os.listdir(target):
        raise core.ClaimError(f"rebuild target is not empty: {target}")
    parsed = recipe.load_recipe(source)
    _materialize(source, target, parsed)
    produced = _produce(producer, target, parsed, guidance=guidance,
                        producer_env=producer_env)
    if produced["status"] != "ok":
        raise core.ClaimError(f"producer {produced['status']}: {produced.get('stderr', '')}")
    gates = _earn_gates(target, source, parsed)
    if any(row["status"] != "ok" for row in gates):
        raise core.ClaimError(f"rebuild gates did not reproduce: {gates}")
    manifest = seal.seal(target)
    if manifest["root"] != verified["root"]:
        raise core.ClaimError("rebuild root mismatch")
    usage = _read_usage(target)
    run.ledger(target, {"when": core._now(), "seconds": produced.get("seconds", 0),
                        "quarantine": produced["quarantine"], **usage})
    return {"root": manifest["root"], "build_digest": identity.build_digest(target),
            "gates": gates, "quarantine": produced["quarantine"]}
