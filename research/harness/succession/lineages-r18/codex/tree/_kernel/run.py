"""Gate execution, host confinement, and the run cost ledger."""

from __future__ import annotations

import hashlib
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

from . import core


_REQ_OPS = ('<=', '>=', '==', '!=', '~=', '<', '>')
_BWRAP_OK = None
_SEATBELT_OK = None


def _have(name: str) -> bool:
    return shutil.which(name) is not None


def _quote_sb(path: str) -> str:
    return json.dumps(os.path.realpath(path))


def _seatbelt_profile(workspace: str) -> str:
    # The host remains readable and usable. File writes and networking are
    # narrowed explicitly, leaving subprocesses and system services intact.
    return ("(version 1)\n"
            "(allow default)\n"
            "(deny network*)\n"
            "(deny file-write*)\n"
            f"(allow file-write* (subpath {_quote_sb(workspace)}))\n"
            "(allow file-write* (literal \"/dev/null\"))\n")


def _bwrap_usable() -> bool:
    global _BWRAP_OK
    if _BWRAP_OK is None:
        if not _have("bwrap"):
            _BWRAP_OK = False
        else:
            try:
                probe = subprocess.run(
                    ["bwrap", "--ro-bind", "/", "/", "--dev-bind", "/dev", "/dev",
                     "--proc", "/proc", "--", "/bin/sh", "-c", "true"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=5, check=False)
                _BWRAP_OK = probe.returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                _BWRAP_OK = False
    return _BWRAP_OK


def sandbox_backend() -> str:
    global _SEATBELT_OK
    if os.environ.get(core._JAILED):
        return "inherited"
    if sys.platform == "darwin" and _have("sandbox-exec"):
        if _SEATBELT_OK is None:
            try:
                with tempfile.TemporaryDirectory() as room:
                    profile = _seatbelt_profile(room)
                    allowed = subprocess.run(
                        ["sandbox-exec", "-p", profile, "/bin/sh", "-c",
                         "echo ok > allowed && echo sink > /dev/null && python3 -c 'import platform, pwd, os; platform.uname(); pwd.getpwuid(os.getuid())'"],
                        cwd=room, stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL, timeout=10, check=False)
                    with tempfile.TemporaryDirectory() as outside:
                        forbidden = subprocess.run(
                            ["sandbox-exec", "-p", profile, "/bin/sh", "-c",
                             f"echo leak > {outside}/LEAK"], cwd=room,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            timeout=5, check=False)
                        _SEATBELT_OK = (allowed.returncode == 0 and
                                        forbidden.returncode != 0 and
                                        not os.path.exists(os.path.join(outside, "LEAK")))
            except (OSError, subprocess.TimeoutExpired):
                _SEATBELT_OK = False
        if _SEATBELT_OK:
            return "seatbelt"
    if sys.platform.startswith("linux") and _bwrap_usable():
        return "bubblewrap"
    return "none"


def sandbox(workspace: str | None = None) -> dict[str, str]:
    return {"backend": sandbox_backend()}


def _sandbox_argv(command: str, workspace: str, backend: str) -> list[str]:
    shell = [core._SHELL, "-c", command]
    if backend == "seatbelt":
        return ["sandbox-exec", "-p", _seatbelt_profile(workspace), *shell]
    if backend == "bubblewrap":
        workspace = os.path.realpath(workspace)
        return ["bwrap", "--ro-bind", "/", "/", "--dev-bind", "/dev", "/dev",
                "--proc", "/proc", "--bind", workspace, workspace,
                "--chdir", workspace, "--", *shell]
    return shell


def _scrub_env(workspace: str | None = None, backend: str = "none",
               extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {key: os.environ[key] for key in core._KEEP_ENV if key in os.environ}
    env.setdefault("PATH", os.defpath)
    if workspace and backend not in ("none", "inherited"):
        scratch = os.path.join(workspace, core.STORE, "tmp")
        os.makedirs(scratch, exist_ok=True)
        env["HOME"] = scratch
        env["TMPDIR"] = scratch
        env[core._JAILED] = "1"
    if extra:
        env.update(extra)
    return env


def _kill_tree(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        try:
            process.kill()
        except OSError:
            pass


def _run(argv: list[str], workspace: str, timeout: float,
         env: dict[str, str]) -> dict[str, object]:
    start = time.monotonic()
    try:
        process = subprocess.Popen(argv, cwd=workspace, env=env,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, start_new_session=True)
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
        return {"status": "environment", "returncode": None,
                "stdout": "", "stderr": str(exc), "seconds": time.monotonic() - start}


def gate_timeout(recipe: dict | None) -> float:
    claim = recipe.get("claim", {}) if isinstance(recipe, dict) else {}
    declared = claim.get("gate_timeout") if isinstance(claim, dict) else None
    if isinstance(declared, (int, float)) and not isinstance(declared, bool) and declared > 0:
        return float(declared)
    configured = os.environ.get(core._ENV_TIMEOUT)
    if configured:
        try:
            value = float(configured)
            if value > 0:
                return value
        except ValueError:
            pass
    return core.GATE_TIMEOUT


def run_gate(command: str, workspace: str, recipe: dict | None,
             extra_env: dict[str, str] | None = None) -> dict[str, object]:
    backend = sandbox_backend()
    env = _scrub_env(workspace, backend, extra_env)
    result = _run(_sandbox_argv(command, workspace, backend), workspace,
                  gate_timeout(recipe), env)
    result["quarantine"] = backend
    return result


def _ledger_path(workspace: str) -> str:
    return os.path.join(workspace, core.LEDGER)


def ledger(workspace: str, event: dict[str, object]) -> None:
    path = _ledger_path(workspace)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as output:
        output.write(json.dumps(event, sort_keys=True) + "\n")


def ledger_events(workspace: str) -> list[dict[str, object]]:
    try:
        with open(_ledger_path(workspace), encoding="utf-8") as source:
            return [json.loads(line) for line in source if line.strip()]
    except FileNotFoundError:
        return []


def cost(workspace: str) -> dict[str, int | float] | None:
    totals: dict[str, int | float] = {}
    for event in ledger_events(workspace):
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
    match = re.match(r"^(<=|>=|==|!=|~=|<|>)(.+)$", requirement)
    if not match:
        return True
    op, expected = match.groups()
    left, right = _version_tuple(actual), _version_tuple(expected)
    return {"<": left < right, "<=": left <= right, "==": left == right,
            "!=": left != right, ">=": left >= right, ">": left > right,
            "~=": left >= right and left[:1] == right[:1]}[op]


def _tool_version(name: str) -> str | None:
    try:
        found = subprocess.run([name, "--version"], capture_output=True,
                               text=True, timeout=5, check=False)
        return (found.stdout or found.stderr).strip()
    except (OSError, subprocess.TimeoutExpired):
        return None


def preflight(recipe: dict) -> list[str]:
    claim = recipe.get("claim", {})
    missing = []
    for requirement in claim.get("requires", []):
        if not isinstance(requirement, str):
            missing.append(str(requirement))
            continue
        name = re.split(r"[<>=~!]", requirement, maxsplit=1)[0]
        if not _have(name):
            try:
                import importlib.util
                present = importlib.util.find_spec(name) is not None
            except (ImportError, ValueError, ModuleNotFoundError):
                present = False
            if not present:
                missing.append(requirement)
    return missing


def _env_cache_dir() -> str:
    return os.environ.get(core._ENV_CACHE,
                          os.path.join(os.path.expanduser("~"), ".cache", "reticuli", "env"))


def furnish(workspace: str, recipe: dict) -> str | None:
    name = recipe.get("claim", {}).get("environment")
    if not name:
        return None
    path = core._safe(workspace, name)
    digest = core._hash_file(path)
    key = hashlib.sha256(f"{digest}:{sys.executable}:{platform.platform()}".encode()).hexdigest()
    destination = os.path.join(_env_cache_dir(), key)
    python = os.path.join(destination, "bin", "python")
    if not os.path.isfile(python):
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        venv.create(destination, with_pip=True)
        done = subprocess.run([python, "-m", "pip", "install", "--require-hashes",
                               "--only-binary=:all:", "-r", path],
                              capture_output=True, text=True,
                              timeout=core.FURNISH_TIMEOUT, check=False)
        if done.returncode:
            shutil.rmtree(destination, ignore_errors=True)
            raise core.ClaimError(f"cannot furnish environment: {done.stderr.strip()}")
    return os.path.join(destination, "bin")


def _in_band(a: float, b: float, tolerance: float = core.TOLERANCE) -> bool:
    return a <= b * tolerance and b <= a * tolerance


def _independence_line(original: dict, rebuild: dict) -> str:
    a, b = original.get("vendor"), rebuild.get("vendor")
    if not a or not b:
        return "unestablished"
    return "same vendor" if a == b else "different vendor"


def independence(original: dict, rebuild: dict) -> dict[str, object]:
    return {"status": _independence_line(original, rebuild),
            "original": original, "rebuild": rebuild}
