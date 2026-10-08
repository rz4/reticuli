"""Running a claim's gate (spec/claim-format.md: gate execution contract).

`run_gate` runs one gate command under a functional platform sandbox
(macOS `sandbox-exec` / Linux `bwrap`, "none" where neither probes usable,
"inherited" where the caller is already jailed), with a scrubbed
environment and a wall-clock bound, and reports a status
(`ok`/`failed`/`timeout`) and which quarantine applied. `ledger` appends
what a run cost to the claim's cost ledger; `cost` totals it, carrying
only the units the ledger actually names. `preflight` checks a recipe's
`requires` against the host; `furnish` builds the private venv a
declared `environment` needs before a gate may run in it. `independence`
records (never enforces) whether a crosscheck's producers were
declared distinct. Stdlib only, never the network itself.
"""
import importlib
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import sys

from . import core
from .core import ClaimError

_REQ_OPS = ("<=", ">=", "==", "!=", "~=", "<", ">")

_BWRAP_OK = None
_SEATBELT_OK = None


# -- version parsing, for `requires` entries that name a minimum ----------

def _version_tuple(text: str) -> tuple:
    """A dotted version string as a tuple of ints, trailing junk dropped."""
    parts = []
    for chunk in text.strip().split("."):
        digits = ""
        for ch in chunk:
            if not ch.isdigit():
                break
            digits += ch
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def _split_requirement(req: str):
    """`("name", op, "version")`, or `(name, None, None)` with no operator."""
    for op in _REQ_OPS:
        idx = req.find(op)
        if idx > 0:
            return req[:idx].strip(), op, req[idx + len(op):].strip()
    return req.strip(), None, None


def _version_ok(actual: str, requirement: str) -> bool:
    """Does `actual` ('1.2.3') satisfy `requirement` ('>=1.0')?"""
    for op in _REQ_OPS:
        if requirement.startswith(op):
            want = _version_tuple(requirement[len(op):])
            have = _version_tuple(actual)
            if op == "<=":
                return have <= want
            if op == ">=":
                return have >= want
            if op == "==":
                return have == want
            if op == "!=":
                return have != want
            if op == "~=":
                return have[:-1] == want[:-1] and have >= want
            if op == "<":
                return have < want
            if op == ">":
                return have > want
    return True


