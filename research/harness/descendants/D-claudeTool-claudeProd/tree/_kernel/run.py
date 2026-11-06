"""Kernel run: confined gate execution, the host contract, and the ledger.

Every gate runs the same way whatever verb invoked it: a scrubbed
environment, a platform sandbox where the host has a functional one, a
wall-clock bound, and somewhere inside the claim it may actually write.
Sandboxes do not nest: given `RETICULI_JAILED` this layer inherits and says
so rather than re-applying one.
"""
import hashlib
import importlib.util
import json
import os
import shutil
import signal
import subprocess
import sys
import time

from .core import (ClaimError, COST_KEYS, COST_LADDER, FURNISH_TIMEOUT,
                   GATE_TIMEOUT, LEDGER, SCRATCH, STORE, _ENV_CACHE,
                   _ENV_TIMEOUT, _JAILED, _KEEP_ENV, _SHELL, _finite,
                   _is_number, _judging_host, _now, _safe)

#: Requirement operators, longest first so `>=` is never read as `>`.
_REQ_OPS = ("<=", ">=", "==", "!=", "~=", "<", ">")

#: Functional-probe cache for bubblewrap: None until measured.
_BWRAP_OK = None


# --------------------------------------------------------------------------
# the host sandbox

def _bwrap_usable() -> bool:
    """A present-but-nonfunctional sandbox counts as none, probed once."""
    global _BWRAP_OK
    if _BWRAP_OK is None:
        if not shutil.which("bwrap"):
            _BWRAP_OK = False
        else:
            try:
                probe = subprocess.run(
                    ["bwrap", "--ro-bind", "/", "/", "--unshare-net", "true"],
                    capture_output=True, check=False, timeout=30)
                _BWRAP_OK = probe.returncode == 0
            except (OSError, subprocess.SubprocessError):
                _BWRAP_OK = False
    return _BWRAP_OK


def sandbox_backend() -> str:
    """Which confinement this host applies -- or inherits, or lacks."""
    if os.environ.get(_JAILED):
        return "inherited"
    if sys.platform == "darwin" and shutil.which("sandbox-exec"):
        return "seatbelt"
    if _bwrap_usable():
        return "bubblewrap"
    return "none"


def _quote_sb(path: str) -> str:
    return path.replace("\\", "\\\\").replace('"', '\\"')


def _sandbox_argv(claim: str, backend: str) -> list:
    """The wrapper that confines a gate to its claim."""
    where = os.path.realpath(claim)
    if backend == "seatbelt":
        profile = ("(version 1)(allow default)(deny network*)"
                   "(deny file-write*)"
                   f'(allow file-write* (subpath "{_quote_sb(where)}")'
                   ' (subpath "/dev"))')
        return ["sandbox-exec", "-p", profile]
    if backend == "bubblewrap":
        return ["bwrap", "--ro-bind", "/", "/",
                "--dev-bind", "/dev", "/dev", "--proc", "/proc",
                "--bind", where, where,
                "--unshare-net", "--die-with-parent"]
    return []


def _scratch(claim: str) -> str:
    """A writable corner inside the claim's store: residue, never declared."""
    where = os.path.join(claim, SCRATCH)
    os.makedirs(where, exist_ok=True)
    return os.path.realpath(where)


def _scrub_env(claim: str, backend: str, extra: dict | None = None) -> dict:
    """A minimal host allowlist plus the claim's own variables.

    Inherited secrets never reach a gate. A confined gate needs a COHERENT
    environment, not merely a confined one, so TMPDIR and HOME point inside
    the claim where a real sandbox permits writes.
    """
    env = {name: os.environ[name] for name in _KEEP_ENV if name in os.environ}
    env.setdefault("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")
    env.setdefault("LANG", "C.UTF-8")
    scratch = _scratch(claim)
    env["TMPDIR"] = scratch
    env["HOME"] = scratch
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if backend in ("seatbelt", "bubblewrap"):
        env[_JAILED] = backend
    elif backend == "inherited":
        env[_JAILED] = os.environ.get(_JAILED, "inherited")
    else:
        env.pop(_JAILED, None)
    if extra:
        env.update({k: v for k, v in extra.items() if v is not None})
    return env


def _kill_tree(process) -> None:
    """The ceiling bounds the WORK, not the paperwork: the whole tree dies."""
    for sig in (signal.SIGKILL,):
        try:
            os.killpg(os.getpgid(process.pid), sig)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                process.kill()
            except (ProcessLookupError, OSError):
                pass
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass


