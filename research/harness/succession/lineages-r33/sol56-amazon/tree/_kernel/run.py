"""Confined gate execution and the private production-cost ledger.

Only the standard library is used.  Sandboxes are selected by functional
probes: an installed but unusable sandbox is honestly reported as ``none``.
"""
from __future__ import annotations

from collections.abc import Mapping
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
from typing import Any

from . import core

_REQ_OPS = ("<=", ">=", "==", "!=", "~=", "<", ">")
_BWRAP_OK: bool | None = None
_SEATBELT_OK: bool | None = None
_NUMBERS = re.compile(r"\d+")
_REQUIREMENT = re.compile(r"^\s*([^<>=!~\s]+)\s*(?:(<=|>=|==|!=|~=|<|>)\s*(\S+))?\s*$")


def _ledger_path(d: str | os.PathLike[str]) -> str:
    return core._safe(d, core.LEDGER)


def ledger(d: str | os.PathLike[str], event: Mapping[str, Any]) -> dict[str, Any]:
    """Append an event to the claim's JSON-lines ledger."""
    if not isinstance(event, Mapping):
        raise core.ClaimError("ledger event must be a mapping")
    item = dict(event)
    item.setdefault("when", core._now())
    try:
        store = core._safe(d, core.STORE)
        if os.path.lexists(store) and not os.path.isdir(store):
            raise core.ClaimError(f"claim store is not a directory: {core.STORE}")
        os.makedirs(store, exist_ok=True)
        with open(_ledger_path(d), "a", encoding="utf-8", newline="\n") as out:
            out.write(json.dumps(item, sort_keys=True, allow_nan=False) + "\n")
            out.flush()
    except core.ClaimError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise core.ClaimError(f"cannot append cost ledger: {exc}") from None
    return item


def ledger_events(d: str | os.PathLike[str]) -> list[dict[str, Any]]:
    """Read complete object entries from the ledger."""
    try:
        path = _ledger_path(d)
        if not os.path.exists(path):
            return []
        events = []
        with open(path, encoding="utf-8") as stream:
            for line in stream:
                try:
                    value = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue                 # tolerate a killed final append
                if isinstance(value, dict):
                    events.append(value)
        return events
    except core.ClaimError:
        raise
    except (OSError, UnicodeError) as exc:
        raise core.ClaimError(f"cannot read cost ledger: {exc}") from None


def cost(d: str | os.PathLike[str]) -> dict[str, int | float] | None:
    """Total measured production units, preserving absence as unmeasured."""
    totals: dict[str, int | float] = {}
    for event in ledger_events(d):
        if event.get("kind") in {"gate", "audit", "verification"}:
            continue
        usage = event.get("usage")
        sources = (event, usage) if isinstance(usage, Mapping) else (event,)
        for key in core.COST_KEYS:
            value = None
            for source in sources:
                if key in source:
                    value = source[key]
                    break
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            if value < 0 or not math.isfinite(float(value)):
                continue
            totals[key] = totals.get(key, 0) + value
    return totals or None


def _version_tuple(value: Any) -> tuple[int, ...]:
    return tuple(int(x) for x in _NUMBERS.findall(str(value)))


def _version_ok(actual: Any, requirement: Any, wanted: Any = None) -> bool:
    """Compare versions; accepts ``(actual, '>=3')`` or ``(actual, '>=', '3')``."""
    if wanted is None:
        text = str(requirement).strip()
        op = ""
        target = text
        for candidate in _REQ_OPS:
            if text.startswith(candidate):
                op, target = candidate, text[len(candidate):].strip()
                break
    else:
        op, target = str(requirement), str(wanted)
    a, b = _version_tuple(actual), _version_tuple(target)
    if not op:
        return bool(a)
    if not a or not b or op not in _REQ_OPS:
        return False
    width = max(len(a), len(b))
    left, right = a + (0,) * (width-len(a)), b + (0,) * (width-len(b))
    if op == "==": return left == right
    if op == "!=": return left != right
    if op == "<=": return left <= right
    if op == ">=": return left >= right
    if op == "<": return left < right
    if op == ">": return left > right
    prefix = b[:-1] if len(b) > 2 else b[:1]
    return left >= right and a[:len(prefix)] == prefix


