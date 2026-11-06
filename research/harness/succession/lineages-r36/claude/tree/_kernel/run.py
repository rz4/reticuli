"""Confined gate execution, the host contract, and the cost ledger.

Every gate runs the same way, whichever verb invoked it:

  * scrubbed environment -- a minimal host allowlist plus the claim's own
    variables, so an inherited secret never reaches a gate and a verdict
    cannot depend on one;
  * sandboxed -- seatbelt on darwin, bubblewrap on linux, probed
    FUNCTIONALLY, because a present-but-nonfunctional sandbox counts as
    none and is reported as none;
  * bounded -- wall-clock limited by the claim's declared window and the
    host ceiling, with the WHOLE process tree killed at the limit;
  * given somewhere to write -- a scratch TMPDIR and HOME inside the claim's
    store, because a real sandbox permits writes only inside the claim while
    the host's point outside it. A confined gate needs a coherent
    environment, not merely a confined one.

A kernel that APPLIES a sandbox also SAYS so, in RETICULI_JAILED: sandboxes
do not nest, and the receiving half of that contract can only fire if some
sender set it.
"""
import json
import os
import shutil
import signal
import subprocess
import sys
import time

from .core import (COST_KEYS, FURNISH_TIMEOUT, GATE_TIMEOUT, LEDGER, STORE,
                   ClaimError, _ENV_CACHE, _ENV_CLAIM, _ENV_MODEL,
                   _ENV_TIMEOUT, _ENV_VENDOR, _JAILED, _KEEP_ENV, _SHELL,
                   _finite, _hash_file, _judging_host, _now, _safe)

#: the comparison operators a `requires` entry may carry
_REQ_OPS = ("<=", ">=", "==", "!=", "~=", "<", ">")

#: functional-probe caches: a backend counts only if it actually works here
_BWRAP_OK = None
_SEATBELT_OK = None


# -- the ledger ------------------------------------------------------------
def _ledger_path(claim: str) -> str:
    return os.path.join(claim, LEDGER)


def ledger(claim: str, event: dict) -> None:
    """Append one event. Residue: outside the root, never a declared file."""
    path = _ledger_path(claim)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = dict(event)
    payload.setdefault("when", _now())
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


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
                    parsed = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    events.append(parsed)
    except (OSError, UnicodeDecodeError):
        return []
    return events


def cost(claim: str):
    """Ledger totals per unit, or None when nothing was measured.

    Totals carry only the keys the ledger names: an unmeasured machine is
    reported, never guessed at. A boolean is not a measurement and a
    non-finite number reports no work, so neither enters a total -- a
    declared ceiling compared against NaN is false whatever the ceiling.

    Discovery-scoped events (what finding the answer cost, as opposed to what
    reproducing it costs) total separately under `discovery`: they are
    testimony a reader weighs, and they must never feed the cost band.
    """
    if not os.path.isfile(_ledger_path(claim)):
        return None
    totals, discovery = {}, {}
    for event in ledger_events(claim):
        target = discovery if event.get("scope") == "discovery" else totals
        for key in COST_KEYS:
            value = event.get(key)
            if _finite(value) and value >= 0:
                target[key] = target.get(key, 0) + value
    if discovery:
        totals["discovery"] = discovery
    return totals or None


# -- the host contract -----------------------------------------------------
def _version_tuple(text: str) -> tuple:
    digits, piece = [], ""
    for char in str(text):
        if char.isdigit():
            piece += char
        elif piece:
            digits.append(int(piece))
            piece = ""
            if char not in ".":
                break
        elif char not in ".":
            if digits:
                break
    if piece:
        digits.append(int(piece))
    return tuple(digits) or (0,)


