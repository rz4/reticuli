"""Run claim gates with a bounded, scrubbed environment and record costs."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import venv
from pathlib import Path

from . import core, recipe as recipe_module


_REQ_OPS = ("<=", ">=", "==", "!=", "~=", "<", ">")
_BWRAP_OK = None


def _have(name: str) -> bool:
    return shutil.which(name) is not None


def _quote_sb(value: str) -> str:
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def _bwrap_usable() -> bool:
    global _BWRAP_OK
    if _BWRAP_OK is None:
        if not _have("bwrap"):
            _BWRAP_OK = False
        else:
            try:
                probe = subprocess.run(
                    ["bwrap", "--ro-bind", "/", "/", "--dev-bind", "/dev", "/dev",
                     "--proc", "/proc", "--unshare-net", "--", "/bin/sh", "-c", "true"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
                _BWRAP_OK = probe.returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                _BWRAP_OK = False
    return _BWRAP_OK


def sandbox_backend() -> str:
    if os.environ.get(core._JAILED):
        return "inherited"
    if sys.platform.startswith("linux") and _bwrap_usable():
        return "bubblewrap"
    # Seatbelt is only usable if a profile permits real gates while confining
    # both filesystem writes and networking. Merely finding sandbox-exec does
    # not establish that property.
    return "none"


def sandbox() -> dict[str, str]:
    return {"backend": sandbox_backend()}


def _sandbox_argv(command: str, directory: str, backend: str | None = None) -> list[str]:
    backend = backend or sandbox_backend()
    shell = "/bin/sh"
    if backend == "bubblewrap":
        return ["bwrap", "--ro-bind", "/", "/", "--bind", directory, directory,
                "--dev-bind", "/dev", "/dev", "--proc", "/proc",
                "--unshare-net", "--die-with-parent", "--chdir", directory,
                "--", shell, "-c", command]
    return [shell, "-c", command]


def _scrub_env(directory: str, extra: dict | None = None,
               backend: str | None = None) -> dict[str, str]:
    env = {key: os.environ[key] for key in core._KEEP_ENV if key in os.environ}
    env.setdefault("PATH", os.defpath)
    env.setdefault("LANG", "C.UTF-8")
    env["HOME"] = directory
    env["TMPDIR"] = directory
    if backend in ("bubblewrap", "seatbelt", "inherited"):
        env[core._JAILED] = "1"
    if extra:
        env.update({str(key): str(value) for key, value in extra.items()})
    return env


def _kill_tree(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (OSError, AttributeError):
        process.kill()


def _run(argv: list[str], *, cwd: str, env: dict[str, str], timeout: float) -> dict:
    start = time.monotonic()
    try:
        process = subprocess.Popen(argv, cwd=cwd, env=env, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True,
                                   start_new_session=True)
        try:
            stdout, stderr = process.communicate(timeout=timeout)
            status = "ok" if process.returncode == 0 else "failed"
        except subprocess.TimeoutExpired:
            _kill_tree(process)
            stdout, stderr = process.communicate()
            status = "timeout"
        return {"status": status, "returncode": process.returncode,
                "stdout": stdout, "stderr": stderr,
                "seconds": time.monotonic() - start}
    except OSError as exc:
        return {"status": "failed", "returncode": None, "stdout": "",
                "stderr": str(exc), "seconds": time.monotonic() - start}


def gate_timeout(parsed: dict | None = None) -> float:
    declared = (parsed or {}).get("claim", {}).get("gate_timeout")
    if declared is not None:
        if type(declared) not in (int, float) or not 0 < declared < float("inf"):
            raise core.ClaimError("gate_timeout must be a positive number")
        return float(declared)
    configured = os.environ.get(core._ENV_TIMEOUT)
    if configured:
        try:
            value = float(configured)
            if 0 < value < float("inf"):
                return value
        except ValueError:
            pass
    return core.GATE_TIMEOUT


def run_gate(command: str, directory: os.PathLike[str] | str,
             parsed: dict | None = None, *, env: dict | None = None) -> dict:
    directory = os.path.abspath(os.fspath(directory))
    backend = sandbox_backend()
    scratch = os.path.join(directory, core.STORE, "tmp")
    os.makedirs(scratch, exist_ok=True)
    result = _run(_sandbox_argv(command, directory, backend), cwd=directory,
                  env=_scrub_env(scratch, env, backend), timeout=gate_timeout(parsed))
    result["quarantine"] = backend
    return result


def _ledger_path(directory: os.PathLike[str] | str) -> str:
    return core._safe(directory, core.LEDGER)


def ledger(directory: os.PathLike[str] | str, event: dict) -> None:
    path = _ledger_path(directory)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, sort_keys=True) + "\n")


def ledger_events(directory: os.PathLike[str] | str) -> list[dict]:
    path = _ledger_path(directory)
    try:
        with open(path, encoding="utf-8") as stream:
            return [json.loads(line) for line in stream if line.strip()]
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as exc:
        raise core.ClaimError(f"cannot read ledger {path}: {exc}") from exc


def cost(directory: os.PathLike[str] | str) -> dict | None:
    totals: dict[str, float] = {}
    for event in ledger_events(directory):
        if event.get("kind") != "producer":
            continue
        for key in core.COST_KEYS:
            value = event.get(key)
            if type(value) in (int, float) and value >= 0:
                totals[key] = totals.get(key, 0) + value
    return totals or None


def _version_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", value))


def _version_ok(actual: str, operator: str, expected: str) -> bool:
    left, right = _version_tuple(actual), _version_tuple(expected)
    if operator == "==":
        return left == right
    if operator == "!=":
        return left != right
    if operator == ">=":
        return left >= right
    if operator == "<=":
        return left <= right
    if operator == ">":
        return left > right
    if operator == "<":
        return left < right
    if operator == "~=":
        return left >= right and left[:max(1, len(right) - 1)] == right[:max(1, len(right) - 1)]
    raise core.ClaimError(f"unknown version operator: {operator}")


def _tool_version(name: str) -> str | None:
    try:
        result = subprocess.run([name, "--version"], capture_output=True, text=True,
                                timeout=5, check=False)
        return (result.stdout or result.stderr).strip().splitlines()[0]
    except (OSError, subprocess.TimeoutExpired, IndexError):
        return None


def preflight(parsed: dict) -> list[str]:
    missing = []
    for requirement in parsed.get("claim", {}).get("requires", []):
        if not isinstance(requirement, str):
            missing.append(str(requirement))
            continue
        match = re.fullmatch(r"([^<>=!~\s]+)\s*(<=|>=|==|!=|~=|<|>)?\s*(.*)", requirement)
        if not match:
            missing.append(requirement)
            continue
        name, operator, version = match.groups()
        available = _have(name) or importlib.util.find_spec(name) is not None
        if not available or (operator and not _version_ok(_tool_version(name) or "", operator, version)):
            missing.append(requirement)
    return missing


def _env_cache_dir() -> str:
    return os.path.expanduser(os.environ.get(core._ENV_CACHE, "~/.cache/reticuli/environments"))


def furnish(directory: os.PathLike[str] | str, parsed: dict | None = None) -> str | None:
    parsed = parsed or recipe_module.load_recipe(directory)
    named = parsed["claim"].get("environment")
    if not named:
        return None
    lock = core._safe(directory, named)
    digest = core._hash_file(lock)
    cache_key = hashlib.sha256(f"{digest}:{sys.executable}:{platform.platform()}".encode()).hexdigest()
    target = os.path.join(_env_cache_dir(), cache_key)
    python = os.path.join(target, "bin", "python")
    if not os.path.isfile(python):
        os.makedirs(os.path.dirname(target), exist_ok=True)
        venv.EnvBuilder(with_pip=True).create(target)
        done = subprocess.run([python, "-m", "pip", "install", "--require-hashes",
                               "--only-binary=:all:", "-r", lock],
                              capture_output=True, text=True, timeout=core.FURNISH_TIMEOUT)
        if done.returncode:
            shutil.rmtree(target, ignore_errors=True)
            raise core.ClaimError(f"cannot furnish environment: {done.stderr.strip()}")
    return target


def _independence_line(producer: dict | None) -> str:
    producer = producer or {}
    return "/".join(str(producer.get(key, "")) for key in ("vendor", "model"))


def independence(original: dict | None, rebuild: dict | None) -> dict:
    a, b = _independence_line(original), _independence_line(rebuild)
    established = bool(a.strip("/") and b.strip("/") and a != b)
    return {"established": established, "original": a, "rebuild": b}


def _in_band(original: float, rebuild: float, tolerance: float = core.TOLERANCE) -> bool:
    if original < 0 or rebuild < 0 or tolerance <= 0:
        return False
    if original == 0:
        return rebuild == 0
    return rebuild <= original * tolerance
