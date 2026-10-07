"""Run claim gates under a bounded, scrubbed host environment.

Gate results and production usage are residue; neither enters claim identity.
"""

from __future__ import annotations

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

from . import core


_REQ_OPS = ('<=', '>=', '==', '!=', '~=', '<', '>')
_BWRAP_OK = None


def _have(name: str) -> bool:
    return shutil.which(name) is not None


def _quote_sb(path: str) -> str:
    return '"' + path.replace('\\', '\\\\').replace('"', '\\"') + '"'


def _seatbelt_profile(directory: str) -> str:
    room = _quote_sb(os.path.realpath(directory))
    return ("(version 1)\n(deny default)\n"
            "(allow file-read*)\n"
            "(allow file-write* (subpath " + room + ") (subpath \"/dev\"))\n"
            "(allow process*)\n(allow sysctl*)\n(allow mach-lookup)\n")


def _bwrap_usable() -> bool:
    global _BWRAP_OK
    if _BWRAP_OK is None:
        if not _have("bwrap"):
            _BWRAP_OK = False
        else:
            try:
                result = subprocess.run(
                    ["bwrap", "--ro-bind", "/", "/", "--dev-bind", "/dev", "/dev",
                     "--proc", "/proc", "--proc", "--tmpfs", "/tmp", "--unshare-net",
                     "/bin/sh", "-c", "true"], capture_output=True, timeout=5)
                _BWRAP_OK = result.returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                _BWRAP_OK = False
    return bool(_BWRAP_OK)


def sandbox_backend() -> str:
    if os.environ.get(core._JAILED):
        return "inherited"
    if sys.platform == "darwin" and _have("sandbox-exec"):
        try:
            with tempfile.TemporaryDirectory() as directory:
                probe = subprocess.run(
                    ["sandbox-exec", "-p", _seatbelt_profile(directory),
                     "/bin/sh", "-c", "echo ok > probe"], cwd=directory,
                    capture_output=True, timeout=5)
                if probe.returncode == 0 and os.path.isfile(os.path.join(directory, "probe")):
                    return "seatbelt"
        except (OSError, subprocess.TimeoutExpired):
            pass
    if sys.platform.startswith("linux") and _bwrap_usable():
        return "bubblewrap"
    return "none"


def sandbox(directory: str | None = None) -> dict:
    return {"backend": sandbox_backend(), "directory": directory}


def _sandbox_argv(command: str, directory: str, backend: str) -> list[str]:
    shell = [core._SHELL, "-c", command]
    if backend == "seatbelt":
        return ["sandbox-exec", "-p", _seatbelt_profile(directory), *shell]
    if backend == "bubblewrap":
        return ["bwrap", "--ro-bind", "/", "/", "--dev-bind", "/dev", "/dev",
                "--proc", "/proc", "--proc", "--bind", os.path.realpath(directory),
                os.path.realpath(directory), "--unshare-net", "--chdir",
                os.path.realpath(directory), *shell]
    return shell


def _scrub_env(directory: str, backend: str = "none", extra: dict | None = None) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items()
           if key in core._KEEP_ENV or key.startswith("RETICULI_")}
    env.setdefault("PATH", os.defpath)
    if backend in ("seatbelt", "bubblewrap"):
        scratch = os.path.join(directory, core.STORE, "tmp")
        os.makedirs(scratch, exist_ok=True)
        env["HOME"] = scratch
        env["TMPDIR"] = scratch
        env[core._JAILED] = "1"
    if extra:
        env.update({str(k): str(v) for k, v in extra.items()})
    return env


def _kill_tree(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        try:
            process.kill()
        except OSError:
            pass


def _run(argv: list[str], directory: str, env: dict[str, str], timeout: float) -> dict:
    started = time.monotonic()
    try:
        process = subprocess.Popen(argv, cwd=directory, env=env,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=True)
    except OSError as exc:
        return {"status": "environment", "returncode": None,
                "stdout": "", "stderr": str(exc), "seconds": time.monotonic() - started}
    try:
        stdout, stderr = process.communicate(timeout=timeout)
        status = "ok" if process.returncode == 0 else "failed"
    except subprocess.TimeoutExpired:
        _kill_tree(process)
        stdout, stderr = process.communicate()
        status = "timeout"
    return {"status": status, "returncode": process.returncode,
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
            "seconds": time.monotonic() - started}


def gate_timeout(claim_recipe: dict | None) -> float:
    declared = ((claim_recipe or {}).get("claim") or {}).get("gate_timeout")
    ceiling = os.environ.get(core._ENV_TIMEOUT)
    if declared is not None:
        value = float(declared)
    elif ceiling is not None:
        value = float(ceiling)
    else:
        value = core.GATE_TIMEOUT
    if not 0 < value < float("inf"):
        raise core.ClaimError("gate_timeout must be a positive finite number")
    return value


def run_gate(command: str, directory: str, claim_recipe: dict | None,
             env: dict | None = None) -> dict:
    backend = sandbox_backend()
    environment = _scrub_env(directory, backend, env)
    result = _run(_sandbox_argv(command, directory, backend), directory,
                  environment, gate_timeout(claim_recipe))
    result["quarantine"] = backend
    return result


def _ledger_path(directory: str) -> str:
    return core._safe(directory, core.LEDGER)


def ledger(directory: str, event: dict) -> None:
    path = _ledger_path(directory)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, sort_keys=True) + "\n")