def _tool_version(name: str):
    if name in ("python", "python3", "cpython"):
        import platform
        return platform.python_version()
    try:
        import importlib
        module = importlib.import_module(name)
        version = getattr(module, "__version__", None)
        if version:
            return str(version)
    except Exception:                      # not a module, or not importable
        pass
    binary = shutil.which(name)
    if not binary:
        return None
    try:
        done = subprocess.run([binary, "--version"], capture_output=True,
                              text=True, timeout=20, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return ((done.stdout or "") + (done.stderr or "")).strip() or None


def _version_ok(name: str, operator: str, wanted: str) -> bool:
    found = _tool_version(name)
    if found is None:
        return False
    have, want = _version_tuple(found), _version_tuple(wanted)
    length = max(len(have), len(want))
    have += (0,) * (length - len(have))
    want += (0,) * (length - len(want))
    if operator == ">=":
        return have >= want
    if operator == "<=":
        return have <= want
    if operator == ">":
        return have > want
    if operator == "<":
        return have < want
    if operator == "==":
        return have == want
    if operator == "!=":
        return have != want
    if operator == "~=":                   # compatible release
        return have >= want and have[:len(want) - 1] == want[:len(want) - 1]
    return False


def _have(requirement: str) -> bool:
    """Is this host's contract met for one `requires` entry?

    An entry names a binary or a Python module, optionally with a version
    comparison. `requires` asserts PRESENCE (and, where stated, version); it
    never constrains a value.
    """
    text = str(requirement).strip()
    for operator in _REQ_OPS:
        if operator in text:
            name, _, wanted = text.partition(operator)
            return _version_ok(name.strip(), operator, wanted.strip())
    if text in ("python", "python3"):
        return True
    if shutil.which(text):
        return True
    try:
        import importlib.util
        return importlib.util.find_spec(text) is not None
    except (ImportError, ValueError, ModuleNotFoundError):
        return False


def preflight(parsed: dict) -> list:
    """What this host does not provide. A missing requirement makes a gate
    outcome `environment` -- the host cannot judge this claim -- which is a
    different fact from the claim being wrong."""
    table = (parsed or {}).get("claim") or {}
    return [r for r in (table.get("requires") or []) if not _have(r)]


# -- the sandbox -----------------------------------------------------------
def _quote_sb(path: str) -> str:
    """A seatbelt profile string literal."""
    return path.replace("\\", "\\\\").replace('"', '\\"')


def _bwrap_usable() -> bool:
    """bwrap on PATH is not a sandbox: a host whose user namespaces are
    blocked has the binary and no confinement. Probe it."""
    global _BWRAP_OK
    if _BWRAP_OK is None:
        _BWRAP_OK = False
        if shutil.which("bwrap"):
            try:
                done = subprocess.run(
                    ["bwrap", "--ro-bind", "/", "/", "--unshare-net", "true"],
                    capture_output=True, timeout=30, check=False)
                _BWRAP_OK = done.returncode == 0
            except (OSError, subprocess.SubprocessError):
                _BWRAP_OK = False
    return _BWRAP_OK


def _seatbelt_usable() -> bool:
    global _SEATBELT_OK
    if _SEATBELT_OK is None:
        _SEATBELT_OK = False
        if sys.platform == "darwin" and shutil.which("sandbox-exec"):
            try:
                done = subprocess.run(
                    ["sandbox-exec", "-p", "(version 1)(allow default)",
                     "true"], capture_output=True, timeout=30, check=False)
                _SEATBELT_OK = done.returncode == 0
            except (OSError, subprocess.SubprocessError):
                _SEATBELT_OK = False
    return _SEATBELT_OK


def sandbox_backend() -> str:
    """Which confinement this host can really apply, honestly named.

    `inherited` when the caller already wrapped us: sandboxes do not nest,
    and re-applying one inside a sandbox refuses.
    """
    if os.environ.get(_JAILED):
        return "inherited"
    if _seatbelt_usable():
        return "seatbelt"
    if _bwrap_usable():
        return "bubblewrap"
    return "none"


def _sandbox_argv(workspace: str, backend: str) -> list:
    """The wrapper argv for one backend over one workspace.

    The floor is a PROPERTY, not a profile syntax: a legitimate gate must
    survive the jail. It may sink to /dev, spawn a subprocess, read the host
    it runs on (the interpreter lives out there), ask the host its name, and
    look up the user it runs as. What stays denied is the network and every
    write outside the workspace.
    """
    room = os.path.realpath(workspace)
    if backend == "seatbelt":
        profile = ("(version 1)(allow default)(deny network*)"
                   "(deny file-write*)"
                   f'(allow file-write* (subpath "{_quote_sb(room)}") '
                   '(subpath "/dev"))')
        return ["sandbox-exec", "-p", profile]
    if backend == "bubblewrap":
        return ["bwrap", "--ro-bind", "/", "/",
                "--dev-bind", "/dev", "/dev", "--proc", "/proc",
                "--bind", room, room, "--chdir", room,
                "--unshare-net", "--die-with-parent"]
    return []


def sandbox(command: str = "true", claim: str | None = None) -> tuple:
    """A functional probe: the wrapper argv and the backend that applied."""
    backend = sandbox_backend()
    workspace = claim or os.getcwd()
    return _sandbox_argv(workspace, backend), backend


# -- the bound -------------------------------------------------------------
def gate_timeout(parsed: dict | None = None) -> float:
    """The effective per-gate ceiling.

    A DECLARED window IS the ceiling, in both directions: the declaration
    may raise it past any implementation default, and a gate past it still
    times out. The host's own ceiling (the environment variable) can only
    tighten -- min(), never max(), the same rule a declared cost band obeys.
    """
    table = (parsed or {}).get("claim") or {}
    declared = table.get("gate_timeout")
    bound = float(declared) if _finite(declared) and declared > 0 \
        else float(GATE_TIMEOUT)
    host = os.environ.get(_ENV_TIMEOUT)
    if host:
        try:
            ceiling = float(host)
        except ValueError:
            ceiling = None
        if ceiling and ceiling > 0:
            bound = min(bound, ceiling)
    return bound


def _kill_tree(process) -> None:
    """The ceiling bounds the WORK, not the paperwork: a runaway grandchild
    outlives the shell a plain kill reaches, so the whole session goes."""
    for killer in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(os.getpgid(process.pid), killer)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                process.kill()
            except OSError:
                pass
        try:
            process.wait(timeout=5)
            return
        except subprocess.TimeoutExpired:
            continue


def _scratch(claim: str) -> str:
    where = os.path.join(claim, STORE, "scratch")
    os.makedirs(where, exist_ok=True)
    return os.path.realpath(where)


def _scrub_env(claim: str, backend: str, extra: dict | None = None) -> dict:
    """A minimal host allowlist plus the claim's own variables."""
    env = {key: os.environ[key] for key in _KEEP_ENV if key in os.environ}
    env.setdefault("PATH", os.defpath)
    scratch = _scratch(claim)
    env["TMPDIR"] = scratch
    env["TEMP"] = scratch
    env["TMP"] = scratch
    env["HOME"] = scratch
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env[_ENV_CLAIM] = os.path.realpath(claim)
    if backend in ("seatbelt", "bubblewrap"):
        env[_JAILED] = backend
    for key, value in (extra or {}).items():
        if value is not None:
            env[key] = str(value)
    return env


def _run(argv, cwd, env, limit):
    """One bounded subprocess, its whole tree bounded with it."""
    started = time.monotonic()
    try:
        process = subprocess.Popen(
            argv, cwd=cwd, env=env, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, start_new_session=True)
    except OSError as exc:
        return 127, "", f"cannot execute: {exc}", 0.0, False
    try:
        out, err = process.communicate(timeout=limit)
        return (process.returncode, out or "", err or "",
                time.monotonic() - started, False)
    except subprocess.TimeoutExpired:
        _kill_tree(process)
        try:
            out, err = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            out, err = "", ""
        return (124, out or "", err or "",
                time.monotonic() - started, True)


def run_gate(command: str, claim: str, parsed: dict | None = None,
             extra_env: dict | None = None, strict: bool = True,
             limit: float | None = None) -> dict:
    """Run one gate: scrubbed, sandboxed, bounded. The gate entry point."""
    os.makedirs(claim, exist_ok=True)
    backend = sandbox_backend() if strict else (
        "inherited" if os.environ.get(_JAILED) else "none")
    argv = (_sandbox_argv(claim, backend) if strict else []) + \
        [_SHELL, "-c", command]
    env = _scrub_env(claim, backend if strict else "none", extra_env)
    bound = limit if limit else gate_timeout(parsed)
    code, out, err, elapsed, timed_out = _run(argv, claim, env, bound)
    status = "timeout" if timed_out else ("ok" if code == 0 else "failed")
    return {"status": status, "quarantine": backend, "returncode": code,
            "stdout": out, "stderr": err, "seconds": round(elapsed, 4),
            "command": command}


# -- the declared environment ----------------------------------------------
def _env_cache_dir() -> str:
    """Furnished environments are host residue, cached per (file digest,
    interpreter, platform). They never touch identity."""
    configured = os.environ.get(_ENV_CACHE)
    if configured:
        return configured
    return os.path.join(os.path.expanduser("~"), ".cache", "reticuli", "env")


def furnish(claim: str, parsed: dict) -> dict:
    """Build a private venv from exactly the artifacts a lock file names.

    `--require-hashes`, so nothing unnamed can arrive, and
    `--only-binary=:all:`, so nothing executes at install time: installing a
    wheel unpacks files, and it is source builds that run code. A room that
    cannot be furnished is an ENVIRONMENT failure -- the gates were not run,
    nothing proven, nothing disproven.
    """
    table = (parsed or {}).get("claim") or {}
    lock = table.get("environment")
    if not lock:
        return {"ok": True, "bin": None, "reason": None}
    path = _safe(claim, lock)
    if not os.path.isfile(path):
        return {"ok": False, "bin": None,
                "reason": f"the declared environment {lock!r} is missing"}
    digest = _hash_file(path)
    import platform
    key = f"{digest[:32]}-{platform.python_version()}-{sys.platform}"
    home = os.path.join(_env_cache_dir(), key)
    marker = os.path.join(home, ".furnished")
    binaries = os.path.join(home, "bin")
    if os.path.isfile(marker):
        return {"ok": True, "bin": binaries, "reason": None}
    shutil.rmtree(home, ignore_errors=True)
    os.makedirs(os.path.dirname(home) or ".", exist_ok=True)
    made = subprocess.run([sys.executable, "-m", "venv", home],
                          capture_output=True, text=True,
                          timeout=FURNISH_TIMEOUT, check=False)
    if made.returncode != 0:
        shutil.rmtree(home, ignore_errors=True)
        return {"ok": False, "bin": None,
                "reason": f"no private environment could be built: "
                          f"{(made.stderr or made.stdout)[-200:]}"}
    python = os.path.join(binaries, "python")
    installed = subprocess.run(
        [python, "-m", "pip", "install", "--no-cache-dir",
         "--require-hashes", "--only-binary=:all:", "-r", path],
        capture_output=True, text=True, cwd=claim,
        timeout=FURNISH_TIMEOUT, check=False)
    if installed.returncode != 0:
        shutil.rmtree(home, ignore_errors=True)
        return {"ok": False, "bin": None,
                "reason": f"the room cannot be furnished from {lock!r}: "
                          f"{(installed.stderr or installed.stdout)[-300:]}"}
    with open(marker, "w", encoding="utf-8") as handle:
        handle.write(digest + "\n")
    return {"ok": True, "bin": binaries, "reason": None}


# -- cost comparison -------------------------------------------------------
def _in_band(c3: float, c1: float, tolerance: float) -> bool:
    """Comparability is a BAND, inclusive at both ends: [1/tol, tol].

    An open interval would refuse a redo whose ratio sits exactly on the
    declared tolerance, so two conforming implementations would disagree
    about a verdict at the boundary.
    """
    if not _finite(c1) or not _finite(c3) or c1 <= 0 or tolerance <= 0:
        return False
    ratio = c3 / c1
    return (1.0 / tolerance) <= ratio <= tolerance


# -- declared independence -------------------------------------------------
def independence(claim: str) -> dict:
    """What the redo's ledger SAYS about who produced it. A declaration,
    never proof: content cannot prove blindness."""
    found = {"vendor": None, "model": None, "blind": False}
    for event in ledger_events(claim):
        if event.get("event") != "producer":
            continue
        for key in ("vendor", "model"):
            if event.get(key):
                found[key] = event[key]
        if "blind" in event:
            found["blind"] = bool(event["blind"])
    return found


def _independence_line(declared: dict | None) -> str:
    if not declared or not (declared.get("vendor") or declared.get("model")):
        return ("unestablished: the redo declares no producer, and content "
                "cannot prove independence")
    vendor = declared.get("vendor") or "unknown"
    model = declared.get("model") or "unknown"
    room = "blind workspace" if declared.get("blind") else "sighted workspace"
    return (f"declared: {vendor}/{model}, {room} "
            f"(declared by the producer, not proven)")


def environment_event(claim: str, backend: str) -> None:
    host = dict(_judging_host())
    host["event"] = "environment"
    host["quarantine"] = backend
    ledger(claim, host)


def producer_declaration() -> dict:
    return {"vendor": os.environ.get(_ENV_VENDOR),
            "model": os.environ.get(_ENV_MODEL)}
