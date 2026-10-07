"""Gate execution: scrubbed env, sandboxed, bounded; and the cost ledger.

`run_gate` runs one gate command under a platform sandbox (macOS
`sandbox-exec`, Linux `bwrap`, or `none`/`inherited` when no confinement
applies), with a scrubbed environment and a wall-clock bound, and reports
its status and which quarantine actually applied. `ledger` appends a cost
event for a claim directory; `ledger_events` reads them back; `cost` totals
them per unit. `gate_timeout` resolves the effective per-gate bound: the
claim's own declaration is the ceiling, overridable downward only by an
explicit host ceiling (`RETICULI_GATE_TIMEOUT`), never by an implementation
default.

`preflight` checks the claim's `requires` contract against the host.
`furnish` builds a private, hash-pinned venv for a claim's `environment`.
`independence` reports declared producer independence between two legs of a
crosscheck (an observation, never enforced).

Stdlib only, never the network (furnishing is the one deliberate exception,
and only when a caller actually invokes it).
"""
import importlib.util
import json
import operator
import os
import platform
import re
import shutil
import signal
import subprocess
import sys

from .core import (
    ClaimError,
    FURNISH_TIMEOUT,
    GATE_TIMEOUT,
    LEDGER,
    STORE,
    _ENV_CACHE,
    _ENV_TIMEOUT,
    _JAILED,
    _KEEP_ENV,
    _SHELL,
    _hash_file,
    _safe,
)

SANDBOXES = {"none", "seatbelt", "bubblewrap", "inherited"}

COST_KEYS = ("usd", "tokens", "calls", "seconds")

# version-requirement operators a `requires` entry may use, longest first so
# a prefix match never swallows a longer operator (`<=` before `<`).
_REQ_OPS = ("<=", ">=", "==", "!=", "~=", "<", ">")
_OPS_BY_LENGTH = tuple(sorted(_REQ_OPS, key=len, reverse=True))
_OPS_FUNCS = {
    "<=": operator.le, ">=": operator.ge, "==": operator.eq,
    "!=": operator.ne, "<": operator.lt, ">": operator.gt,
}

# cached functional probe of bubblewrap; None means "not yet probed".
_BWRAP_OK = None
_SEATBELT_OK = None


# ---- the cost ledger -------------------------------------------------------

def _ledger_path(d: str) -> str:
    return os.path.join(d, LEDGER)


def ledger(d: str, event: dict) -> None:
    """Append one cost event to the claim directory's ledger."""
    path = _ledger_path(d)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, sort_keys=True) + "\n")


def ledger_events(d: str) -> list:
    """Every event appended to the claim directory's ledger, in order."""
    path = _ledger_path(d)
    if not os.path.isfile(path):
        return []
    events = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def cost(d: str) -> dict:
    """Ledger totals per unit (usd/tokens/calls/seconds).

    Totals carry only the keys the ledger actually names -- an unmeasured
    unit is never guessed at as zero. `None` if nothing was measured.
    """
    totals = {}
    for event in ledger_events(d):
        for key in COST_KEYS:
            value = event.get(key)
            if value is not None and not isinstance(value, bool):
                totals[key] = totals.get(key, 0) + value
    return totals or None


# ---- the declared timeout is the ceiling, in both directions --------------

def gate_timeout(recipe) -> float:
    """The effective per-gate wall-clock bound.

    A claim's own `[claim] gate_timeout` IS the ceiling: it may raise the
    bound past any implementation default. An explicit host ceiling
    (`RETICULI_GATE_TIMEOUT`) may still lower it -- that is an operator's
    deliberate override, not an implementation default smuggled back in.
    """
    claim = recipe.get("claim", {}) if isinstance(recipe, dict) else {}
    declared = claim.get("gate_timeout")
    bound = float(declared) if declared is not None else GATE_TIMEOUT
    host_cap = os.environ.get(_ENV_TIMEOUT)
    if host_cap:
        try:
            bound = min(bound, float(host_cap))
        except ValueError:
            pass
    return bound


# ---- the scrubbed environment ---------------------------------------------

def _scrub_env() -> dict:
    """A minimal host allowlist: inherited secrets never reach a gate."""
    return {k: os.environ[k] for k in _KEEP_ENV if k in os.environ}


def _scratch_dir(workdir: str) -> str:
    """Scratch space inside the room: where a real sandbox applies, the
    gate's TMPDIR/HOME point here rather than at the host's own -- residue,
    never a declared file."""
    path = os.path.join(workdir, STORE, "room")
    os.makedirs(path, exist_ok=True)
    return path


# ---- the sandbox ------------------------------------------------------------

