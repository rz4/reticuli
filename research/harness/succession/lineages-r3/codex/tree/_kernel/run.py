"""Run claim gates with bounded execution and record production costs.

The sandbox probe is functional: a binary that exists but cannot confine a
process is never reported as an active sandbox.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from . import core


_REQ_OPS = ("<=", ">=", "==", "!=", "~=", "<", ">")
_BWRAP_OK = None


def _have(name: str) -> bool:
    return shutil.which(name) is not None


def _version_tuple(value: str) -> tuple[int, ...]:
    numbers = re.findall(r"\d+", value)
    return tuple(map(int, numbers)) if numbers else ()


def _tool_version(name: str) -> str | None:
    try:
        result = subprocess.run([name, "--version"], capture_output=True,
                                text=True, timeout=5, check=False)
        return (result.stdout or result.stderr).strip().splitlines()[0]
    except (OSError, subprocess.TimeoutExpired, IndexError):
        return None


def _version_ok(actual: str, requirement: str) -> bool:
    """Check a simple optional version constraint on a host requirement."""
    match = re.match(r"^\s*(<=|>=|==|!=|~=|<|>)\s*(\d+(?:\.\d+)*)\s*$", requirement)
    if not match:
        return False
    op, expected = match.groups()
    a, b = _version_tuple(actual), _version_tuple(expected)
    width = max(len(a), len(b))
    a, b = a + (0,) * (width - len(a)), b + (0,) * (width - len(b))
    if op == "~=":
        upper = (b[0] + 1,) if len(_version_tuple(expected)) == 1 else b[:-2] + (b[-2] + 1,)
        return a >= b and a < upper + (0,) * (width - len(upper))
    return {"<=": a <= b, ">=": a >= b, "==": a == b,
            "!=": a != b, "<": a < b, ">": a > b}[op]


def preflight(recipe: dict) -> list[str]:
    """List unavailable host requirements declared by a recipe."""
    missing = []
    for requirement in recipe.get("claim", {}).get("requires", []):
        if not isinstance(requirement, str):
            missing.append(str(requirement))
            continue
        name = re.split(r"<=|>=|==|!=|~=|<|>", requirement, maxsplit=1)[0].strip()
        condition = requirement[len(name):]
        available = _have(name) or importlib.util.find_spec(name) is not None
        if not available or (condition and not _version_ok(_tool_version(name) or "", condition)):
            missing.append(requirement)
    return missing


def gate_timeout(recipe: dict | None = None) -> float:
    declared = (recipe or {}).get("claim", {}).get("gate_timeout", core.GATE_TIMEOUT)
    try:
        bound = float(declared)
    except (TypeError, ValueError):
        bound = core.GATE_TIMEOUT
    return min(max(bound, 0.001), core.GATE_TIMEOUT)


def _bwrap_usable() -> bool:
    global _BWRAP_OK
    if _BWRAP_OK is None:
        if not _have("bwrap"):
            _BWRAP_OK = False
        else:
            try:
                probe = subprocess.run(
                    ["bwrap", "--ro-bind", "/", "/", "--dev-bind", "/dev", "/dev",
                     "--proc", "/proc", "--proc", "--", "/bin/sh", "-c", "exit 0"],
                    capture_output=True, timeout=5, check=False)
                _BWRAP_OK = probe.returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                _BWRAP_OK = False
    return _BWRAP_OK


def sandbox_backend() -> str:
    if os.environ.get(core._JAILED):
        return "inherited"
    if sys.platform == "darwin" and _have("sandbox-exec"):
        try:
            probe = subprocess.run(["sandbox-exec", "-p", "(version 1) (allow default)",
                                    "/bin/sh", "-c", "exit 0"],
                                   capture_output=True, timeout=5, check=False)
            if probe.returncode == 0:
                return "seatbelt"
        except (OSError, subprocess.TimeoutExpired):
            pass
    if sys.platform.startswith("linux") and _bwrap_usable():
        return "bubblewrap"
    return "none"


def sandbox() -> dict[str, str]:
    return {"backend": sandbox_backend()}


def _quote_sb(value: str) -> str:
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def _sandbox_argv(command: str, directory: str, backend: str) -> list[str]:
    shell = [core._SHELL, "-c", command]
    if backend == "seatbelt":
        rule = ("(version 1) (deny default) (allow process*) (allow file-read*) "
                f"(allow file-write* (subpath {_quote_sb(os.path.realpath(directory))}))")
        return ["sandbox-exec", "-p", rule, *shell]
    if backend == "bubblewrap":
        return ["bwrap", "--ro-bind", "/", "/", "--dev-bind", "/dev", "/dev",
                "--proc", "/proc", "--tmpfs", "/tmp", "--bind",
                os.path.realpath(directory), os.path.realpath(directory), "--unshare-net", "--", *shell]
    return shell


def _scrub_env(directory: str, extra: dict[str, str] | None = None,
               backend: str = "none") -> dict[str, str]:
    result = {key: os.environ[key] for key in core._KEEP_ENV if key in os.environ}
    result.setdefault("PATH", os.defpath)
    result.setdefault("LANG", "C.UTF-8")
    scratch = os.path.join(directory, core.STORE, "scratch")
    os.makedirs(scratch, exist_ok=True)
    result["HOME"] = scratch
    result["TMPDIR"] = scratch
    if backend in ("seatbelt", "bubblewrap", "inherited"):
        result[core._JAILED] = "1"
    if extra:
        result.update({str(k): str(v) for k, v in extra.items()})
    return result


def _kill_tree(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        process.kill()


def _run(argv: list[str], directory: str, env: dict[str, str], timeout: float) -> dict:
    started = time.monotonic()
    try:
        process = subprocess.Popen(argv, cwd=directory, env=env, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True, start_new_session=True)
        try:
            stdout, stderr = process.communicate(timeout=timeout)
            status = "ok" if process.returncode == 0 else "failed"
        except subprocess.TimeoutExpired:
            _kill_tree(process)
            stdout, stderr = process.communicate()
            status = "timeout"
        return {"status": status, "returncode": process.returncode,
                "stdout": stdout, "stderr": stderr,
                "seconds": time.monotonic() - started}
    except OSError as exc:
        return {"status": "environment", "returncode": None,
                "stdout": "", "stderr": str(exc), "seconds": time.monotonic() - started}


def run_gate(command: str, directory: os.PathLike[str] | str,
             recipe: dict | None = None, *, env: dict[str, str] | None = None,
             timeout: float | None = None) -> dict:
    directory = os.fspath(directory)
    missing = preflight(recipe or {})
    backend = sandbox_backend()
    if missing:
        return {"status": "environment", "quarantine": backend,
                "detail": "missing requirements: " + ", ".join(missing)}
    result = _run(_sandbox_argv(command, directory, backend), directory,
                  _scrub_env(directory, env, backend), timeout or gate_timeout(recipe))
    result["quarantine"] = backend
    return result


def _ledger_path(directory: os.PathLike[str] | str) -> str:
    return os.path.join(directory, core.LEDGER)


def ledger(directory: os.PathLike[str] | str, event: dict) -> None:
    path = _ledger_path(directory)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, sort_keys=True) + "\n")


def ledger_events(directory: os.PathLike[str] | str) -> list[dict]:
    try:
        with open(_ledger_path(directory), encoding="utf-8") as stream:
            return [json.loads(line) for line in stream if line.strip()]
    except FileNotFoundError:
        return []


def cost(directory: os.PathLike[str] | str) -> dict[str, float] | None:
    totals: dict[str, float] = {}
    for event in ledger_events(directory):
        if event.get("kind") not in ("producer", "produce"):
            continue
        for key in core.COST_KEYS:
            value = event.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                totals[key] = totals.get(key, 0) + value
    return totals or None


def _env_cache_dir() -> str:
    return os.environ.get(core._ENV_CACHE, os.path.join(tempfile.gettempdir(), "reticuli-env"))


def furnish(directory: os.PathLike[str] | str, recipe: dict) -> str | None:
    """Build a hash-pinned private Python environment when declared."""
    name = recipe.get("claim", {}).get("environment")
    if not name:
        return None
    import venv
    digest = core._hash_file(core._safe(directory, name))
    destination = os.path.join(_env_cache_dir(), digest, f"{sys.implementation.name}-{sys.version_info.major}.{sys.version_info.minor}")
    python = os.path.join(destination, "bin", "python")
    if not os.path.isfile(python):
        venv.create(destination, with_pip=True)
        result = subprocess.run([python, "-m", "pip", "install", "--require-hashes",
                                 "--only-binary=:all:", "-r", core._safe(directory, name)],
                                capture_output=True, text=True, timeout=core.FURNISH_TIMEOUT)
        if result.returncode:
            raise core.ClaimError(f"cannot furnish environment: {result.stderr.strip()}")
    return os.path.join(destination, "bin")


def independence(first: dict | None, third: dict | None) -> dict:
    first, third = first or {}, third or {}
    separate = bool(first.get("vendor") and third.get("vendor") and
                    first["vendor"] != third["vendor"])
    return {"established": separate, "vendor": third.get("vendor"),
            "model": third.get("model")}


def _independence_line(first: dict | None, third: dict | None) -> str:
    return "independence established" if independence(first, third)["established"] else "independence unestablished"


def _in_band(value: float, original: float, tolerance: float = core.TOLERANCE) -> bool:
    if original < 0 or value < 0:
        return False
    return value <= original * tolerance if original else value == 0
