"""Materializing, rebuilding, and deeply auditing claims.

A build is performed in a fresh directory.  Identity-bearing inputs are copied
there, generated files are either copied for an audit or supplied by a
producer, and gate verdicts are always earned again.  In particular, the
verdict files in the sealed claim are comparison targets; they are never
trusted merely because they are present.
"""

from __future__ import annotations

from collections.abc import Mapping
import json
import math
import os
import re
import shutil
import stat
import subprocess
import tempfile
import time
from typing import Any

from . import core, identity, recipe as recipe_module, run, seal


_BARE_TOML_KEY = re.compile(r"^[A-Za-z0-9_-]+$")


def _toml_key(value: str) -> str:
    """Spell one TOML key without changing its value."""

    return value if _BARE_TOML_KEY.fullmatch(value) else json.dumps(value)


def _toml_value(value: Any) -> str:
    """Return a TOML spelling for values admitted by recipe validation."""

    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=True)
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float) and math.isfinite(value):
        return repr(value)
    if isinstance(value, list):
        if any(isinstance(item, dict) for item in value):
            raise core.ClaimError("cannot put a table array in an inline TOML value")
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    if isinstance(value, dict):
        members = (
            f"{_toml_key(str(key))} = {_toml_value(child)}"
            for key, child in value.items()
        )
        return "{ " + ", ".join(members) + " }"
    raise core.ClaimError(f"recipe contains a value which cannot be written as TOML: {value!r}")


def _toml_recipe(document: Mapping[str, Any]) -> str:
    """Serialize a parsed recipe as ordinary, semantically equivalent TOML.

    This is needed for format 3 and later: their judging room receives the
    guidance-free root preimage, but it must still receive a recipe rather
    than an implementation-specific JSON representation of that preimage.
    """

    lines: list[str] = []

    # TOML scalar keys at the document root have to precede table headers.
    for key, value in document.items():
        if not isinstance(value, (dict, list)) or (
            isinstance(value, list) and not any(isinstance(x, dict) for x in value)
        ):
            lines.append(f"{_toml_key(str(key))} = {_toml_value(value)}")
    if lines:
        lines.append("")

    for key, value in document.items():
        name = _toml_key(str(key))
        if isinstance(value, dict):
            lines.append(f"[{name}]")
            for child_key, child in value.items():
                lines.append(f"{_toml_key(str(child_key))} = {_toml_value(child)}")
            lines.append("")
        elif isinstance(value, list) and any(isinstance(x, dict) for x in value):
            if not all(isinstance(x, dict) for x in value):
                raise core.ClaimError(f"mixed table array cannot be written as TOML: {key!r}")
            for table in value:
                lines.append(f"[[{name}]]")
                for child_key, child in table.items():
                    lines.append(f"{_toml_key(str(child_key))} = {_toml_value(child)}")
                lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _copy_declared(source: str, target: str, name: str, *, required: bool = True) -> bool:
    """Copy a safely declared regular file and return whether it existed."""

    src = core._safe(source, name)
    if not os.path.lexists(src):
        if required:
            raise core.ClaimError(f"declared file is absent: {name}")
        return False
    try:
        info = os.lstat(src)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise core.ClaimError(f"declared file is not an unaliased regular file: {name}")
        dst = core._safe(target, name)
        core._copy_into(src, dst)
        return True
    except core.ClaimError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise core.ClaimError(f"cannot materialize {name!r}: {exc}") from None