def _run(command: str, cwd: str, env: dict, timeout: float,
         argv_prefix: list | None = None) -> dict:
    """One shell command, bounded, its whole process tree killable."""
    argv = list(argv_prefix or []) + [_SHELL, "-c", command]
    started = time.monotonic()
    try:
        process = subprocess.Popen(
            argv, cwd=cwd, env=env, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, start_new_session=True)
    except OSError as exc:
        return {"status": "failed", "code": 127, "stdout": "",
                "stderr": str(exc), "seconds": 0.0}
    try:
        out, err = process.communicate(timeout=timeout)
        status = "ok" if process.returncode == 0 else "failed"
        code = process.returncode
    except subprocess.TimeoutExpired:
        _kill_tree(process)
        try:
            out, err = process.communicate(timeout=10)
        except (subprocess.TimeoutExpired, ValueError):
            out, err = "", ""
        status, code = "timeout", -9
    return {"status": status, "code": code, "stdout": out or "",
            "stderr": err or "", "seconds": time.monotonic() - started}


def gate_timeout(parsed: dict | None) -> float:
    """A declared `gate_timeout` IS the ceiling, not a suggestion."""
    declared = ((parsed or {}).get("claim") or {}).get("gate_timeout")
    if declared is not None:
        return float(declared)
    from_env = os.environ.get(_ENV_TIMEOUT)
    if from_env:
        try:
            return float(from_env)
        except ValueError:
            pass
    return float(GATE_TIMEOUT)


def run_gate(command: str, claim: str, parsed: dict | None = None,
             env_extra: dict | None = None, path_prefix: str | None = None,
             strict: bool = True) -> dict:
    """One gate: scrubbed env, sandboxed where real, bounded."""
    backend = sandbox_backend() if strict else "none"
    env = _scrub_env(claim, backend, env_extra)
    if path_prefix:
        env["PATH"] = path_prefix + os.pathsep + env.get("PATH", "")
    prefix = _sandbox_argv(claim, backend) if strict else []
    outcome = _run(command, claim, env, gate_timeout(parsed), prefix)
    outcome["quarantine"] = backend
    outcome["command"] = command
    return outcome


def sandbox(command: str, claim: str, parsed: dict | None = None):
    """Functional probe: run a command confined, and name what confined it."""
    outcome = run_gate(command, claim, parsed)
    return outcome, outcome["quarantine"]


# --------------------------------------------------------------------------
# the environment contract

def _version_tuple(text: str) -> tuple:
    numbers = []
    for chunk in (text or "").replace("-", ".").split("."):
        digits = "".join(c for c in chunk if c.isdigit())
        if not digits:
            break
        numbers.append(int(digits))
    return tuple(numbers)


def _version_ok(have: tuple, operator: str, want: tuple) -> bool:
    if not have:
        return False
    width = max(len(have), len(want))
    left = tuple(list(have) + [0] * (width - len(have)))
    right = tuple(list(want) + [0] * (width - len(want)))
    if operator == "==":
        return left == right
    if operator == "!=":
        return left != right
    if operator == "<":
        return left < right
    if operator == "<=":
        return left <= right
    if operator == ">":
        return left > right
    if operator == ">=":
        return left >= right
    if operator == "~=":
        return left[:len(want) - 1] == right[:len(want) - 1] and left >= right
    return False


def _tool_version(name: str) -> tuple:
    if name in ("python", "python3"):
        return tuple(sys.version_info[:3])
    try:
        done = subprocess.run([name, "--version"], capture_output=True,
                              text=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return ()
    text = (done.stdout or "") + " " + (done.stderr or "")
    for token in text.split():
        numbers = _version_tuple(token)
        if numbers:
            return numbers
    return ()


def _have(name: str) -> bool:
    if name in ("python", "python3"):
        return True
    if shutil.which(name):
        return True
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError, ModuleNotFoundError):
        return False


def preflight(parsed: dict) -> list:
    """The environment contract: what the host does not provide."""
    missing = []
    for requirement in ((parsed.get("claim") or {}).get("requires") or []):
        if not isinstance(requirement, str) or not requirement.strip():
            continue
        text = requirement.strip()
        name, operator, want = text, None, None
        for candidate in _REQ_OPS:
            if candidate in text:
                head, _, tail = text.partition(candidate)
                name, operator, want = head.strip(), candidate, tail.strip()
                break
        if not _have(name):
            missing.append(requirement)
            continue
        if operator and want:
            if not _version_ok(_tool_version(name), operator,
                               _version_tuple(want)):
                missing.append(requirement)
    return missing


# --------------------------------------------------------------------------
# furnishing a room from a hash-pinned environment file

def _env_cache_dir() -> str:
    override = os.environ.get(_ENV_CACHE)
    if override:
        return override
    base = os.environ.get("XDG_CACHE_HOME") or \
        os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(base, "reticuli", "env")


