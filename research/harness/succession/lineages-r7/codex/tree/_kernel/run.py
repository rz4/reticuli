"""Run claim gates with bounded execution and record measured work.

The runner keeps gate input in the claim directory, gives confined commands a
scratch area there, and reports the confinement that actually ran.
"""

from __future__ import annotations

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

from . import core


_REQ_OPS = ("<=", ">=", "==", "!=", "~=", "<", ">")
_BWRAP_OK = None
_SANDBOX_BACKEND = None


def _have(command: str) -> bool:
    return shutil.which(command) is not None


def _quote_sb(path: str | os.PathLike[str]) -> str:
    """Quote a literal path for a Seatbelt profile string."""
    return json.dumps(os.path.realpath(path))


def _seatbelt_profile(directory: str | os.PathLike[str]) -> str:
    # Read access includes the interpreter, shared libraries, and /etc/hosts.
    # process* permits the shells and subprocesses used by ordinary gates.
    return "\n".join((
        "(version 1)",
        "(deny default)",
        "(allow file-read*)",
        "(allow process*)",
        "(allow sysctl-read)",
        '(allow file-write* (literal "/dev/null"))',
        f"(allow file-write* (subpath {_quote_sb(directory)}))",
    )) + "\n"


def _bwrap_usable() -> bool:
    global _BWRAP_OK
    if _BWRAP_OK is not None:
        return _BWRAP_OK
    if not _have("bwrap"):
        _BWRAP_OK = False
        return False
    try:
        completed = subprocess.run(
            ["bwrap", "--ro-bind", "/", "/", "--dev-bind", "/dev", "/dev",
             "--proc", "/proc", "--unshare-net", "--", "/bin/sh", "-c", "true"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5,
            check=False)
        _BWRAP_OK = completed.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        _BWRAP_OK = False
    return _BWRAP_OK


def sandbox_backend() -> str:
    """Name a usable sandbox, or the inherited confinement signal."""
    global _SANDBOX_BACKEND
    if os.environ.get(core._JAILED):
        return "inherited"
    if _SANDBOX_BACKEND is not None:
        return _SANDBOX_BACKEND
    if platform.system() == "Darwin" and _have("sandbox-exec"):
        try:
            with tempfile.TemporaryDirectory() as room:
                profile = _seatbelt_profile(room)
                probe = subprocess.run(
                    ["sandbox-exec", "-p", profile, "/bin/sh", "-c",
                     "echo ok > probe && echo sink > /dev/null && /bin/true"],
                    cwd=room, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, timeout=5, check=False)
                if probe.returncode == 0:
                    _SANDBOX_BACKEND = "seatbelt"
                    return _SANDBOX_BACKEND
        except (OSError, subprocess.TimeoutExpired):
            pass
    if platform.system() == "Linux" and _bwrap_usable():
        _SANDBOX_BACKEND = "bubblewrap"
    else:
        _SANDBOX_BACKEND = "none"
    return _SANDBOX_BACKEND


def sandbox() -> dict[str, str]:
    return {"backend": sandbox_backend()}


def _sandbox_argv(command: str, directory: str, backend: str) -> list[str]:
    if backend == "seatbelt":
        return ["sandbox-exec", "-p", _seatbelt_profile(directory),
                core._SHELL, "-c", command]
    if backend == "bubblewrap":
        directory = os.path.realpath(directory)
        return ["bwrap", "--ro-bind", "/", "/", "--dev-bind", "/dev", "/dev",
                "--proc", "/proc", "--unshare-net", "--bind", directory, directory,
                "--chdir", directory, "--", core._SHELL, "-c", command]
    return [core._SHELL, "-c", command]


def _scrub_env(directory: str | os.PathLike[str] | None = None,
               extra: dict[str, str] | None = None) -> dict[str, str]:
    allowed = {key: os.environ[key] for key in core._KEEP_ENV if key in os.environ}
    if directory is not None:
        scratch = os.path.join(os.path.realpath(directory), core.STORE, "tmp")
        os.makedirs(scratch, exist_ok=True)
        allowed["HOME"] = scratch
        allowed["TMPDIR"] = scratch
    if extra:
        allowed.update({str(key): str(value) for key, value in extra.items()})
    return allowed


def gate_timeout(recipe: dict | None = None) -> float:
    """A declared timeout is the gate's ceiling, including above the default."""
    declared = (recipe or {}).get("claim", {}).get("gate_timeout")
    if declared is not None:
        if isinstance(declared, bool) or not isinstance(declared, (int, float)) \
                or not math.isfinite(declared) or declared <= 0:
            raise core.ClaimError("gate_timeout must be a positive number")
        return declared
    override = os.environ.get(core._ENV_TIMEOUT)
    if override is not None:
        try:
            value = float(override)
            if math.isfinite(value) and value > 0:
                return value
        except ValueError:
            pass
    return core.GATE_TIMEOUT


def _kill_tree(process: subprocess.Popen) -> None:
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    except ProcessLookupError:
        pass
    process.communicate()


def _run(argv: list[str], directory: str, env: dict[str, str],
         timeout: float) -> dict:
    start = time.monotonic()
    try:
        process = subprocess.Popen(argv, cwd=directory, env=env,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=True)
    except OSError as error:
        return {"status": "environment", "error": str(error),
                "seconds": time.monotonic() - start}
    try:
        stdout, stderr = process.communicate(timeout=timeout)
        status = "ok" if process.returncode == 0 else "failed"
    except subprocess.TimeoutExpired:
        _kill_tree(process)
        stdout, stderr = b"", b""
        status = "timeout"
    return {"status": status, "returncode": process.returncode,
            "stdout": stdout.decode("utf-8", "replace"),
            "stderr": stderr.decode("utf-8", "replace"),
            "seconds": time.monotonic() - start}


def run_gate(command: str, directory: str | os.PathLike[str],
             recipe: dict | None = None, *, env: dict[str, str] | None = None) -> dict:
    """Execute one gate and return its verdict and applied quarantine."""
    directory = os.path.realpath(directory)
    backend = sandbox_backend()
    gate_env = _scrub_env(directory, env)
    if backend in ("seatbelt", "bubblewrap"):
        gate_env[core._JAILED] = "1"
    result = _run(_sandbox_argv(command, directory, backend), directory,
                  gate_env, gate_timeout(recipe))
    result["quarantine"] = backend
    return result


def _ledger_path(directory: str | os.PathLike[str]) -> str:
    return core._safe(directory, core.LEDGER)


def ledger(directory: str | os.PathLike[str], event: dict) -> None:
    """Append one JSON event to the claim's cost ledger."""
    path = _ledger_path(directory)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as target:
        target.write(json.dumps(event, sort_keys=True) + "\n")


def ledger_events(directory: str | os.PathLike[str]) -> list[dict]:
    try:
        with open(_ledger_path(directory), encoding="utf-8") as source:
            return [json.loads(line) for line in source if line.strip()]
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as error:
        raise core.ClaimError(f"cannot read cost ledger: {error}") from error


def cost(directory: str | os.PathLike[str]) -> dict[str, float] | None:
    totals: dict[str, float] = {}
    for event in ledger_events(directory):
        for key in core.COST_KEYS:
            value = event.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool) \
                    and math.isfinite(value) and value >= 0:
                totals[key] = totals.get(key, 0) + value
    return totals or None