def _tool_version(name: str) -> str | None:
    executable = shutil.which(name)
    if executable is None:
        return None
    for option in ("--version", "-V"):
        try:
            done = subprocess.run([executable, option], capture_output=True,
                                  text=True, timeout=5, check=False,
                                  env=_scrub_env())
        except (OSError, subprocess.SubprocessError):
            continue
        text = (done.stdout or done.stderr).strip()
        if text and _version_tuple(text):
            return text.splitlines()[0]
    return None


def _have(requirement: str) -> bool:
    if not isinstance(requirement, str):
        return False
    match = _REQUIREMENT.fullmatch(requirement)
    if match is None:
        return False
    name, op, wanted = match.groups()
    executable = shutil.which(name)
    module = False
    if executable is None:
        try:
            module = importlib.util.find_spec(name) is not None
        except (ImportError, AttributeError, ValueError):
            pass
    if executable is None and not module:
        return False
    if op is None:
        return True
    actual = _tool_version(name) if executable else None
    if actual is None and module:
        try:
            from importlib import metadata
            actual = metadata.version(name)
        except Exception:
            pass
    return actual is not None and _version_ok(actual, op, wanted)


def preflight(recipe: Mapping[str, Any] | None) -> list[str]:
    """Return missing binaries/modules declared by ``[claim] requires``."""
    if not isinstance(recipe, Mapping):
        return []
    claim = recipe.get("claim", {})
    required = claim.get("requires", []) if isinstance(claim, Mapping) else []
    return ([x for x in required if isinstance(x, str) and not _have(x)]
            if isinstance(required, list) else [])


def gate_timeout(recipe: Mapping[str, Any] | None = None) -> float:
    """Return the declared ceiling (or default), bounded by an explicit host cap."""
    declared = None
    if isinstance(recipe, Mapping):
        claim = recipe.get("claim", {})
        if isinstance(claim, Mapping):
            declared = claim.get("gate_timeout")
    good = (not isinstance(declared, bool) and isinstance(declared, (int, float))
            and math.isfinite(float(declared)) and declared > 0)
    result = float(declared if good else core.GATE_TIMEOUT)
    raw = os.environ.get(core._ENV_TIMEOUT)
    if raw:
        try:
            cap = float(raw)
            if math.isfinite(cap) and cap > 0:
                result = min(result, cap)
        except ValueError:
            pass
    return result


def _scrub_env(extra: Mapping[str, Any] | None = None,
               home: str | None = None) -> dict[str, str]:
    """Build a small environment without inherited credentials."""
    env = {key: os.environ[key] for key in core._KEEP_ENV if key in os.environ}
    env.setdefault("PATH", os.defpath)
    env.setdefault("LANG", "C.UTF-8")
    protocol = {value for key, value in vars(core).items()
                if key.startswith("_ENV_") and isinstance(value, str)}
    for key in protocol:
        if key in os.environ:
            env[key] = os.environ[key]
    if home is not None:
        env["HOME"] = env["TMPDIR"] = home
    if extra:
        for key, value in extra.items():
            if isinstance(key, str) and value is not None:
                env[key] = str(value)
    return env


