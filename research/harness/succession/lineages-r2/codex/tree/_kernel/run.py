"""Execute claim gates and account for their measured production costs."""

from __future__ import annotations

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
from pathlib import Path

from . import core


_REQ_OPS = ('<=', '>=', '==', '!=', '~=', '<', '>')
_BWRAP_OK = None


def _have(name: str) -> bool:
    return shutil.which(name) is not None


def _version_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", version))


def _tool_version(name: str) -> tuple[int, ...] | None:
    if not _have(name):
        return None
    try:
        done = subprocess.run([name, "--version"], capture_output=True, text=True,
                              timeout=5, check=False)
        return _version_tuple(done.stdout or done.stderr)
    except (OSError, subprocess.TimeoutExpired):
        return None


def _version_ok(actual: tuple[int, ...], requirement: str) -> bool:
    match = re.fullmatch(r"\s*(<=|>=|==|!=|~=|<|>)\s*([\d.]+)\s*", requirement)
    if match is None:
        return False
    op, wanted = match.groups()
    target = _version_tuple(wanted)
    left = actual + (0,) * max(0, len(target) - len(actual))
    right = target + (0,) * max(0, len(actual) - len(target))
    if op == "~=":
        upper = (target[0] + 1,) if len(target) < 2 else target[:-2] + (target[-2] + 1,)
        return left >= right and actual < upper
    return {"<": left < right, "<=": left <= right, ">": left > right,
            ">=": left >= right, "==": left == right, "!=": left != right}[op]


def preflight(recipe: dict) -> list[str]:
    """List declared host requirements that cannot be found."""
    import importlib.util

    missing = []
    for item in recipe.get("claim", {}).get("requires", []):
        if not isinstance(item, str) or not item:
            missing.append(str(item))
            continue
        name = re.split(r"[<>=!~]", item, maxsplit=1)[0].strip()
        found = _have(name) or importlib.util.find_spec(name.replace("-", "_")) is not None
        if not found:
            missing.append(item)
    return missing


def gate_timeout(recipe: dict | None = None) -> float:
    """Apply the host ceiling to the claim's declared gate timeout."""
    declared = (recipe or {}).get("claim", {}).get("gate_timeout", core.GATE_TIMEOUT)
    try:
        declared = float(declared)
    except (TypeError, ValueError):
        declared = core.GATE_TIMEOUT
    if declared <= 0:
        declared = core.GATE_TIMEOUT
    try:
        ceiling = float(os.environ.get(core._ENV_TIMEOUT, core.GATE_TIMEOUT))
    except ValueError:
        ceiling = core.GATE_TIMEOUT
    return min(declared, ceiling if ceiling > 0 else core.GATE_TIMEOUT)