def _have(name: str) -> bool:
    """Is `name` available on this host -- a binary on PATH or a Python
    module importable by this interpreter?"""
    if shutil.which(name):
        return True
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _bwrap_usable() -> bool:
    """Functional probe of bubblewrap: present but broken counts as none."""
    global _BWRAP_OK
    if _BWRAP_OK is not None:
        return _BWRAP_OK
    if not shutil.which("bwrap"):
        _BWRAP_OK = False
        return False
    try:
        proc = subprocess.run(
            ["bwrap", "--ro-bind", "/", "/", "--unshare-all", "--", "true"],
            capture_output=True, timeout=5,
        )
        _BWRAP_OK = proc.returncode == 0
    except OSError:
        _BWRAP_OK = False
    except subprocess.TimeoutExpired:
        _BWRAP_OK = False
    return _BWRAP_OK


def _seatbelt_usable() -> bool:
    """Functional probe of macOS sandbox-exec: present but broken counts as
    none, honestly reported."""
    global _SEATBELT_OK
    if _SEATBELT_OK is not None:
        return _SEATBELT_OK
    if not shutil.which("sandbox-exec"):
        _SEATBELT_OK = False
        return False
    try:
        proc = subprocess.run(
            ["sandbox-exec", "-p", "(version 1)(allow default)", "true"],
            capture_output=True, timeout=5,
        )
        _SEATBELT_OK = proc.returncode == 0
    except OSError:
        _SEATBELT_OK = False
    except subprocess.TimeoutExpired:
        _SEATBELT_OK = False
    return _SEATBELT_OK


def sandbox_backend() -> str:
    """Which quarantine applies here: `inherited` when already jailed (the
    kernel never nests sandboxes), else a functional probe of the host."""
    if os.environ.get(_JAILED):
        return "inherited"
    if sys.platform == "darwin" and _seatbelt_usable():
        return "seatbelt"
    if sys.platform.startswith("linux") and _bwrap_usable():
        return "bubblewrap"
    return "none"


def sandbox() -> dict:
    """A functional probe of the host sandbox, beyond just its backend name."""
    backend = sandbox_backend()
    return {"backend": backend, "functional": backend not in ("none",)}


def _quote_sb(s: str) -> str:
    """Escape a string for embedding in a seatbelt (Scheme-like) profile."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _seatbelt_profile(room: str) -> str:
    room_q = _quote_sb(room)
    return "\n".join([
        "(version 1)",
        "(deny default)",
        "(allow file-read*)",
        f'(allow file-write* (subpath "{room_q}"))',
        '(allow file-write-data (literal "/dev/null"))',
        "(allow process-fork)",
        "(allow process-exec)",
        "(allow signal (target same-sandbox))",
        "(allow sysctl-read)",
        "(allow mach-lookup)",
        "(allow iokit-open)",
        "",
    ])


def _sandbox_argv(backend: str, room: str, scratch: str, cmd: str) -> list:
    """Wrap `cmd` (a shell command) for the given quarantine backend."""
    if backend in ("none", "inherited"):
        return [_SHELL, "-c", cmd]
    if backend == "seatbelt":
        profile = _seatbelt_profile(room)
        return ["sandbox-exec", "-p", profile, _SHELL, "-c", cmd]
    if backend == "bubblewrap":
        return [
            "bwrap",
            "--ro-bind", "/", "/",
            "--dev", "/dev",
            "--proc", "/proc",
            "--bind", room, room,
            "--unshare-net",
            "--die-with-parent",
            "--",
            _SHELL, "-c", cmd,
        ]
    raise ClaimError(f"unknown sandbox backend: {backend!r}")


# ---- running one gate -------------------------------------------------------

def _kill_tree(proc) -> None:
    """Kill a confined gate's whole process tree, not just its direct
    child -- a sandboxed command is itself wrapped by at least one process."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
        except OSError:
            pass
    try:
        proc.wait(timeout=5)
    except Exception:
        pass