def furnish(parsed: dict, room: str) -> dict:
    """Build a private venv from exactly the artifacts the file names.

    `--require-hashes`, so nothing unnamed can arrive; `--only-binary=:all:`,
    so nothing executes at install time. A room that cannot be furnished is
    an `environment` failure: nothing proven, nothing disproven.
    """
    declared = (parsed.get("claim") or {}).get("environment")
    if not declared:
        return {"ok": True, "path": None, "reason": None}
    lock = _safe(room, declared)
    if not os.path.isfile(lock):
        return {"ok": False, "path": None,
                "reason": f"environment file {declared!r} is missing"}
    with open(lock, "rb") as handle:
        digest = hashlib.sha256(handle.read()).hexdigest()
    key = hashlib.sha256(
        ("|".join([digest, sys.executable, sys.platform,
                   ".".join(str(n) for n in sys.version_info[:2])]))
        .encode("utf-8")).hexdigest()[:32]
    venv = os.path.join(_env_cache_dir(), key)
    bindir = os.path.join(venv, "bin")
    stamp = os.path.join(venv, ".furnished")
    if os.path.isfile(stamp):
        return {"ok": True, "path": bindir, "reason": None}
    shutil.rmtree(venv, ignore_errors=True)
    os.makedirs(os.path.dirname(venv) or ".", exist_ok=True)
    try:
        made = subprocess.run(
            [sys.executable, "-m", "venv", venv], capture_output=True,
            text=True, timeout=FURNISH_TIMEOUT, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "path": None, "reason": f"venv: {exc}"}
    if made.returncode != 0:
        shutil.rmtree(venv, ignore_errors=True)
        return {"ok": False, "path": None,
                "reason": (made.stderr or made.stdout)[-400:]}
    pip = os.path.join(bindir, "python")
    try:
        done = subprocess.run(
            [pip, "-m", "pip", "install", "--require-hashes",
             "--only-binary=:all:", "--disable-pip-version-check",
             "--no-input", "-r", os.path.abspath(lock)],
            cwd=room, capture_output=True, text=True,
            timeout=FURNISH_TIMEOUT, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        shutil.rmtree(venv, ignore_errors=True)
        return {"ok": False, "path": None, "reason": f"pip: {exc}"}
    if done.returncode != 0:
        shutil.rmtree(venv, ignore_errors=True)
        return {"ok": False, "path": None,
                "reason": (done.stderr or done.stdout)[-400:]}
    with open(stamp, "w", encoding="utf-8") as handle:
        handle.write(digest + "\n")
    return {"ok": True, "path": bindir, "reason": None}


# --------------------------------------------------------------------------
# the cost ledger

def _ledger_path(claim: str) -> str:
    return os.path.join(claim, LEDGER)


def ledger(claim: str, event: dict) -> dict:
    """Append one event. The ledger is residue: outside every root."""
    record = dict(event)
    record.setdefault("at", _now())
    path = _ledger_path(claim)
    os.makedirs(os.path.join(claim, STORE), exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return record


def ledger_events(claim: str) -> list:
    path = _ledger_path(claim)
    if not os.path.isfile(path):
        return []
    events = []
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if isinstance(event, dict):
                    events.append(event)
    except (OSError, UnicodeDecodeError):
        return []
    return events


def _total(events) -> dict | None:
    totals: dict = {}
    for event in events:
        for unit in COST_KEYS:
            value = event.get(unit)
            if not _finite(value):
                continue
            totals[unit] = totals.get(unit, 0) + value
    return totals or None


def cost(claim: str, scope: str | None = None) -> dict | None:
    """Ledger totals per unit, or None when nothing was measured.

    An unmeasured machine is reported, never guessed at: a key the ledger
    never names does not appear. Discovery-scoped events are totalled
    separately -- what a session cost to discover is not what a redo costs.
    """
    events = [e for e in ledger_events(claim)
              if (e.get("scope") or None) == scope]
    return _total(events)


def discovery(claim: str) -> dict | None:
    return cost(claim, scope="discovery")


def _in_band(left, right, tolerance: float) -> bool:
    """Comparability is the CLOSED band [1/tolerance, tolerance]."""
    if not _is_number(left) or not _is_number(right):
        return False
    if right == 0:
        return left == 0
    ratio = float(left) / float(right)
    return (1.0 / float(tolerance)) <= ratio <= float(tolerance)


def independence(claim: str) -> dict:
    """The redo's declared producer -- a declaration, never proof."""
    found = {}
    for event in ledger_events(claim):
        if event.get("event") == "producer":
            for key in ("vendor", "model", "blind", "cutoff"):
                if key in event:
                    found[key] = event[key]
    return found


def _independence_line(declared: dict | None) -> str:
    if declared and declared.get("vendor"):
        where = "blind workspace" if declared.get("blind") else \
            "workspace not blind"
        return (f"declared: {declared.get('vendor')}/"
                f"{declared.get('model')}, {where} "
                f"(a declaration, not proven)")
    return ("unestablished: content cannot prove blindness, and the ledger "
            "carries no producer declaration")
