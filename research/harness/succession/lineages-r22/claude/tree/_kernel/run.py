"""Running a gate: confinement, the cost ledger, and the environment contract.

`run_gate` is the one way any verb executes a gate command: a scrubbed
environment, a sandbox probed functionally rather than assumed
(`sandbox_backend`/`sandbox`), and a wall-clock bound that a claim's own
`gate_timeout` may raise past any implementation default
(`gate_timeout`). The sandbox is permissive by default and denies only
what the format actually promises to deny -- the network, and writes
outside the workspace -- so a real gate's ordinary syscalls (spawning a
child, reading the host, asking its own name, looking up its own user)
keep working under confinement (spec/claim-format.md: the jail's floor).

`preflight` checks the environment contract (`[claim] requires`) against
the host, with an optional version constraint parsed by `_REQ_OPS`.
`furnish` builds (and caches) a private venv from a claim's pinned
`environment` file, hash-pinned and wheel-only, so furnishing can use the
network while the gate that follows still cannot. `independence` records,
never enforces, whether two producers' declarations look distinct.

`ledger`/`ledger_events`/`cost` are the claim's own cost bookkeeping: one
JSON line per rebuild, totalled per unit, omitting any unit nothing ever
measured.
"""
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import tempfile

from . import core
from .core import ClaimError

# Requirement-string operators, longest first so "pkg>=1.0" never
# mis-splits on a bare ">" (spec/claim-format.md: [claim] requires).
_REQ_OPS = ('<=', '>=', '==', '!=', '~=', '<', '>')

# Cached result of the one-time functional bwrap probe: None (unprobed),
# or the probe's boolean verdict.
_BWRAP_OK = None


# ---------------------------------------------------------------- helpers --

def _in_band(fn, *args, **kwargs):
    """Call `fn`, turning any exception into a ClaimError with a reason --
    the environment a gate depends on (a venv install, a tool probe) is as
    untrusted as the claim's own recipe."""
    try:
        return fn(*args, **kwargs)
    except ClaimError:
        raise
    except Exception as exc:
        raise ClaimError(f"{getattr(fn, '__name__', fn)} failed: {exc}") from exc


def _have(name: str) -> bool:
    """Is `name` satisfiable on this host: a binary on PATH, or an
    importable Python module?"""
    if shutil.which(name) is not None:
        return True
    try:
        import importlib.util
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError, ModuleNotFoundError):
        return False


def _split_requirement(req: str):
    """Split a `requires` entry into `(name, op, version)`; `op`/`version`
    are `None` when the entry names no version constraint."""
    for op in _REQ_OPS:
        idx = req.find(op)
        if idx != -1:
            return req[:idx].strip(), op, req[idx + len(op):].strip()
    return req.strip(), None, None


def _version_tuple(version: str) -> tuple:
    """A dotted version string as a tuple comparable to another of the
    same shape: numeric components compare as integers."""
    parts = re.split(r"[.+-]", version.strip())
    return tuple(int(p) if p.isdigit() else p for p in parts if p != "")


def _version_ok(installed: str, op: str, required: str) -> bool:
    """Does `installed` satisfy `<op> required`?"""
    a = _version_tuple(installed)
    b = _version_tuple(required)
    try:
        if op == "==":
            return a == b
        if op == "!=":
            return a != b
        if op == "<=":
            return a <= b
        if op == ">=":
            return a >= b
        if op == "<":
            return a < b
        if op == ">":
            return a > b
        if op == "~=":
            return a[:-1] == b[:-1] and a >= b
    except TypeError:
        return str(installed) == str(required) if op in ("==", "~=") else False
    raise ClaimError(f"unknown version operator: {op!r}")