def _run(argv: list, cwd: str, env: dict, timeout: float):
    """Run `argv`, in its own process group so a timeout can kill the tree."""
    proc = subprocess.Popen(
        argv, cwd=cwd, env=env, start_new_session=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    try:
        proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        raise
    return proc


def run_gate(cmd: str, workdir: str, recipe=None) -> dict:
    """Run one gate command under the host's quarantine: scrubbed
    environment, sandboxed, bounded by `gate_timeout`.

    Returns `{"status": ..., "quarantine": ...}` -- status one of `ok`,
    `failed`, `timeout`; quarantine the backend that actually applied.
    """
    backend = sandbox_backend()
    timeout = gate_timeout(recipe)
    room = os.path.realpath(workdir)
    scratch = _scratch_dir(room)

    env = _scrub_env()
    env["TMPDIR"] = scratch
    env["HOME"] = scratch
    if backend != "none":
        env[_JAILED] = "1"

    argv = _sandbox_argv(backend, room, scratch, cmd)
    try:
        proc = _run(argv, cwd=room, env=env, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "quarantine": backend}

    status = "ok" if proc.returncode == 0 else "failed"
    return {"status": status, "quarantine": backend}


# ---- the environment contract: `requires` ----------------------------------

def _version_tuple(v: str) -> tuple:
    parts = re.findall(r"\d+", v)
    return tuple(int(p) for p in parts) if parts else (0,)


def _tool_version(name: str) -> str:
    try:
        proc = subprocess.run(
            [name, "--version"], capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return (proc.stdout or proc.stderr or "").strip()


def _version_ok(current: str, requirement: str) -> bool:
    """Does version string `current` satisfy a requirement like `>=1.2.3`?"""
    requirement = requirement.strip()
    for op in _OPS_BY_LENGTH:
        if requirement.startswith(op):
            target = requirement[len(op):].strip()
            cur_t = _version_tuple(current)
            tgt_t = _version_tuple(target)
            if op == "~=":
                if len(tgt_t) < 2:
                    return cur_t == tgt_t
                return cur_t[:-1] == tgt_t[:-1] and cur_t >= tgt_t
            return _OPS_FUNCS[op](cur_t, tgt_t)
    return _version_tuple(current) == _version_tuple(requirement)


def preflight(recipe: dict) -> list:
    """The claim's `requires` the host does not satisfy -- empty means the
    environment contract holds."""
    claim = recipe.get("claim", {}) if isinstance(recipe, dict) else {}
    requires = claim.get("requires") or []
    missing = []
    for req in requires:
        name, version_req = req, None
        for op in _OPS_BY_LENGTH:
            if op in req:
                name, _, rest = req.partition(op)
                name = name.strip()
                version_req = op + rest.strip()
                break
        if not _have(name):
            missing.append(req)
            continue
        if version_req is not None:
            current = _tool_version(name)
            if not current or not _version_ok(current, version_req):
                missing.append(req)
    return missing


# ---- the environment: a hash-pinned venv -----------------------------------

def _env_cache_dir() -> str:
    override = os.environ.get(_ENV_CACHE)
    if override:
        return override
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(
        os.path.expanduser("~"), ".cache")
    return os.path.join(base, "reticuli", "envs")


def _in_band(action: str, exc: Exception) -> ClaimError:
    """Wrap a raw exception as a refusal with a reason, never a bare
    traceback -- the claim's own declarations are untrusted input too."""
    return ClaimError(f"{action}: {exc}")


def furnish(d: str, recipe: dict) -> str:
    """Build (or reuse, from cache) a private venv from the claim's
    hash-pinned `[claim] environment` file. Returns the venv directory, or
    `None` when the claim declares no environment."""
    claim = recipe.get("claim", {}) if isinstance(recipe, dict) else {}
    env_file = claim.get("environment")
    if not env_file:
        return None
    path = _safe(d, env_file)
    digest = _hash_file(path)
    cache_root = _env_cache_dir()
    key = f"{digest}-{platform.python_version()}-{platform.machine()}"
    venv_dir = os.path.join(cache_root, key)
    if os.path.isdir(venv_dir):
        return venv_dir
    os.makedirs(cache_root, exist_ok=True)
    try:
        subprocess.run(
            [sys.executable, "-m", "venv", venv_dir],
            check=True, timeout=FURNISH_TIMEOUT,
            capture_output=True,
        )
        pip = os.path.join(venv_dir, "bin", "pip")
        subprocess.run(
            [pip, "install", "--require-hashes", "--only-binary=:all:",
             "-r", path],
            check=True, timeout=FURNISH_TIMEOUT, capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired) as exc:
        shutil.rmtree(venv_dir, ignore_errors=True)
        raise _in_band(f"could not furnish environment from {env_file!r}", exc) from exc
    return venv_dir


# ---- declared producer independence (an observation, never enforced) -----

def _independence_line(a: dict, b: dict) -> str:
    a = a or {}
    b = b or {}
    va, ma = a.get("vendor"), a.get("model")
    vb, mb = b.get("vendor"), b.get("model")
    if va and vb and va == vb and ma == mb:
        return "independence unestablished (same vendor and model)"
    if va and vb and va == vb:
        return "independence unestablished (same vendor)"
    return "independent"


def independence(m1: dict, m3: dict) -> str:
    """Declared producer independence between a crosscheck's M1 and M3 --
    recorded, never enforced: content cannot prove blindness."""
    p1 = (m1 or {}).get("producer", {})
    p3 = (m3 or {}).get("producer", {})
    return _independence_line(p1, p3)