def ledger_events(directory: str) -> list[dict]:
    try:
        with open(_ledger_path(directory), encoding="utf-8") as stream:
            return [json.loads(line) for line in stream if line.strip()]
    except FileNotFoundError:
        return []


def cost(directory: str) -> dict | None:
    totals: dict[str, float | int] = {}
    for event in ledger_events(directory):
        if event.get("kind") not in ("producer", "production"):
            continue
        for key in core.COST_KEYS:
            value = event.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                totals[key] = totals.get(key, 0) + value
    return totals or None


def _version_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", value))


def _version_ok(actual: str, requirement: str) -> bool:
    match = re.match(r"\s*(<=|>=|==|!=|~=|<|>)\s*([\d.]+)", requirement)
    if not match:
        return True
    op, expected = match.groups()
    left, right = _version_tuple(actual), _version_tuple(expected)
    return {"<": left < right, "<=": left <= right, "==": left == right,
            "!=": left != right, ">=": left >= right, ">": left > right,
            "~=": left >= right and left[:1] == right[:1]}[op]


def _tool_version(name: str) -> str | None:
    try:
        result = subprocess.run([name, "--version"], capture_output=True,
                                text=True, timeout=5)
        return (result.stdout or result.stderr).strip() if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def preflight(claim_recipe: dict) -> list[str]:
    missing = []
    for requirement in claim_recipe.get("claim", {}).get("requires", []):
        if not isinstance(requirement, str):
            missing.append(str(requirement))
            continue
        match = re.match(r"^([^<>=!~]+)(.*)$", requirement)
        name, constraint = match.groups() if match else (requirement, "")
        name = name.strip()
        found = _have(name) or importlib.util.find_spec(name) is not None
        if not found or (constraint and not _version_ok(_tool_version(name) or "0", constraint)):
            missing.append(requirement)
    return missing


def _env_cache_dir() -> str:
    return os.environ.get(core._ENV_CACHE, os.path.join(Path.home(), ".cache", "reticuli", "env"))


def furnish(directory: str, claim_recipe: dict) -> dict:
    name = claim_recipe.get("claim", {}).get("environment")
    if not name:
        return {"status": "ok", "path": None}
    source = core._safe(directory, name)
    digest = core._hash_file(source)
    key = f"{digest}-{sys.version_info.major}.{sys.version_info.minor}-{platform.system()}-{platform.machine()}"
    target = os.path.join(_env_cache_dir(), key)
    executable = os.path.join(target, "bin", "python")
    if os.path.isfile(executable):
        return {"status": "ok", "path": target}
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        venv.EnvBuilder(with_pip=True).create(target)
        completed = subprocess.run(
            [executable, "-m", "pip", "install", "--require-hashes",
             "--only-binary=:all:", "-r", source], capture_output=True,
            text=True, timeout=core.FURNISH_TIMEOUT)
        if completed.returncode:
            return {"status": "environment", "detail": completed.stderr[-2000:]}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "environment", "detail": str(exc)}
    return {"status": "ok", "path": target}


def _in_band(value: float, target: float, tolerance: float = core.TOLERANCE) -> bool:
    return target / tolerance <= value <= target * tolerance


def _independence_line(original: dict | None, rebuilt: dict | None) -> str:
    first = (original or {}).get("vendor")
    second = (rebuilt or {}).get("vendor")
    if first and second and first != second:
        return "independent vendors declared"
    return "independence unestablished"


def independence(original: dict | None, rebuilt: dict | None) -> dict:
    return {"established": bool(original and rebuilt and original.get("vendor")
                                and rebuilt.get("vendor")
                                and original.get("vendor") != rebuilt.get("vendor")),
            "detail": _independence_line(original, rebuilt)}