def _bwrap_usable() -> bool:
    global _BWRAP_OK
    if _BWRAP_OK is None:
        if not _have("bwrap"):
            _BWRAP_OK = False
        else:
            try:
                probe = subprocess.run(
                    ["bwrap", "--ro-bind", "/", "/", "--proc", "/proc",
                     "--dev-bind", "/dev", "/dev", "--unshare-net", "/bin/sh", "-c", "true"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5, check=False)
                _BWRAP_OK = probe.returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                _BWRAP_OK = False
    return _BWRAP_OK


def _quote_sb(path: str) -> str:
    return '"' + path.replace('\\', '\\\\').replace('"', '\\"') + '"'


def sandbox_backend() -> str:
    if os.environ.get(core._JAILED):
        return "inherited"
    if sys.platform == "darwin" and _have("sandbox-exec"):
        try:
            probe = subprocess.run(["sandbox-exec", "-p", "(version 1) (allow default)",
                                    "/bin/sh", "-c", "true"], capture_output=True,
                                   timeout=5, check=False)
            if probe.returncode == 0:
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
    if backend == "bubblewrap":
        return ["bwrap", "--ro-bind", "/", "/", "--bind", directory, directory,
                "--proc", "/proc", "--dev-bind", "/dev", "/dev", "--unshare-net",
                "--chdir", directory, *shell]
    if backend == "seatbelt":
        profile = ("(version 1) (deny default) (allow process*) "
                   "(allow file-read*) "
                   f"(allow file-write* (subpath {_quote_sb(directory)}))")
        return ["sandbox-exec", "-p", profile, *shell]
    return shell


def _scrub_env(directory: str, extra: dict | None = None) -> dict[str, str]:
    allowed = {key: value for key, value in os.environ.items()
               if key in core._KEEP_ENV or key.startswith("RETICULI_")}
    allowed.setdefault("PATH", os.defpath)
    allowed.setdefault("LANG", "C")
    if extra:
        allowed.update({str(key): str(value) for key, value in extra.items()})
    return allowed


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
    except OSError as exc:
        return {"status": "environment", "stdout": "", "stderr": str(exc),
                "returncode": None, "seconds": time.monotonic() - started}
    try:
        stdout, stderr = process.communicate(timeout=timeout)
        status = "ok" if process.returncode == 0 else "failed"
    except subprocess.TimeoutExpired:
        _kill_tree(process)
        stdout, stderr = process.communicate()
        status = "timeout"
    return {"status": status, "stdout": stdout, "stderr": stderr,
            "returncode": process.returncode, "seconds": time.monotonic() - started}


def run_gate(command: str, directory: os.PathLike[str] | str,
             recipe: dict | None = None, *, timeout: float | None = None,
             env: dict | None = None) -> dict:
    """Run one shell gate in its claim directory with a bounded, scrubbed host."""
    location = os.path.realpath(directory)
    backend = sandbox_backend()
    environment = _scrub_env(location, env)
    if backend in ("seatbelt", "bubblewrap"):
        scratch = os.path.join(location, core.STORE, "tmp")
        os.makedirs(scratch, exist_ok=True)
        environment.update({"HOME": scratch, "TMPDIR": scratch, core._JAILED: "1"})
    result = _run(_sandbox_argv(command, location, backend), location, environment,
                  gate_timeout(recipe) if timeout is None else min(float(timeout), gate_timeout(recipe)))
    result["quarantine"] = backend
    return result


def _ledger_path(directory: os.PathLike[str] | str) -> str:
    return core._safe(directory, core.LEDGER)


def ledger(directory: os.PathLike[str] | str, event: dict) -> None:
    """Append one JSON event to the claim's local cost ledger."""
    path = _ledger_path(directory)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, sort_keys=True) + "\n")


def ledger_events(directory: os.PathLike[str] | str) -> list[dict]:
    path = _ledger_path(directory)
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as stream:
            return [json.loads(line) for line in stream if line.strip()]
    except (OSError, ValueError) as exc:
        raise core.ClaimError(f"cannot read ledger {path}: {exc}") from exc


def cost(directory: os.PathLike[str] | str) -> dict | None:
    totals = {}
    for event in ledger_events(directory):
        if event.get("kind") != "producer":
            continue
        for unit in core.COST_KEYS:
            value = event.get(unit)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
                totals[unit] = totals.get(unit, 0) + value
    return totals or None


def _in_band(value: float, reference: float, tolerance: float = core.TOLERANCE) -> bool:
    return reference / tolerance <= value <= reference * tolerance


def _independence_line(original: dict | None, rebuild: dict | None) -> str:
    if not original or not rebuild:
        return "unestablished"
    if original.get("vendor") == rebuild.get("vendor"):
        return "same vendor"
    return "declared independent"


def independence(original: dict | None, rebuild: dict | None) -> dict:
    return {"status": _independence_line(original, rebuild)}


def _env_cache_dir() -> str:
    return os.environ.get(core._ENV_CACHE, os.path.join(tempfile.gettempdir(), "reticuli-envs"))


def furnish(directory: os.PathLike[str] | str, recipe: dict | None = None) -> str | None:
    """Install a declared, hash-pinned Python environment into a private cache."""
    from . import recipe as recipe_module
    import hashlib

    parsed = recipe if recipe is not None else recipe_module.load_recipe(directory)
    name = parsed.get("claim", {}).get("environment")
    if not name:
        return None
    source = core._safe(directory, name)
    digest = core._hash_file(source)
    cache_key = hashlib.sha256((digest + sys.executable + platform.platform()).encode()).hexdigest()
    target = os.path.join(_env_cache_dir(), cache_key)
    python = os.path.join(target, "bin", "python")
    if os.path.isfile(python):
        return os.path.join(target, "bin")
    import venv
    os.makedirs(os.path.dirname(target), exist_ok=True)
    try:
        venv.EnvBuilder(with_pip=True).create(target)
        subprocess.run([python, "-m", "pip", "install", "--require-hashes",
                        "--only-binary=:all:", "-r", source], check=True,
                       timeout=core.FURNISH_TIMEOUT, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        shutil.rmtree(target, ignore_errors=True)
        raise core.ClaimError(f"cannot furnish environment: {exc}") from exc
    return os.path.join(target, "bin")
