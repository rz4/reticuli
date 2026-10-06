"""Run claim gates in a bounded, scrubbed environment and record costs."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
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
from typing import Any

from . import core


_REQ_OPS = ("<=", ">=", "==", "!=", "~=", "<", ">")
_BWRAP_OK = None


def _have(name: str) -> bool:
    return shutil.which(name) is not None


def _quote_sb(path: str) -> str:
    """Quote a literal path in a Seatbelt profile."""
    return '"' + path.replace('\\', '\\\\').replace('"', '\\"') + '"'


def _seatbelt_profile(directory: str) -> str:
    room = os.path.realpath(directory)
    return ("(version 1)(deny default)"
            "(allow process*)(allow file-read*)"
            "(allow sysctl*)"
            "(allow file-write* (subpath " + _quote_sb(room) + ")"
            " (subpath \"/dev\"))")


def _bwrap_usable() -> bool:
    global _BWRAP_OK
    if _BWRAP_OK is not None:
        return _BWRAP_OK
    if not _have("bwrap"):
        _BWRAP_OK = False
        return False
    try:
        p = subprocess.run(
            ["bwrap", "--unshare-net", "--ro-bind", "/", "/",
             "--dev-bind", "/dev", "/dev", "--proc", "/proc",
             "--", "/bin/sh", "-c", "true"],
            capture_output=True, timeout=5, check=False)
        _BWRAP_OK = p.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        _BWRAP_OK = False
    return _BWRAP_OK


def sandbox_backend() -> str:
    if os.environ.get(core._JAILED):
        return "inherited"
    if sys.platform == "darwin" and _have("sandbox-exec"):
        try:
            with tempfile.TemporaryDirectory() as room:
                args = ["sandbox-exec", "-p", _seatbelt_profile(room),
                        "/bin/sh", "-c", "printf ok > probe && cat probe > /dev/null"]
                p = subprocess.run(args, cwd=room, capture_output=True,
                                   timeout=5, check=False)
                if p.returncode == 0:
                    return "seatbelt"
        except (OSError, subprocess.TimeoutExpired):
            pass
    if sys.platform.startswith("linux") and _bwrap_usable():
        return "bubblewrap"
    return "none"


def sandbox() -> dict[str, str]:
    return {"backend": sandbox_backend()}


def _sandbox_argv(command: str, directory: str, backend: str) -> list[str]:
    shell = [core._SHELL, "-c", command]
    if backend == "seatbelt":
        return ["sandbox-exec", "-p", _seatbelt_profile(directory), *shell]
    if backend == "bubblewrap":
        room = os.path.realpath(directory)
        return ["bwrap", "--unshare-net", "--ro-bind", "/", "/",
                "--dev-bind", "/dev", "/dev", "--proc", "/proc",
                "--bind", room, room, "--chdir", room, "--", *shell]
    return shell


def _scrub_env(directory: str, backend: str, extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {key: os.environ[key] for key in core._KEEP_ENV if key in os.environ}
    env["PATH"] = os.environ.get("PATH", os.defpath)
    env["HOME"] = directory
    env["TMPDIR"] = directory
    if backend in ("seatbelt", "bubblewrap"):
        env[core._JAILED] = "1"
    if extra:
        env.update(extra)
    return env


def _kill_tree(process: subprocess.Popen[Any]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (OSError, AttributeError):
        try:
            process.kill()
        except OSError:
            pass


def _run(argv: list[str], directory: str, env: dict[str, str],
         timeout: float) -> dict[str, Any]:
    started = time.monotonic()
    try:
        process = subprocess.Popen(argv, cwd=directory, env=env,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=True)
    except OSError as exc:
        return {"status": "environment", "stdout": "", "stderr": str(exc),
                "seconds": time.monotonic() - started}
    try:
        out, err = process.communicate(timeout=timeout)
        status = "ok" if process.returncode == 0 else "failed"
    except subprocess.TimeoutExpired:
        _kill_tree(process)
        out, err = process.communicate()
        status = "timeout"
    return {"status": status, "returncode": process.returncode,
            "stdout": out.decode("utf-8", "replace"),
            "stderr": err.decode("utf-8", "replace"),
            "seconds": time.monotonic() - started}


def gate_timeout(recipe: dict[str, Any] | None) -> float:
    declared = (recipe or {}).get("claim", {}).get("gate_timeout")
    if declared is not None:
        return float(declared)
    host = os.environ.get(core._ENV_TIMEOUT)
    if host:
        try:
            value = float(host)
            if math.isfinite(value) and value > 0:
                return value
        except ValueError:
            pass
    return core.GATE_TIMEOUT


def run_gate(command: str, directory: os.PathLike[str] | str,
             recipe: dict[str, Any] | None = None,
             env: dict[str, str] | None = None) -> dict[str, Any]:
    """Run one shell gate and report its outcome and actual quarantine."""
    room = os.path.realpath(directory)
    backend = sandbox_backend()
    scratch = os.path.join(room, core.STORE, "tmp")
    os.makedirs(scratch, exist_ok=True)
    gate_env = _scrub_env(scratch, backend, env)
    result = _run(_sandbox_argv(command, room, backend), room, gate_env,
                  gate_timeout(recipe))
    result["quarantine"] = backend
    return result


def _ledger_path(directory: os.PathLike[str] | str) -> str:
    return core._safe(directory, core.LEDGER)


def ledger(directory: os.PathLike[str] | str, event: dict[str, Any]) -> None:
    path = _ledger_path(directory)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, sort_keys=True) + "\n")


def ledger_events(directory: os.PathLike[str] | str) -> list[dict[str, Any]]:
    try:
        with open(_ledger_path(directory), encoding="utf-8") as stream:
            return [json.loads(line) for line in stream if line.strip()]
    except FileNotFoundError:
        return []


def cost(directory: os.PathLike[str] | str) -> dict[str, float] | None:
    totals: dict[str, float] = {}
    for event in ledger_events(directory):
        if event.get("kind") != "producer":
            continue
        for key in core.COST_KEYS:
            value = event.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                totals[key] = totals.get(key, 0) + value
    return totals or None


def preflight(recipe: dict[str, Any]) -> list[str]:
    missing = []
    for name in recipe.get("claim", {}).get("requires", []):
        if not _have(name) and importlib.util.find_spec(name) is None:
            missing.append(name)
    return missing


def _env_cache_dir() -> str:
    return os.path.expanduser(os.environ.get(core._ENV_CACHE, "~/.cache/reticuli/env"))


def furnish(recipe: dict[str, Any], directory: os.PathLike[str] | str) -> str | None:
    """Create or reuse the recipe's hash-pinned Python environment."""
    name = recipe.get("claim", {}).get("environment")
    if not name:
        return None
    requirements = core._safe(directory, name)
    digest = core._hash_file(requirements)
    key = hashlib.sha256((digest + sys.executable + platform.platform()).encode()).hexdigest()
    target = os.path.join(_env_cache_dir(), key)
    marker = os.path.join(target, ".ready")
    if os.path.isfile(marker):
        return target
    os.makedirs(os.path.dirname(target), exist_ok=True)
    venv.EnvBuilder(with_pip=True).create(target)
    pip = os.path.join(target, "Scripts" if os.name == "nt" else "bin", "pip")
    done = subprocess.run([pip, "install", "--require-hashes", "--only-binary=:all:",
                           "-r", requirements], capture_output=True, text=True,
                          timeout=core.FURNISH_TIMEOUT, check=False)
    if done.returncode:
        raise core.ClaimError(f"cannot furnish environment: {done.stderr.strip()}")
    Path(marker).write_text("ready\n", encoding="utf-8")
    return target