def _materialize(
    source: str | os.PathLike[str],
    into: str | os.PathLike[str],
    *,
    generated: bool = False,
    input_from: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Create a cold judging room from a claim.

    ``generated`` copies the present realization, as an audit requires.  Gate
    outputs are deliberately omitted in all cases.  Component-supplied
    produce outputs are copied even for a rebuild because this claim's
    producer does not own them.
    """

    src = os.path.abspath(os.fspath(source))
    dst = os.path.abspath(os.fspath(into))
    parsed = recipe_module.load_recipe(src)
    try:
        if os.path.exists(dst):
            if not os.path.isdir(dst):
                raise core.ClaimError(f"build target is not a directory: {dst}")
            if os.listdir(dst):
                raise core.ClaimError(f"build target is not empty: {dst}")
        else:
            os.makedirs(dst)

        version = parsed["claim"].get("format", 1)
        if version >= 3:
            preimage = identity._preimage_recipe(parsed)
            recipe_target = core._safe(dst, core.RECIPE)
            with open(recipe_target, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(_toml_recipe(preimage))
        else:
            recipe_source = recipe_module.recipe_path(src)
            recipe_name = os.path.basename(recipe_source)
            core._copy_into(recipe_source, core._safe(dst, recipe_name))

        input_source = os.path.abspath(os.fspath(input_from)) if input_from is not None else src
        for name in recipe_module._inputs(parsed, src):
            _copy_declared(input_source, dst, name)

        if generated:
            for step in recipe_module.produces(parsed):
                _copy_declared(src, dst, step["output"], required=False)
        else:
            # A `from` output belongs to another claim's realization and is
            # not an output this producer can be asked to recreate.
            for step in recipe_module.produces(parsed):
                if "from" in step:
                    _copy_declared(src, dst, step["output"])
        return parsed
    except core.ClaimError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise core.ClaimError(f"cannot materialize claim: {exc}") from None


def _compare_pin(expected: str | os.PathLike[str], actual: str | os.PathLike[str]) -> bool:
    """Whether two paths are byte-identical unaliased regular files."""

    try:
        left = os.lstat(expected)
        right = os.lstat(actual)
        if not stat.S_ISREG(left.st_mode) or not stat.S_ISREG(right.st_mode):
            return False
        if left.st_nlink != 1 or right.st_nlink != 1 or left.st_size != right.st_size:
            return False
        return core._hash_file(expected) == core._hash_file(actual)
    except (OSError, TypeError, ValueError):
        return False


def _step_guidance(step: Mapping[str, Any], enabled: bool = True) -> str | None:
    """Return a producer hint, accepting both historical spellings."""

    if not enabled:
        return None
    for key in core.GUIDANCE_KEYS:
        value = step.get(key)
        if isinstance(value, str):
            return value
    return None


def _read_usage(path: str | os.PathLike[str]) -> dict[str, int | float]:
    """Read and validate a producer's optional usage report.

    The producer may report oracle units.  Wall clock is measured by the
    kernel and therefore is never accepted from this payload.
    """

    candidate = os.fspath(path)
    if os.path.isdir(candidate):
        candidate = core._safe(candidate, core.USAGE)
    try:
        if not os.path.isfile(candidate):
            return {}
        with open(candidate, "r", encoding="utf-8") as stream:
            value = json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise core.ClaimError(f"cannot read producer usage: {exc}") from None
    if not isinstance(value, dict):
        raise core.ClaimError("producer usage must be a JSON object")
    result: dict[str, int | float] = {}
    for key in ("usd", "tokens", "calls"):
        if key not in value:
            continue
        item = value[key]
        if (
            isinstance(item, bool)
            or not isinstance(item, (int, float))
            or not math.isfinite(float(item))
            or item < 0
        ):
            raise core.ClaimError(f"producer usage {key!r} must be a finite non-negative number")
        result[key] = item
    return result


def _produce(
    command: str,
    room: str | os.PathLike[str],
    step: Mapping[str, Any],
    outputs: list[str],
    *,
    guidance: bool = True,
    producer_env: Mapping[str, Any] | None = None,
    claim_root: str | None = None,
) -> dict[str, Any]:
    """Invoke an unconstrained producer for one named output.

    Producers inherit the caller's reachability and HOME.  Their products are
    judged by the separately sandboxed gates; imposing the gate jail here
    would prevent network-backed and credential-backed producer tools from
    doing their job.
    """

    if not isinstance(command, str) or not command:
        raise core.ClaimError("producer must be a non-empty shell command")
    directory = os.path.abspath(os.fspath(room))
    output = step.get("output")
    if not isinstance(output, str):
        raise core.ClaimError("produce step has no output")
    target = core._safe(directory, output)
    parent = os.path.dirname(target)
    if parent:
        os.makedirs(parent, exist_ok=True)

    usage_path = core._safe(directory, core.USAGE)
    try:
        if os.path.lexists(usage_path):
            os.unlink(usage_path)
    except OSError as exc:
        raise core.ClaimError(f"cannot clear producer usage report: {exc}") from None

    env = os.environ.copy()
    # Do not accidentally relay protocol values belonging to an outer build.
    for name in (
        core._ENV_CLAIM, core._ENV_OUTPUT, core._ENV_OUTPUTS,
        core._ENV_REQUEST, core._ENV_USAGE,
    ):
        env.pop(name, None)
    env[core._ENV_OUTPUT] = target
    env[core._ENV_OUTPUTS] = json.dumps(outputs, sort_keys=True)
    env[core._ENV_USAGE] = usage_path
    if claim_root:
        env[core._ENV_CLAIM] = claim_root
    hint = _step_guidance(step, guidance)
    if hint is not None:
        env[core._ENV_REQUEST] = hint
    if producer_env:
        for key, value in producer_env.items():
            if isinstance(key, str) and value is not None:
                env[key] = str(value)

    started = time.monotonic()
    shell = core._SHELL if os.path.isabs(core._SHELL) and os.path.exists(core._SHELL) else "/bin/sh"
    try:
        done = subprocess.run(
            [shell, "-c", command], cwd=directory, env=env,
            capture_output=True, text=True, check=False,
            timeout=float(core.PRODUCER_TIMEOUT),
        )
        status = "ok" if done.returncode == 0 else "failed"
        result: dict[str, Any] = {
            "status": status,
            "returncode": done.returncode,
            "stdout": done.stdout,
            "stderr": done.stderr,
            "seconds": time.monotonic() - started,
            "output": output,
        }
    except subprocess.TimeoutExpired as exc:
        result = {
            "status": "timeout", "returncode": None,
            "stdout": exc.stdout or "", "stderr": exc.stderr or "",
            "seconds": time.monotonic() - started, "output": output,
        }
    except (OSError, ValueError) as exc:
        result = {
            "status": "failed", "returncode": None, "stdout": "",
            "stderr": str(exc), "seconds": time.monotonic() - started,
            "output": output,
        }
    try:
        result["usage"] = _read_usage(usage_path)
    except core.ClaimError as exc:
        result["status"] = "failed"
        result["stderr"] = (result.get("stderr") or "") + "\n" + str(exc)
        result["usage"] = {}
    return result


def _gate_rows(
    source: str,
    room: str,
    parsed: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Run all gates cold in recipe order and compare their pinned bytes."""

    rows: list[dict[str, Any]] = []
    for step in recipe_module.gates(dict(parsed)):
        name = step["output"]
        actual = core._safe(room, name)
        try:
            if os.path.lexists(actual):
                if os.path.isdir(actual) and not os.path.islink(actual):
                    shutil.rmtree(actual)
                else:
                    os.unlink(actual)
            parent = os.path.dirname(actual)
            if parent:
                os.makedirs(parent, exist_ok=True)
        except OSError as exc:
            rows.append({
                "output": name, "status": "failed", "quarantine": "none",
                "stderr": f"cannot clear gate verdict: {exc}",
            })
            continue

        execution = run.run_gate(step["run"], room, parsed)
        status = execution.get("status", "failed")
        if status == "ok":
            expected = core._safe(source, name)
            status = "reproduced" if _compare_pin(expected, actual) else "mismatch"
        row = {
            "output": name,
            "status": status,
            "quarantine": execution.get("quarantine", "none"),
        }
        for key in ("returncode", "stdout", "stderr", "seconds", "missing"):
            if key in execution:
                row[key] = execution[key]
        rows.append(row)
    return rows


def _ssh_verify(
    data: bytes | str,
    signature: str | os.PathLike[str],
    allowed_signers: str | os.PathLike[str],
    *,
    namespace: str = core.SIGN_NAMESPACE,
    identity_name: str = "*",
) -> bool:
    """Verify an ssh-keygen detached signature, returning a simple boolean."""

    executable = shutil.which("ssh-keygen")
    if executable is None:
        return False
    payload = data.encode("utf-8") if isinstance(data, str) else data
    try:
        done = subprocess.run(
            [executable, "-Y", "verify", "-f", os.fspath(allowed_signers),
             "-I", identity_name, "-n", namespace, "-s", os.fspath(signature)],
            input=payload, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            check=False,
        )
        return done.returncode == 0
    except (OSError, TypeError, ValueError):
        return False


def _authorized(
    d: str | os.PathLike[str],
    digest: str,
    allowed_signers: str | os.PathLike[str] | None = None,
) -> bool:
    """Whether any detached signature in the private sign directory authorizes a digest."""

    anchor = os.fspath(allowed_signers) if allowed_signers is not None else os.environ.get(core._ENV_SIGNERS)
    if not anchor:
        return False
    try:
        directory = core._safe(d, core.SIGN_DIR)
        if not os.path.isdir(directory):
            return False
        for name in sorted(os.listdir(directory)):
            if name.endswith((".sign", ".sig")) and _ssh_verify(
                digest + "\n", os.path.join(directory, name), anchor
            ):
                return True
    except (OSError, core.ClaimError):
        return False
    return False


def audit(d: str | os.PathLike[str], **_options: Any) -> dict[str, Any]:
    """Re-earn every gate against the concrete generated bytes presently held."""

    source = os.path.abspath(os.fspath(d))
    try:
        verification = seal.verify(source)
    except core.ClaimError as exc:
        return {"ok": False, "verdict": "refused", "detail": str(exc), "gates": []}
    if not verification.get("ok"):
        return {
            "ok": False, "verdict": "identity mismatch", "gates": [],
            "root": verification.get("root"),
            "recomputed": verification.get("recomputed"),
        }

    parent = tempfile.mkdtemp(prefix="reticuli-audit-")
    room = os.path.join(parent, "room")
    try:
        parsed = _materialize(source, room, generated=True)
        rows = _gate_rows(source, room, parsed)
        ok = all(row.get("status") in {"ok", "reproduced"} for row in rows)
        return {
            "ok": ok,
            "verdict": "earned" if ok else "broken",
            "root": verification.get("root"),
            "gates": rows,
        }
    except core.ClaimError as exc:
        return {
            "ok": False, "verdict": "refused", "detail": str(exc),
            "root": verification.get("root"), "gates": [],
        }
    finally:
        shutil.rmtree(parent, ignore_errors=True)


def rebuild(
    d: str | os.PathLike[str],
    producer: str,
    into: str | os.PathLike[str],
    *,
    produce_from: str | os.PathLike[str] | None = None,
    input_from: str | os.PathLike[str] | None = None,
    guidance: bool = True,
    producer_env: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Regrow generated outputs in *into*, re-run gates, and seal the result."""

    source = os.path.abspath(os.fspath(d))
    target = os.path.abspath(os.fspath(into))
    verification = seal.verify(source)
    if not verification.get("ok"):
        raise core.ClaimError("cannot rebuild a claim whose sealed identity does not hold")

    parsed = _materialize(source, target, generated=False, input_from=input_from)
    own_outputs = recipe_module.generated_outputs(parsed)

    # ``produce_from`` permits an explicitly supplied realization to seed
    # outputs.  Missing outputs still go through the producer.
    if produce_from is not None:
        supplied = os.path.abspath(os.fspath(produce_from))
        for name in own_outputs:
            _copy_declared(supplied, target, name, required=False)

    production: list[dict[str, Any]] = []
    for step in recipe_module.produces(parsed):
        step_class = step.get("class", "generated")
        if "from" in step:
            continue
        # An explicitly supplied output need not invoke the producer again.
        output_path = core._safe(target, step["output"])
        if produce_from is not None and os.path.isfile(output_path):
            continue
        result = _produce(
            producer, target, step, own_outputs,
            guidance=guidance, producer_env=producer_env,
            claim_root=verification.get("root"),
        )
        production.append(result)
        if result.get("status") != "ok":
            backend = run.sandbox_backend()
            return {
                "ok": False, "root": None, "verdict": "producer " + str(result.get("status")),
                "production": production, "gates": [], "quarantine": backend,
            }
        if step_class not in ("generated", "free"):
            expected = core._safe(source, step["output"])
            if not _compare_pin(expected, output_path):
                return {
                    "ok": False, "root": None, "verdict": "pinned output mismatch",
                    "production": production, "gates": [],
                    "quarantine": run.sandbox_backend(),
                }

    rows = _gate_rows(source, target, parsed)
    quarantine = rows[-1]["quarantine"] if rows else run.sandbox_backend()
    gates_ok = all(row.get("status") in {"ok", "reproduced"} for row in rows)
    if not gates_ok:
        return {
            "ok": False, "root": None, "verdict": "gates failed",
            "production": production, "gates": rows, "quarantine": quarantine,
        }

    manifest = seal.seal(target)
    if manifest["root"] != verification.get("root"):
        return {
            "ok": False, "root": manifest["root"], "verdict": "root mismatch",
            "production": production, "gates": rows, "quarantine": quarantine,
        }

    elapsed = sum(float(item.get("seconds", 0.0)) for item in production)
    usage: dict[str, int | float] = {}
    for item in production:
        report = item.get("usage")
        if isinstance(report, Mapping):
            for key, value in report.items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    usage[key] = usage.get(key, 0) + value
    event: dict[str, Any] = {
        "kind": "rebuild", "seconds": elapsed,
        "quarantine": quarantine,
    }
    if usage:
        event["usage"] = usage
    run.ledger(target, event)

    return {
        "ok": True,
        "root": manifest["root"],
        "build_digest": identity.build_digest(target),
        "verdict": "earned",
        "production": production,
        "gates": rows,
        "quarantine": quarantine,
    }


ClaimError = core.ClaimError

__all__ = [
    "ClaimError", "_authorized", "_compare_pin", "_materialize", "_produce",
    "_read_usage", "_ssh_verify", "_step_guidance", "audit", "rebuild",
]