def _tool_version(name: str) -> str:
    """Best-effort installed version string for a binary or a Python
    module, by whatever means applies first."""
    try:
        import importlib.metadata
        return importlib.metadata.version(name)
    except Exception:
        pass
    path = shutil.which(name)
    if path:
        try:
            out = subprocess.run([path, "--version"], capture_output=True,
                                  text=True, timeout=5)
            text = (out.stdout or out.stderr or "").strip()
            m = re.search(r"\d+(?:\.\d+)+", text)
            if m:
                return m.group(0)
        except (OSError, subprocess.TimeoutExpired):
            pass
    try:
        mod = __import__(name)
        v = getattr(mod, "__version__", None)
        if v:
            return str(v)
    except ImportError:
        pass
    raise ClaimError(f"cannot determine the installed version of {name!r}")


def preflight(recipe: dict) -> list:
    """The environment contract: which declared `requires` entries this
    host cannot satisfy -- missing entirely, or present but failing a
    declared version constraint. Empty means the host is ready."""
    claim = (recipe or {}).get("claim", {})
    missing = []
    for req in claim.get("requires", []):
        name, op, wanted = _split_requirement(req)
        if not _have(name):
            missing.append(req)
            continue
        if op is not None:
            try:
                if not _version_ok(_tool_version(name), op, wanted):
                    missing.append(req)
            except ClaimError:
                missing.append(req)
    return missing


def _independence_line(established: bool) -> str:
    """The human-readable line a crosscheck attaches to an independence
    verdict (spec/verification.md: `independence unestablished`)."""
    if established:
        return "independence declared"
    return "independence unestablished: same vendor and model as the original producer"


def independence(m1_producer: dict, m3_producer: dict) -> dict:
    """Declared producer independence of a crosscheck -- recorded, never
    enforced, since content cannot prove blindness. A shared vendor and
    model marks the pair unestablished."""
    m1 = m1_producer or {}
    m3 = m3_producer or {}
    same_vendor = m1.get("vendor") is not None and m1.get("vendor") == m3.get("vendor")
    same_model = m1.get("model") is not None and m1.get("model") == m3.get("model")
    established = not (same_vendor and same_model)
    return {"established": established, "line": _independence_line(established)}


# ------------------------------------------------------------------ cost --

def _ledger_path(d: str) -> str:
    return os.path.join(d, core.LEDGER)


def ledger(d: str, entry: dict) -> None:
    """Append one JSON entry to the claim's cost ledger."""
    path = _ledger_path(d)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def ledger_events(d: str) -> list:
    """Every entry recorded in the claim's ledger, in file order."""
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


def cost(d: str) -> dict:
    """Ledger totals per unit (spec/kernel-api.md); a unit nothing ever
    measured is simply absent, never zero. `None` if nothing was measured
    at all."""
    totals = {}
    for event in ledger_events(d):
        for key in core.COST_KEYS:
            value = event.get(key)
            if value is None:
                continue
            totals[key] = totals.get(key, 0) + value
    return totals or None


def gate_timeout(recipe: dict) -> float:
    """The effective wall-clock ceiling for a gate: a claim's own
    declaration IS the ceiling, raising it past any implementation
    default; `RETICULI_GATE_TIMEOUT`, where set, is the host's own cap and
    still bounds a declaration past it (spec/claim-format.md,
    checks/run_check.py)."""
    claim = (recipe or {}).get("claim", {}) if recipe else {}
    declared = claim.get("gate_timeout")
    base = float(declared) if declared is not None else core.GATE_TIMEOUT
    cap = os.environ.get(core._ENV_TIMEOUT)
    if cap is not None:
        try:
            base = min(base, float(cap))
        except ValueError:
            pass
    return base


# -------------------------------------------------------------- sandbox --