def _quote_sb(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _seatbelt_profile(room: str) -> str:
    # A deny with a negative filter closes writes everywhere except the room
    # and device sinks.  Allow-default preserves real host reads, spawning,
    # uname/sysctl, and user-database mach lookups.
    allowed = "(require-any (subpath %s) (subpath \"/dev\"))" % _quote_sb(room)
    return " ".join(("(version 1)", "(allow default)", "(deny network*)",
                     "(deny file-write* (require-not %s))" % allowed))


def _bwrap_usable() -> bool:
    global _BWRAP_OK
    if _BWRAP_OK is not None:
        return _BWRAP_OK
    executable = shutil.which("bwrap")
    if executable is None or not sys.platform.startswith("linux"):
        _BWRAP_OK = False
        return False
    room = tempfile.mkdtemp(prefix="reticuli-bwrap-probe-")
    try:
        argv = [executable, "--die-with-parent", "--unshare-net",
                "--ro-bind", "/", "/", "--bind", room, room,
                "--dev", "/dev", "--proc", "/proc", "--chdir", room,
                "/bin/sh", "-c", "printf x > ok && test -r /etc/hosts && printf x >/dev/null"]
        done = subprocess.run(argv, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=8,
                              check=False, env=_scrub_env())
        _BWRAP_OK = done.returncode == 0 and os.path.isfile(os.path.join(room, "ok"))
    except (OSError, subprocess.SubprocessError):
        _BWRAP_OK = False
    finally:
        shutil.rmtree(room, ignore_errors=True)
    return bool(_BWRAP_OK)


def _seatbelt_usable() -> bool:
    global _SEATBELT_OK
    if _SEATBELT_OK is not None:
        return _SEATBELT_OK
    executable = shutil.which("sandbox-exec")
    if executable is None or sys.platform != "darwin":
        _SEATBELT_OK = False
        return False
    room = tempfile.mkdtemp(prefix="reticuli-seatbelt-probe-")
    try:
        done = subprocess.run([executable, "-p", _seatbelt_profile(room),
                               "/bin/sh", "-c",
                               "printf x > ok && test -r /etc/hosts && printf x >/dev/null"],
                              cwd=room, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=8,
                              check=False, env=_scrub_env(home=room))
        _SEATBELT_OK = done.returncode == 0 and os.path.isfile(os.path.join(room, "ok"))
    except (OSError, subprocess.SubprocessError):
        _SEATBELT_OK = False
    finally:
        shutil.rmtree(room, ignore_errors=True)
    return bool(_SEATBELT_OK)


def sandbox_backend() -> str:
    if os.environ.get(core._JAILED):
        return "inherited"
    if _bwrap_usable():
        return "bubblewrap"
    if _seatbelt_usable():
        return "seatbelt"
    return "none"


def sandbox() -> dict[str, str]:
    return {"backend": sandbox_backend()}


def _sandbox_argv(command: str, d: str | os.PathLike[str], scratch: str,
                  backend: str | None = None) -> list[str]:
    backend = backend or sandbox_backend()
    room = os.path.abspath(os.fspath(d))
    shell = core._SHELL if os.path.isabs(core._SHELL) and os.path.exists(core._SHELL) else "/bin/sh"
    if backend == "bubblewrap":
        return [shutil.which("bwrap") or "bwrap", "--die-with-parent",
                "--unshare-net", "--ro-bind", "/", "/", "--bind", room, room,
                "--dev", "/dev", "--proc", "/proc", "--chdir", room,
                "--setenv", "HOME", scratch, "--setenv", "TMPDIR", scratch,
                "--setenv", core._JAILED, "1", "--", shell, "-c", command]
    if backend == "seatbelt":
        return [shutil.which("sandbox-exec") or "sandbox-exec", "-p",
                _seatbelt_profile(room), shell, "-c", command]
    return [shell, "-c", command]


def _kill_tree(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    except OSError:
        try: process.kill()
        except OSError: pass


def _run(argv: list[str], *, cwd: str | os.PathLike[str] | None = None,
         env: Mapping[str, str] | None = None,
         timeout: float | None = None) -> dict[str, Any]:
    started = time.monotonic()
    try:
        process = subprocess.Popen(argv, cwd=cwd, env=dict(env) if env else None,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, start_new_session=(os.name == "posix"))
    except OSError as exc:
        return {"status": "failed", "returncode": None, "stdout": "",
                "stderr": str(exc), "seconds": time.monotonic()-started}
    try:
        stdout, stderr = process.communicate(timeout=timeout)
        status = "ok" if process.returncode == 0 else "failed"
    except subprocess.TimeoutExpired:
        _kill_tree(process)
        stdout, stderr = process.communicate()
        status = "timeout"
    return {"status": status, "returncode": process.returncode,
            "stdout": stdout, "stderr": stderr,
            "seconds": time.monotonic()-started}


def _env_cache_dir() -> str:
    configured = os.environ.get(core._ENV_CACHE)
    if configured:
        root = os.path.abspath(os.path.expanduser(configured))
    elif sys.platform == "darwin":
        root = os.path.expanduser("~/Library/Caches/reticuli/environments")
    else:
        root = os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")),
                            "reticuli", "environments")
    os.makedirs(root, exist_ok=True)
    return root


def furnish(d: str | os.PathLike[str], recipe: Mapping[str, Any] | None = None) -> str | None:
    """Build/reuse a wheels-only, hash-checked private venv when declared."""
    if isinstance(d, Mapping) and recipe is not None and not isinstance(recipe, Mapping):
        d, recipe = recipe, d
    if not isinstance(recipe, Mapping):
        return None
    claim = recipe.get("claim", {})
    name = claim.get("environment") if isinstance(claim, Mapping) else None
    if not isinstance(name, str) or not name:
        return None
    try:
        requirements = core._safe(d, name)
        tag = [core._hash_file(requirements), sys.executable, sys.version,
               platform.system(), platform.machine()]
        key = hashlib.sha256(json.dumps(tag).encode()).hexdigest()
        target = os.path.join(_env_cache_dir(), key)
        marker = os.path.join(target, ".reticuli-ready")
        if os.path.isfile(marker):
            return target
        shutil.rmtree(target, ignore_errors=True)
        venv.EnvBuilder(with_pip=True, clear=True).create(target)
        bindir = "Scripts" if os.name == "nt" else "bin"
        python = os.path.join(target, bindir, "python.exe" if os.name == "nt" else "python")
        done = subprocess.run([python, "-m", "pip", "install", "--require-hashes",
                               "--only-binary=:all:", "-r", requirements],
                              capture_output=True, text=True, check=False,
                              timeout=float(core.FURNISH_TIMEOUT), env=_scrub_env())
        if done.returncode:
            shutil.rmtree(target, ignore_errors=True)
            raise core.ClaimError("cannot furnish claim environment: " +
                                  (done.stderr or done.stdout).strip()[-1000:])
        with open(marker, "w", encoding="utf-8") as out: out.write("ready\n")
        return target
    except core.ClaimError:
        raise
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise core.ClaimError(f"cannot furnish claim environment: {exc}") from None


def run_gate(command: str, d: str | os.PathLike[str],
             recipe: Mapping[str, Any] | None = None,
             env: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Run one scrubbed, bounded, and where possible sandboxed gate."""
    backend = sandbox_backend()
    missing = preflight(recipe)
    if missing:
        return {"status": "environment", "quarantine": backend, "missing": missing,
                "stdout": "", "stderr": "missing requirements: " + ", ".join(missing),
                "returncode": None, "seconds": 0.0}
    room, scratch = os.path.abspath(os.fspath(d)), ""
    try:
        os.makedirs(room, exist_ok=True)
        store = core._safe(room, core.STORE)
        os.makedirs(store, exist_ok=True)
        scratch = tempfile.mkdtemp(prefix="gate-", dir=store)
        gate_env = _scrub_env(env, scratch if backend in {"bubblewrap", "seatbelt"} else None)
        try:
            furnished = furnish(room, recipe)
        except core.ClaimError as exc:
            return {"status": "environment", "quarantine": backend, "stdout": "",
                    "stderr": str(exc), "returncode": None, "seconds": 0.0}
        if furnished:
            bindir = os.path.join(furnished, "Scripts" if os.name == "nt" else "bin")
            gate_env["PATH"] = bindir + os.pathsep + gate_env["PATH"]
            gate_env["VIRTUAL_ENV"] = furnished
        result = _run(_sandbox_argv(command, room, scratch, backend), cwd=room,
                      env=gate_env, timeout=gate_timeout(recipe))
        result["quarantine"] = backend
        return result
    except (OSError, TypeError, ValueError, core.ClaimError) as exc:
        return {"status": "failed", "quarantine": backend, "stdout": "",
                "stderr": str(exc), "returncode": None, "seconds": 0.0}
    finally:
        if scratch: shutil.rmtree(scratch, ignore_errors=True)


def _in_band(value: float, lower: float = 1.5, upper: float = 4.0) -> bool:
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(float(value)) and lower <= value < upper)


def _independence_line(value: Mapping[str, Any] | None) -> str:
    if not isinstance(value, Mapping):
        return "independence unestablished"
    fields = [str(value[k]) for k in ("vendor", "model") if value.get(k)]
    if value.get("blind") is True: fields.append("blind")
    return "/".join(fields) if fields else "independence unestablished"


def independence(original: Mapping[str, Any] | None,
                 rebuild: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Report producer independence as an observation, never an enforcement."""
    if rebuild is None:
        rebuild, original = original, None
    established = isinstance(rebuild, Mapping) and rebuild.get("blind") is True
    if isinstance(original, Mapping) and isinstance(rebuild, Mapping):
        for key in ("vendor", "model"):
            if original.get(key) and original.get(key) == rebuild.get(key):
                established = False
    return {"established": established, "declaration": _independence_line(rebuild)}


ClaimError = core.ClaimError
__all__ = ["ClaimError", "cost", "furnish", "gate_timeout", "independence",
           "ledger", "ledger_events", "preflight", "run_gate", "sandbox",
           "sandbox_backend"]