def _version_tuple(value: str) -> tuple[int, ...]:
    match = re.search(r"\d+(?:\.\d+)*", value)
    return tuple(map(int, match.group().split("."))) if match else ()


def _tool_version(command: str) -> str | None:
    if not _have(command):
        return None
    try:
        done = subprocess.run([command, "--version"], capture_output=True,
                              text=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return (done.stdout or done.stderr).strip().splitlines()[0]


def _version_ok(actual: str, operator: str, required: str) -> bool:
    left, right = _version_tuple(actual), _version_tuple(required)
    if not left or not right:
        return False
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
    return False


def preflight(recipe: dict) -> list[str]:
    """List missing host requirements declared by a claim."""
    import importlib.util

    missing = []
    for requirement in recipe.get("claim", {}).get("requires", []):
        if not isinstance(requirement, str):
            missing.append(str(requirement))
            continue
        match = re.fullmatch(r"([^<>=!~\s]+)\s*(<=|>=|==|!=|~=|<|>)?\s*(.*)", requirement)
        if match is None:
            missing.append(requirement)
            continue
        name, op, version = match.groups()
        found = _have(name) or importlib.util.find_spec(name) is not None
        if not found or (op and not _version_ok(_tool_version(name) or "", op, version)):
            missing.append(requirement)
    return missing


def _env_cache_dir() -> str:
    return os.path.expanduser(os.environ.get(core._ENV_CACHE,
                                            "~/.cache/reticuli/environments"))


def furnish(directory: str | os.PathLike[str], recipe: dict) -> str | None:
    """Build a cached, hash-pinned Python environment when one is declared."""
    from . import identity

    name = recipe.get("claim", {}).get("environment")
    if name is None:
        return None
    lock = core._safe(directory, name)
    digest = core._hash_file(lock)
    tag = f"{digest}-{sys.version_info.major}.{sys.version_info.minor}-{platform.system()}-{platform.machine()}"
    target = os.path.join(_env_cache_dir(), tag)
    marker = os.path.join(target, ".furnished")
    if os.path.isfile(marker):
        return target
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        venv.EnvBuilder(with_pip=True).create(target)
        pip = os.path.join(target, "bin", "pip")
        done = subprocess.run([pip, "install", "--require-hashes", "--only-binary=:all:",
                               "-r", lock], capture_output=True, text=True,
                              timeout=core.FURNISH_TIMEOUT, check=False)
        if done.returncode:
            raise core.ClaimError(f"environment furnishing failed: {done.stderr[-1000:]}")
        Path(marker).touch()
        return target
    except (OSError, subprocess.TimeoutExpired) as error:
        raise core.ClaimError(f"environment furnishing failed: {error}") from error


def _in_band(first: float, second: float, tolerance: float = core.TOLERANCE) -> bool:
    if first < 0 or second < 0 or tolerance < 1:
        return False
    if first == second == 0:
        return True
    return min(first, second) > 0 and max(first, second) / min(first, second) <= tolerance


def _independence_line(original: dict | None, rebuilt: dict | None) -> str:
    if not original or not rebuilt:
        return "unestablished"
    vendor1, vendor3 = original.get("vendor"), rebuilt.get("vendor")
    if not vendor1 or not vendor3 or vendor1 == vendor3:
        return "unestablished"
    return "declared"


def independence(original: dict | None, rebuilt: dict | None) -> dict:
    return {"status": _independence_line(original, rebuilt),
            "original": original, "rebuilt": rebuilt}
