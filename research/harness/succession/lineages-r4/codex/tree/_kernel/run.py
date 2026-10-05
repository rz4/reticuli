"""Execute claim gates and record their measured costs.

Gate execution is deliberately separate from recipe parsing and identity:
the same command runner is used regardless of which operation requested a
gate.  A sandbox is used only after a functional probe succeeds.
"""

from __future__ import annotations

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

from . import core


_REQ_OPS = ("<=", ">=", "==", "!=", "~=", "<", ">")
_BWRAP_OK = None


def _have(name: str) -> bool:
    return shutil.which(name) is not None


def _version_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", value))


def _version_ok(actual: str, requirement: str) -> bool:
    match = re.match(r"^\s*(<=|>=|==|!=|~=|<|>)\s*(\d+(?:\.\d+)*)\s*$", requirement)
    if not match:
        return False
    operator, wanted = match.groups()
    a, b = _version_tuple(actual), _version_tuple(wanted)
    width = max(len(a), len(b))
    a, b = a + (0,) * (width - len(a)), b + (0,) * (width - len(b))
    if operator == "<=": return a <= b
    if operator == ">=": return a >= b
    if operator == "==": return a == b
    if operator == "!=": return a != b
    if operator == "<": return a < b
    if operator == ">": return a > b
    return a >= b and a[0] == b[0]


def _tool_version(name: str) -> str | None:
    try:
        result = subprocess.run([name, "--version"], capture_output=True,
                                text=True, timeout=5, check=False)
        return (result.stdout or result.stderr).strip().splitlines()[0]
    except (OSError, subprocess.TimeoutExpired, IndexError):
        return None


def preflight(recipe: dict | None) -> list[str]:
    """Return host requirements that cannot be found."""
    requirements = (recipe or {}).get("claim", {}).get("requires", [])
    missing = []
    for requirement in requirements:
        if not isinstance(requirement, str):
            missing.append(str(requirement))
            continue
        name = re.split(r"[<>=!~]", requirement, 1)[0].strip()
        if not name or not (_have(name) or importlib.util.find_spec(name)):
            missing.append(requirement)
    return missing