def _seatbelt_usable() -> bool:
    """Functional probe of macOS `sandbox-exec`: present is not enough."""
    try:
        result = subprocess.run(
            ["/usr/bin/sandbox-exec", "-p", "(version 1)(allow default)",
             core._SHELL, "-c", "true"],
            capture_output=True, timeout=5,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _bwrap_usable() -> bool:
    """Functional probe of Linux `bwrap`, cached in `_BWRAP_OK`: present is
    not enough -- an unprivileged host may have a bwrap binary that cannot
    actually create a namespace."""
    global _BWRAP_OK
    if _BWRAP_OK is not None:
        return _BWRAP_OK
    bwrap = shutil.which("bwrap")
    if not bwrap:
        _BWRAP_OK = False
        return False
    try:
        result = subprocess.run(
            [bwrap, "--ro-bind", "/", "/", "--unshare-net",
             "--die-with-parent", "true"],
            capture_output=True, timeout=5,
        )
        _BWRAP_OK = result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        _BWRAP_OK = False
    return _BWRAP_OK


def sandbox_backend() -> str:
    """Which confinement applies right now: `inherited` when already
    inside one (`RETICULI_JAILED` -- a kernel given the signal inherits
    rather than nesting), else a functional probe of the host's own
    mechanism, else `none`, reported honestly rather than assumed."""
    if os.environ.get(core._JAILED):
        return "inherited"
    if sys.platform == "darwin":
        return "seatbelt" if _seatbelt_usable() else "none"
    if sys.platform.startswith("linux"):
        return "bubblewrap" if _bwrap_usable() else "none"
    return "none"


def sandbox() -> dict:
    """A functional probe of the host sandbox; the shape beyond `backend`
    is implementation-defined (spec/verification.md)."""
    return {"backend": sandbox_backend()}


def _quote_sb(s: str) -> str:
    """Escape a string for a Seatbelt profile string literal."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _seatbelt_profile(workspace: str) -> str:
    """A permissive-by-default Seatbelt profile that denies only what the
    format promises to deny: the network, and writes outside the
    workspace. Reads, process spawn, and host-identity lookups (uname,
    the user database) stay open -- the jail's floor
    (spec/claim-format.md): a kernel may allow-by-default-and-deny or
    deny-by-default-with-a-sufficient-allowlist, so long as a real gate
    runs, and the narrower deny list is the one that needs no per-syscall
    tuning to clear it."""
    return "\n".join([
        "(version 1)",
        "(allow default)",
        "(deny network*)",
        '(deny file-write* (require-not (subpath "%s")))' % _quote_sb(workspace),
        '(allow file-write* (literal "/dev/null"))',
    ])


def _sandbox_argv(backend: str, cmd: str, d: str, scratch: str) -> list:
    """The argv that runs `cmd` under `backend`'s confinement, or
    unwrapped for `none`/`inherited`."""
    if backend == "seatbelt":
        profile = _seatbelt_profile(os.path.realpath(d))
        return ["/usr/bin/sandbox-exec", "-p", profile, core._SHELL, "-c", cmd]
    if backend == "bubblewrap":
        bwrap = shutil.which("bwrap")
        argv = [
            bwrap,
            "--ro-bind", "/", "/",
            "--dev", "/dev",
            "--proc", "/proc",
            "--bind", d, d,
        ]
        if scratch and scratch != d:
            argv += ["--bind", scratch, scratch]
        argv += [
            "--unshare-net",
            "--die-with-parent",
            "--chdir", d,
            core._SHELL, "-c", cmd,
        ]
        return argv
    return [core._SHELL, "-c", cmd]


def _scrub_env(d: str, recipe: dict, scratch: str = None) -> dict:
    """A minimal host allowlist plus the already-jailed signal; inherited
    secrets never reach a gate. Where a real sandbox applies, `TMPDIR` and
    `HOME` point into the scratch directory inside the claim's store, so a
    gate using `tempfile` has somewhere confinement actually lets it write
    (spec/claim-format.md: a confined gate needs a coherent environment,
    not merely a confined one)."""
    env = {k: os.environ[k] for k in core._KEEP_ENV if k in os.environ}
    env[core._JAILED] = "1"
    if scratch is not None:
        env["TMPDIR"] = scratch
        env["HOME"] = scratch
    return env


def _kill_tree(pid: int) -> None:
    """Kill a timed-out gate's whole process group, not just the shell
    that spawned its children."""
    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass


def _run(argv: list, cwd: str, env: dict, timeout: float):
    """Run `argv`, returning `(returncode, timed_out)`; a timeout kills the
    whole process group rather than leaving orphans behind."""
    proc = subprocess.Popen(
        argv, cwd=cwd, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        return proc.wait(timeout=timeout), False
    except subprocess.TimeoutExpired:
        _kill_tree(proc.pid)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        return None, True


def run_gate(cmd: str, d: str, recipe: dict) -> dict:
    """Run one gate command inside `d`: scrubbed environment, sandboxed
    under whatever backend is actually functional, bounded by the
    declared (or default) wall-clock ceiling (spec/claim-format.md: the
    gate execution contract). Returns at least `status`
    (`ok`/`failed`/`timeout`) and `quarantine` (the sandbox backend that
    applied)."""
    backend = sandbox_backend()
    timeout = gate_timeout(recipe)
    scratch = None
    if backend not in ("none", "inherited"):
        scratch_root = os.path.join(d, core.STORE, "scratch")
        os.makedirs(scratch_root, exist_ok=True)
        scratch = tempfile.mkdtemp(dir=scratch_root)
    env = _scrub_env(d, recipe, scratch)
    argv = _sandbox_argv(backend, cmd, d, scratch if scratch is not None else d)
    returncode, timed_out = _run(argv, d, env, timeout)
    if timed_out:
        status = "timeout"
    elif returncode == 0:
        status = "ok"
    else:
        status = "failed"
    return {"status": status, "quarantine": backend}


# ----------------------------------------------------------- furnishing --

def _env_cache_dir() -> str:
    """Where furnished venvs are cached: `RETICULI_ENV_CACHE`, or a
    per-user cache directory. Host residue, never identity
    (spec/claim-format.md)."""
    override = os.environ.get(core._ENV_CACHE)
    if override:
        os.makedirs(override, exist_ok=True)
        return override
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    path = os.path.join(base, "reticuli", "env")
    os.makedirs(path, exist_ok=True)
    return path


def furnish(d: str, recipe: dict) -> str:
    """Build (or reuse a cached) private venv for the claim's pinned
    `environment` file -- `--require-hashes`, `--only-binary=:all:`, so
    nothing unnamed arrives and nothing executes at install time. Returns
    the venv's bin directory to put first on the gate's `PATH`, or `None`
    when the claim declares no environment. A room that cannot be
    furnished is a refusal naming why (spec/claim-format.md: an
    `environment` failure, not a verdict)."""
    claim = (recipe or {}).get("claim", {}) if recipe else {}
    env_file = claim.get("environment")
    if not env_file:
        return None
    path = core._safe(d, env_file)
    if not os.path.isfile(path):
        raise ClaimError(f"environment file is gone: {env_file!r}")
    digest = core._hash_file(path)
    key = f"{digest}-{platform.python_version()}-{sys.platform}-{platform.machine()}"
    venv_dir = os.path.join(_env_cache_dir(), key)
    bin_name = "Scripts" if sys.platform == "win32" else "bin"
    bin_dir = os.path.join(venv_dir, bin_name)
    if os.path.isdir(venv_dir):
        return bin_dir

    tmp_dir = venv_dir + ".tmp"
    shutil.rmtree(tmp_dir, ignore_errors=True)
    _in_band(subprocess.run, [sys.executable, "-m", "venv", tmp_dir],
             check=True, capture_output=True, text=True, timeout=core.FURNISH_TIMEOUT)
    pip = os.path.join(tmp_dir, bin_name, "pip")
    result = subprocess.run(
        [pip, "install", "--require-hashes", "--only-binary=:all:", "-r", path],
        capture_output=True, text=True, timeout=core.FURNISH_TIMEOUT,
    )
    if result.returncode != 0:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise ClaimError(
            f"cannot furnish environment {env_file!r}: {result.stderr.strip()}"
        )
    os.replace(tmp_dir, venv_dir)
    return bin_dir