def _version_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", version))


def _tool_version(name: str) -> str | None:
    if not _have(name):
        return None
    try:
        result = subprocess.run([name, "--version"], capture_output=True,
                                text=True, timeout=5, check=False)
        return (result.stdout or result.stderr).splitlines()[0]
    except (OSError, subprocess.TimeoutExpired, IndexError):
        return None


def _version_ok(actual: str, requirement: str) -> bool:
    match = re.fullmatch(r"\s*(<=|>=|==|!=|~=|<|>)\s*([\d.]+)\s*", requirement)
    if not match:
        return False
    op, expected = match.groups()
    left, right = _version_tuple(actual), _version_tuple(expected)
    if op == "==":
        return left == right
    if op == "!=":
        return left != right
    if op == "<":
        return left < right
    if op == ">":
        return left > right
    if op == "<=":
        return left <= right
    if op == ">=":
        return left >= right
    return left >= right and left[:1] == right[:1]


def _in_band(first: float, second: float, tolerance: float = core.TOLERANCE) -> bool:
    if first < 0 or second < 0 or tolerance < 1:
        return False
    if first == second == 0:
        return True
    if not first or not second:
        return False
    return max(first / second, second / first) <= tolerance


def _independence_line(first: dict[str, Any] | None,
                       second: dict[str, Any] | None) -> str:
    if not first or not second:
        return "unestablished"
    if first.get("vendor") and first.get("vendor") != second.get("vendor"):
        return "declared"
    return "unestablished"


def independence(first: dict[str, Any] | None,
                 second: dict[str, Any] | None) -> str:
    return _independence_line(first, second)