def _quote_sb(path: str) -> str:
    """Quote a path in a Seatbelt profile string."""
    return '"' + path.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _bwrap_usable() -> bool:
    global _BWRAP_OK
    if _BWRAP_OK is None:
        if not _have("bwrap"):
            _BWRAP_OK = False
        else:
            try:
                probe = subprocess.run(
                    ["bwrap", "--ro-bind", "/", "/", "--proc", "/proc",
                     "--dev-bind", "/dev", "/dev", "--", "/bin/sh", "-c", "exit 0"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=5, check=False)
                _BWRAP_OK = probe.returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                _BWRAP_OK = False
    return _BWRAP_OK


def sandbox_backend() -> str:
    if os.environ.get(core._JAILED):
        return "inherited"
    if sys.platform == "darwin" and _have("sandbox-exec"):
        try:
            result = subprocess.run(["sandbox-exec", "-p", "(version 1) (allow default)",
                                     "/usr/bin/true"], stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL, timeout=5, check=False)
            if result.returncode == 0:
                return "seatbelt"
        except (OSError, subprocess.TimeoutExpired):
            pass
    if sys.platform.startswith("linux") and _bwrap_usable():
        return "bubblewrap"
    return "none"


def sandbox() -> dict[str, str]:
    return {"backend": sandbox_backend()}


def _sandbox_argv(command: str, directory: str, backend: str, scratch: str) -> list[str]:
    shell = [core._SHELL, "-c", command]
    if backend == "seatbelt":
        profile = ("(version 1) (deny default) "
                   "(allow process*) (allow file-read*) "
                   f"(allow file-write* (subpath {_quote_sb(os.path.realpath(directory))}))")
        return ["sandbox-exec", "-p", profile, *shell]
    if backend == "bubblewrap":
        return ["bwrap", "--ro-bind", "/", "/", "--bind", os.path.realpath(directory),
                os.path.realpath(directory), "--proc", "/proc", "--dev-bind", "/dev", "/dev",
                "--unshare-net", "--", *shell]
    return shell


def _scrub_env(directory: str, scratch: str, backend: str,
               extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {key: os.environ[key] for key in core._KEEP_ENV if key in os.environ}
    env["HOME"] = scratch
    env["TMPDIR"] = scratch
    env.setdefault("PATH", os.defpath)
    if backend in ("seatbelt", "bubblewrap", "inherited"):
        env[core._JAILED] = "1"
    if extra:
        env.update({str(k): str(v) for k, v in extra.items()})
    return env


def _kill_tree(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        process.kill()


def _run(argv: list[str], directory: str, env: dict[str, str],
         timeout: float) -> dict:
    start = time.monotonic()
    try:
        process = subprocess.Popen(argv, cwd=directory, env=env, text=True,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=True)
    except OSError as exc:
        return {"status": "environment", "error": str(exc), "seconds": time.monotonic()-start}
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


def gate_timeout(recipe: dict | None) -> float:
    """Use the declared timeout as the ceiling, including above the default."""
    declared = (recipe or {}).get("claim", {}).get("gate_timeout", core.GATE_TIMEOUT)
    try:
        limit = float(declared)
    except (TypeError, ValueError) as exc:
        raise core.ClaimError("gate_timeout must be a positive number") from exc
    if not math.isfinite(limit) or limit <= 0:
        raise core.ClaimError("gate_timeout must be a positive number")
    host = os.environ.get(core._ENV_TIMEOUT)
    if host:
        try:
            host_limit = float(host)
            if math.isfinite(host_limit) and host_limit > 0:
                limit = min(limit, host_limit)
        except ValueError:
            pass
    return limit


def run_gate(command: str, directory: os.PathLike[str] | str,
             recipe: dict | None, *, extra_env: dict[str, str] | None = None) -> dict:
    """Run one gate in the claim directory with a bounded, scrubbed host."""
    directory = os.path.abspath(os.fspath(directory))
    missing = preflight(recipe)
    backend = sandbox_backend()
    if missing:
        return {"status": "environment", "quarantine": backend,
                "missing": missing, "seconds": 0.0}
    store = os.path.join(directory, core.STORE)
    os.makedirs(store, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="gate-", dir=store) as scratch:
        env = _scrub_env(directory, scratch, backend, extra_env)
        result = _run(_sandbox_argv(command, directory, backend, scratch),
                      directory, env, gate_timeout(recipe))
    result["quarantine"] = backend
    return result


def _ledger_path(directory: os.PathLike[str] | str) -> str:
    return os.path.join(os.fspath(directory), core.LEDGER)


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
    totals = {}
    for event in ledger_events(directory):
        if not isinstance(event, dict):
            continue
        for key in core.COST_KEYS:
            value = event.get(key)
            if type(value) in (int, float) and math.isfinite(value):
                totals[key] = totals.get(key, 0) + value
    return totals or None


def _env_cache_dir() -> str:
    return os.environ.get(core._ENV_CACHE, os.path.join(Path.home(), ".cache", "reticuli", "envs"))


def furnish(directory: os.PathLike[str] | str, recipe: dict) -> str | None:
    """Prepare a hash-pinned Python environment and return its bin directory."""
    environment = recipe.get("claim", {}).get("environment")
    if not environment:
        return None
    from . import core as c
    import hashlib
    requirement = c._safe(directory, environment)
    digest = c._hash_file(requirement)
    name = hashlib.sha256(f"{digest}:{sys.executable}:{platform.platform()}".encode()).hexdigest()
    target = os.path.join(_env_cache_dir(), name)
    bin_dir = os.path.join(target, "Scripts" if os.name == "nt" else "bin")
    marker = os.path.join(target, ".furnished")
    if not os.path.isfile(marker):
        os.makedirs(os.path.dirname(target), exist_ok=True)
        venv.EnvBuilder(with_pip=True).create(target)
        pip = os.path.join(bin_dir, "pip")
        try:
            subprocess.run([pip, "install", "--require-hashes", "--only-binary=:all:",
                            "-r", requirement], check=True, timeout=core.FURNISH_TIMEOUT,
                           capture_output=True, text=True)
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise core.ClaimError(f"cannot furnish environment: {exc}") from exc
        Path(marker).write_text("ok\n", encoding="utf-8")
    return bin_dir


def independence(original: dict | None, rebuilt: dict | None) -> dict:
    a, b = original or {}, rebuilt or {}
    same = bool(a.get("vendor") and a.get("vendor") == b.get("vendor"))
    return {"established": not same and bool(b.get("vendor")),
            "same_vendor": same, "producer": b}


def _in_band(first: float, second: float, tolerance: float = core.TOLERANCE) -> bool:
    if first < 0 or second < 0 or tolerance < 1:
        return False
    if first == second == 0:
        return True
    if first == 0 or second == 0:
        return False
    return max(first / second, second / first) <= tolerance


def _independence_line(original: dict | None, rebuilt: dict | None) -> str:
    finding = independence(original, rebuilt)
    return "independence established" if finding["established"] else "independence unestablished"