def _tool_version(name: str):
    """The first dotted version token `name --version` prints, or `None`."""
    try:
        done = subprocess.run([name, "--version"], capture_output=True,
                               text=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = (done.stdout or "") + (done.stderr or "")
    found = re.search(r"\d+(?:\.\d+)+", text)
    return found.group(0) if found else None


# -- the environment contract: `requires` -------------------------------

def _have(name: str) -> bool:
    """Is `name` a binary on PATH or an importable Python module?"""
    if shutil.which(name):
        return True
    try:
        importlib.import_module(name)
        return True
    except Exception:
        return False


def preflight(recipe: dict) -> list:
    """Declared `requires` entries missing from this host, recipe order."""
    claim = recipe.get("claim", {}) if isinstance(recipe, dict) else {}
    missing = []
    for req in claim.get("requires") or []:
        name, op, want = _split_requirement(req)
        if not _have(name):
            missing.append(req)
            continue
        if op:
            actual = _tool_version(name)
            if actual is None or not _version_ok(actual, op + want):
                missing.append(req)
    return missing


# -- furnishing a declared `environment` ---------------------------------

def _env_cache_dir() -> str:
    """Host cache root for furnished venvs, keyed by (digest, interpreter,
    platform) at the call site -- never part of a claim's identity."""
    override = os.environ.get(core._ENV_CACHE)
    if override:
        return override
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(base, "reticuli", "envs")


def furnish(d: str, path: str) -> str:
    """Build (or reuse) a private venv from a hash-pinned requirements file;
    return its `bin` directory. A room that cannot be furnished refuses as
    a `ClaimError` (spec/claim-format.md: an `environment` failure)."""
    full = core._safe(d, path)
    try:
        digest = core._hash_file(full)
    except OSError as e:
        raise ClaimError(f"cannot read environment file {path!r}: {e}") from e

    key = "-".join([
        digest,
        platform.python_implementation(), platform.python_version(),
        sys.platform, platform.machine(),
    ])
    venv_dir = os.path.join(_env_cache_dir(), key)
    bin_dir = os.path.join(venv_dir, "bin")
    if os.path.isdir(bin_dir):
        return bin_dir

    try:
        subprocess.run([sys.executable, "-m", "venv", venv_dir], check=True,
                        capture_output=True, text=True, timeout=core.FURNISH_TIMEOUT)
        subprocess.run(
            [os.path.join(bin_dir, "python3"), "-m", "pip", "install",
             "--require-hashes", "--only-binary=:all:", "-r", full],
            check=True, capture_output=True, text=True, timeout=core.FURNISH_TIMEOUT)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
        shutil.rmtree(venv_dir, ignore_errors=True)
        raise ClaimError(f"could not furnish environment from {path!r}: {e}") from e
    return bin_dir


# -- the sandbox: a functional probe, never a presence check -------------

def _in_band() -> bool:
    """Is this process already running inside a sandbox? A gate it starts
    must inherit rather than nest (spec/kernel-api.md)."""
    return os.environ.get(core._JAILED) == "1"


def _seatbelt_usable() -> bool:
    global _SEATBELT_OK
    if _SEATBELT_OK is None:
        if not os.path.exists("/usr/bin/sandbox-exec"):
            _SEATBELT_OK = False
        else:
            try:
                done = subprocess.run(
                    ["/usr/bin/sandbox-exec", "-p", "(version 1)(allow default)",
                     "/bin/sh", "-c", "exit 0"],
                    capture_output=True, timeout=5, check=False)
                _SEATBELT_OK = done.returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                _SEATBELT_OK = False
    return _SEATBELT_OK


def _bwrap_usable() -> bool:
    global _BWRAP_OK
    if _BWRAP_OK is None:
        if shutil.which("bwrap") is None:
            _BWRAP_OK = False
        else:
            try:
                done = subprocess.run(
                    ["bwrap", "--ro-bind", "/", "/", "--unshare-net", "--die-with-parent", "true"],
                    capture_output=True, timeout=5, check=False)
                _BWRAP_OK = done.returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                _BWRAP_OK = False
    return _BWRAP_OK


def sandbox_backend() -> str:
    """Which quarantine actually applies here: `inherited` when already
    jailed, else the first platform sandbox that probes functional, else
    `none` -- honestly reported, never assumed from mere presence."""
    if _in_band():
        return "inherited"
    if sys.platform == "darwin" and _seatbelt_usable():
        return "seatbelt"
    if sys.platform.startswith("linux") and _bwrap_usable():
        return "bubblewrap"
    return "none"


def sandbox() -> dict:
    """A functional probe of the host sandbox (spec/kernel-api.md: `jail`)."""
    return {"backend": sandbox_backend(), "platform": sys.platform, "jailed": _in_band()}


# -- the room a gate runs in: scrubbed environment, confined paths -------

def _scrub_env(d: str) -> dict:
    """A minimal host allowlist plus the claim's own scratch (spec/
    claim-format.md): TMPDIR/HOME point inside the claim's store so a
    gate using `tempfile` has somewhere the sandbox actually lets it write."""
    env = {k: os.environ[k] for k in core._KEEP_ENV if k in os.environ}
    env.setdefault("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")
    scratch = os.path.join(d, core.STORE, "scratch")
    os.makedirs(scratch, exist_ok=True)
    env["HOME"] = scratch
    env["TMPDIR"] = scratch
    env[core._JAILED] = "1"
    return env


def _quote_sb(text: str) -> str:
    """Quote a string as a sandbox-exec (Scheme) profile literal."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _seatbelt_profile(workspace: str) -> str:
    """The jail's floor (spec/claim-format.md): a gate may sink to
    /dev/null, spawn a subprocess, and read anything the host can reach
    (the interpreter lives out there) -- and may write only inside its
    own workspace. Network and writes elsewhere stay denied by default."""
    lines = [
        "(version 1)",
        "(deny default)",
        "(allow process-fork)",
        "(allow process-exec*)",
        "(allow file-read*)",
        "(allow sysctl-read)",
        "(allow mach-lookup)",
        "(allow signal (target self))",
        f"(allow file-write* (subpath {_quote_sb(workspace)}))",
        '(allow file-write* (literal "/dev/null"))',
    ]
    return "\n".join(lines)


def _bwrap_argv(command: str, workspace: str) -> list:
    return [
        "bwrap",
        "--ro-bind", "/", "/",
        "--dev", "/dev",
        "--proc", "/proc",
        "--tmpfs", "/tmp",
        "--bind", workspace, workspace,
        "--unshare-net",
        "--die-with-parent",
        "--chdir", workspace,
        core._SHELL, "-c", command,
    ]


def _sandbox_argv(command: str, d: str, backend: str) -> list:
    """The argv that runs `command` under `backend`'s confinement."""
    workspace = os.path.realpath(d)
    if backend == "seatbelt":
        profile_path = os.path.join(workspace, core.STORE, "scratch", "sandbox.sb")
        os.makedirs(os.path.dirname(profile_path), exist_ok=True)
        with open(profile_path, "w", encoding="utf-8") as f:
            f.write(_seatbelt_profile(workspace))
        return ["/usr/bin/sandbox-exec", "-f", profile_path, core._SHELL, "-c", command]
    if backend == "bubblewrap":
        return _bwrap_argv(command, workspace)
    return [core._SHELL, "-c", command]


# -- running and bounding the gate's process ------------------------------

def _kill_tree(pid: int) -> None:
    """Kill a timed-out gate's whole process group, not just its leader."""
    try:
        os.killpg(os.getpgid(pid), signal.SIGKILL)
        return
    except (ProcessLookupError, PermissionError, OSError):
        pass
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


def _run(argv: list, cwd: str, env: dict, timeout: float) -> dict:
    """Run `argv`, bounded by `timeout`; the whole tree is killed on expiry."""
    proc = subprocess.Popen(argv, cwd=cwd, env=env, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        out, err = proc.communicate(timeout=timeout)
        return {"returncode": proc.returncode, "stdout": out, "stderr": err, "timed_out": False}
    except subprocess.TimeoutExpired:
        _kill_tree(proc.pid)
        out, err = proc.communicate()
        return {"returncode": proc.returncode, "stdout": out, "stderr": err, "timed_out": True}


def gate_timeout(recipe) -> float:
    """The declared `gate_timeout` IS the ceiling when present -- it may
    raise the bound past any implementation default, never undercut by
    one. Absent a declaration, `RETICULI_GATE_TIMEOUT` sets the host
    default, else `core.GATE_TIMEOUT`."""
    claim = recipe.get("claim", {}) if isinstance(recipe, dict) else {}
    declared = claim.get("gate_timeout")
    if declared is not None:
        return float(declared)
    env = os.environ.get(core._ENV_TIMEOUT)
    if env:
        try:
            return float(env)
        except ValueError:
            pass
    return core.GATE_TIMEOUT


def run_gate(command: str, d: str, recipe=None) -> dict:
    """Run one gate command in `d`: scrubbed environment, sandboxed,
    bounded by `gate_timeout(recipe)`. Reports `status`
    (`ok`/`failed`/`timeout`) and which `quarantine` applied."""
    timeout = gate_timeout(recipe)
    backend = sandbox_backend()
    env = _scrub_env(d)
    argv = _sandbox_argv(command, d, backend)
    result = _run(argv, d, env, timeout)
    if result["timed_out"]:
        status = "timeout"
    elif result["returncode"] == 0:
        status = "ok"
    else:
        status = "failed"
    return {
        "status": status,
        "quarantine": backend,
        "returncode": result["returncode"],
        "stdout": result["stdout"],
        "stderr": result["stderr"],
    }


# -- the cost ledger -------------------------------------------------------

def _ledger_path(d: str) -> str:
    return os.path.join(d, core.LEDGER)


def ledger(d: str, entry: dict) -> None:
    """Append one cost-ledger entry (spec/verification.md: producer
    identity, model, calls, tokens, usd, seconds, and judging-host residue)."""
    path = _ledger_path(d)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    record = dict(entry)
    record.setdefault("when", core._now())
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True))
        f.write("\n")


