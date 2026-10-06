"""Execute claim gates and account for the cost of producing their outputs.

The sandbox is selected by a functional probe.  A host without a working
sandbox is reported honestly rather than treating a binary's presence as
confinement.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import platform
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import venv

from . import core


_REQ_OPS = ("<=", ">=", "==", "!=", "~=", "<", ">")
_BWRAP_OK = None
_SEATBELT_OK = None


def _have(name: str) -> bool:
    return shutil.which(name) is not None


def _quote_sb(path: str) -> str:
    """Quote a path as a Seatbelt profile string."""
    return json.dumps(os.path.realpath(path))


def _seatbelt_profile(directory: str) -> str:
    room = _quote_sb(directory)
    return ("(version 1)\n"
            "(deny default)\n"
            "(allow process*)\n"
            "(allow file-read*)\n"
            f"(allow file-write* (subpath {room}) (subpath \"/dev\"))\n"
            "(deny network*)\n")


def _bwrap_usable() -> bool:
    global _BWRAP_OK
    if _BWRAP_OK is None:
        if not _have("bwrap"):
            _BWRAP_OK = False
        else:
            try:
                with tempfile.TemporaryDirectory() as room:
                    cmd = ["bwrap", "--die-with-parent", "--unshare-net",
                           "--ro-bind", "/", "/", "--bind", room, room,
                           "--dev-bind", "/dev", "/dev", "--chdir", room,
                           core._SHELL, "-c", "printf ok > test"]
                    done = subprocess.run(cmd, stdout=subprocess.DEVNULL,
                                          stderr=subprocess.DEVNULL, timeout=5)
                    _BWRAP_OK = done.returncode == 0 and os.path.isfile(os.path.join(room, "test"))
            except (OSError, subprocess.TimeoutExpired):
                _BWRAP_OK = False
    return bool(_BWRAP_OK)


def _seatbelt_usable() -> bool:
    global _SEATBELT_OK
    if _SEATBELT_OK is None:
        if not _have("sandbox-exec"):
            _SEATBELT_OK = False
        else:
            try:
                with tempfile.TemporaryDirectory() as room:
                    cmd = ["sandbox-exec", "-p", _seatbelt_profile(room),
                           core._SHELL, "-c",
                           "echo ok > test && echo ok > /dev/null && cat /etc/hosts > /dev/null"]
                    done = subprocess.run(cmd, cwd=room, stdout=subprocess.DEVNULL,
                                          stderr=subprocess.DEVNULL, timeout=5)
                    _SEATBELT_OK = done.returncode == 0 and os.path.isfile(os.path.join(room, "test"))
            except (OSError, subprocess.TimeoutExpired):
                _SEATBELT_OK = False
    return bool(_SEATBELT_OK)


def sandbox_backend() -> str:
    if os.environ.get(core._JAILED):
        return "inherited"
    if platform.system() == "Darwin" and _seatbelt_usable():
        return "seatbelt"
    if platform.system() == "Linux" and _bwrap_usable():
        return "bubblewrap"
    return "none"


def sandbox() -> dict[str, str]:
    return {"backend": sandbox_backend()}


def _sandbox_argv(command: str, directory: str, backend: str | None = None) -> list[str]:
    backend = backend or sandbox_backend()
    shell = [core._SHELL, "-c", command]
    if backend == "seatbelt":
        return ["sandbox-exec", "-p", _seatbelt_profile(directory), *shell]
    if backend == "bubblewrap":
        return ["bwrap", "--die-with-parent", "--unshare-net", "--ro-bind", "/", "/",
                "--bind", os.path.realpath(directory), os.path.realpath(directory),
                "--dev-bind", "/dev", "/dev", "--chdir", os.path.realpath(directory), *shell]
    return shell


def _scrub_env(directory: str | None = None, backend: str = "none",
               extra: dict | None = None) -> dict[str, str]:
    env = {key: os.environ[key] for key in core._KEEP_ENV if key in os.environ}
    env.setdefault("PATH", os.defpath)
    if directory is not None and backend in ("seatbelt", "bubblewrap"):
        scratch = os.path.join(os.path.realpath(directory), core.STORE, "tmp")
        os.makedirs(scratch, exist_ok=True)
        env["HOME"] = scratch
        env["TMPDIR"] = scratch
        env[core._JAILED] = "1"
    if extra:
        env.update({str(key): str(value) for key, value in extra.items()})
    return env


def gate_timeout(recipe: dict | None = None) -> float:
    claim = (recipe or {}).get("claim", {})
    value = claim.get("gate_timeout")
    if value is None:
        value = os.environ.get(core._ENV_TIMEOUT, core.GATE_TIMEOUT)
    try:
        value = float(value)
    except (TypeError, ValueError) as exc:
        raise core.ClaimError("gate timeout must be a positive number") from exc
    if not math.isfinite(value) or value <= 0:
        raise core.ClaimError("gate timeout must be a positive number")
    return value


def _kill_tree(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        try:
            process.kill()
        except OSError:
            pass


def _run(argv: list[str], directory: str, timeout: float,
         env: dict[str, str] | None = None) -> dict:
    start = time.monotonic()
    try:
        process = subprocess.Popen(argv, cwd=directory, env=env,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, start_new_session=True)
    except OSError as exc:
        return {"status": "environment", "detail": str(exc), "seconds": time.monotonic() - start}
    try:
        stdout, stderr = process.communicate(timeout=timeout)
        status = "ok" if process.returncode == 0 else "failed"
    except subprocess.TimeoutExpired:
        _kill_tree(process)
        stdout, stderr = process.communicate()
        status = "timeout"
    return {"status": status, "returncode": process.returncode,
            "stdout": stdout, "stderr": stderr, "seconds": time.monotonic() - start}


def run_gate(command: str, directory: str, recipe: dict | None = None,
             env: dict | None = None) -> dict:
    backend = sandbox_backend()
    result = _run(_sandbox_argv(command, directory, backend), directory,
                  gate_timeout(recipe), _scrub_env(directory, backend, env))
    result["quarantine"] = backend
    result["sandbox"] = backend
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
    except (OSError, ValueError) as exc:
        raise core.ClaimError(f"cannot read cost ledger: {exc}") from exc


def cost(directory: str) -> dict | None:
    totals = {}
    for event in ledger_events(directory):
        if event.get("kind") != "producer":
            continue
        for key in core.COST_KEYS:
            value = event.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                totals[key] = totals.get(key, 0) + value
    return totals or None


def _version_tuple(value: str) -> tuple[int, ...]:
    import re
    match = re.search(r"\d+(?:\.\d+)*", value)
    return tuple(int(part) for part in match.group().split(".")) if match else ()


def _version_ok(actual: str, requirement: str) -> bool:
    for op in _REQ_OPS:
        if requirement.startswith(op):
            wanted = _version_tuple(requirement[len(op):])
            got = _version_tuple(actual)
            if op == "==": return got == wanted
            if op == "!=": return got != wanted
            if op == ">=": return got >= wanted
            if op == "<=": return got <= wanted
            if op == ">": return got > wanted
            if op == "<": return got < wanted
            if op == "~=": return got >= wanted and got[:1] == wanted[:1]
    return bool(_version_tuple(actual))


def _tool_version(name: str) -> str | None:
    path = shutil.which(name)
    if path is None:
        return None
    try:
        result = subprocess.run([path, "--version"], capture_output=True,
                                text=True, timeout=5)
        return (result.stdout or result.stderr).strip().splitlines()[0]
    except (OSError, IndexError, subprocess.TimeoutExpired):
        return None


def preflight(recipe: dict) -> list[str]:
    missing = []
    for requirement in recipe.get("claim", {}).get("requires", []):
        if not isinstance(requirement, str):
            missing.append(str(requirement))
            continue
        name = requirement
        for op in _REQ_OPS:
            name = name.split(op, 1)[0]
        name = name.strip()
        if not _have(name) and importlib.util.find_spec(name) is None:
            missing.append(requirement)
    return missing


def _env_cache_dir() -> str:
    return os.environ.get(core._ENV_CACHE, os.path.join(os.path.expanduser("~"), ".cache", "reticuli", "env"))


def furnish(directory: str, recipe: dict) -> str | None:
    name = recipe.get("claim", {}).get("environment")
    if not name:
        return None
    source = core._safe(directory, name)
    key = hashlib.sha256((core._hash_file(source) + sys.executable + platform.platform()).encode()).hexdigest()
    target = os.path.join(_env_cache_dir(), key)
    python = os.path.join(target, "bin", "python")
    if not os.path.isfile(python):
        os.makedirs(target, exist_ok=True)
        venv.EnvBuilder(with_pip=True).create(target)
        try:
            subprocess.run([python, "-m", "pip", "install", "--require-hashes",
                            "--only-binary=:all:", "-r", source], check=True,
                           timeout=core.FURNISH_TIMEOUT, capture_output=True, text=True)
        except (OSError, subprocess.SubprocessError) as exc:
            raise core.ClaimError(f"cannot furnish environment: {exc}") from exc
    return os.path.join(target, "bin")


def _in_band(left: float, right: float, tolerance: float = core.TOLERANCE) -> bool:
    if left < 0 or right < 0:
        return False
    if left == 0 or right == 0:
        return left == right
    return max(left / right, right / left) <= tolerance


def _independence_line(original: dict | None, rebuilt: dict | None) -> str:
    original = original or {}
    rebuilt = rebuilt or {}
    if original.get("vendor") and rebuilt.get("vendor"):
        return "same vendor" if original["vendor"] == rebuilt["vendor"] else "different vendors"
    return "unestablished"


def independence(original: dict | None = None, rebuilt: dict | None = None) -> dict:
    line = _independence_line(original, rebuilt)
    return {"status": line, "established": line == "different vendors"}