def ledger_events(d: str) -> list:
    """Every entry appended to `d`'s ledger, in append order."""
    path = _ledger_path(d)
    if not os.path.isfile(path):
        return []
    events = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def cost(d: str):
    """Ledger totals per unit; `None` if nothing was measured. A total
    carries only the keys the ledger actually names (spec/kernel-api.md)."""
    totals = {}
    for event in ledger_events(d):
        for key in core.COST_KEYS:
            value = event.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                totals[key] = totals.get(key, 0) + value
    return totals or None


# -- declared producer independence (spec/verification.md) ---------------

def _independence_line(m1: dict, m3: dict, established: bool) -> str:
    vendor1 = (m1 or {}).get("vendor", "unknown")
    vendor3 = (m3 or {}).get("vendor", "unknown")
    if established:
        return f"{vendor3} is declared independent of {vendor1}"
    return f"independence unestablished ({vendor3} vs {vendor1})"


def independence(m1: dict, m3: dict) -> dict:
    """Declared (never enforced) producer independence of a crosscheck:
    same-vendor rebuilds are marked as such."""
    vendor1 = (m1 or {}).get("vendor")
    vendor3 = (m3 or {}).get("vendor")
    established = bool(vendor1) and bool(vendor3) and vendor1 != vendor3
    return {"established": established, "line": _independence_line(m1, m3, established)}
