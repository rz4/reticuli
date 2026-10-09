"""Confined gate execution and the cost ledger (`spec/claim-format.md`,
`spec/verification.md`).

A gate always runs the same way: a scrubbed environment, sandboxed where a
functional sandbox exists on the host, bounded by its declared (or
default) wall-clock ceiling, and given scratch space inside the claim's
own store rather than the host's shared temp directories. `run_gate` is
that one execution path; everything else here either builds the sandbox
invocation, totals what a run cost, or checks the host can meet a claim's
declared environment contract.

Stdlib only.
"""
import importlib.metadata
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
import tempfile

from . import core
from .core import ClaimError

_REQ_OPS = ("<=", ">=", "==", "!=", "~=", "<", ">")
_VERSION_COMPARE = {
    "<=": operator.le,
    ">=": operator.ge,
    "==": operator.eq,
    "!=": operator.ne,
    "<": operator.lt,
    ">": operator.gt,
}

# Lazily probed, functionally: a present-but-broken bwrap counts as none.
_BWRAP_OK = None


# -- Sandbox probing and selection --------------------------------------


def _in_band() -> bool:
    """Already running inside an applied sandbox (sandboxes do not nest)."""
    return bool(os.environ.get(core._JAILED))


def _bwrap_usable() -> bool:
    """Functional probe of `bwrap`: present is not the same as working."""
    global _BWRAP_OK
    if _BWRAP_OK is None:
        path = shutil.which("bwrap")
        if not path:
            _BWRAP_OK = False
        else:
            try:
                probe = subprocess.run(
                    [path, "--ro-bind", "/", "/", "--unshare-all",
                     "--die-with-parent", "true"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=5,
                )
                _BWRAP_OK = probe.returncode == 0
            except (OSError, subprocess.SubprocessError):
                _BWRAP_OK = False
    return _BWRAP_OK


def sandbox_backend() -> str:
    """Which confinement, if any, a gate here would run under."""
    if _in_band():
        return "inherited"
    system = platform.system()
    if system == "Darwin" and shutil.which("sandbox-exec"):
        return "seatbelt"
    if system == "Linux" and _bwrap_usable():
        return "bubblewrap"
    return "none"


def sandbox() -> dict:
    """A functional probe of the host sandbox (`spec/verification.md`)."""
    return {
        "backend": sandbox_backend(),
        "platform": platform.system().lower(),
        "machine": platform.machine(),
        "runtime": f"{platform.python_implementation()} {platform.python_version()}",
    }


# -- Building the confined invocation -----------------------------------


def _quote_sb(s: str) -> str:
    """Escape a string literal for embedding in a seatbelt profile."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _seatbelt_profile(workspace: str, scratch: str) -> str:
    paths = [os.path.realpath(workspace)]
    if scratch:
        real_scratch = os.path.realpath(scratch)
        if real_scratch not in paths:
            paths.append(real_scratch)
    subpaths = "\n".join(f'  (subpath "{_quote_sb(p)}")' for p in paths)
    return (
        "(version 1)\n"
        "(deny default)\n"
        "(allow process-fork)\n"
        "(allow process-exec*)\n"
        "(allow signal (target same-sandbox))\n"
        "(allow file-read*)\n"
        "(allow file-write*\n"
        f"{subpaths}\n"
        '  (literal "/dev/null")\n'
        '  (literal "/dev/tty")\n'
        '  (literal "/dev/stdout")\n'
        '  (literal "/dev/stderr"))\n'
        "(allow file-ioctl)\n"
        "(allow sysctl-read)\n"
        "(allow mach-lookup)\n"
    )


def _bwrap_argv(workspace: str, scratch: str) -> list:
    real_ws = os.path.realpath(workspace)
    argv = [
        "bwrap",
        "--ro-bind", "/", "/",
        "--dev", "/dev",
        "--proc", "/proc",
        "--tmpfs", "/tmp",
        "--bind", real_ws, real_ws,
        "--unshare-net",
        "--die-with-parent",
        "--chdir", real_ws,
    ]
    if scratch:
        real_scratch = os.path.realpath(scratch)
        if real_scratch != real_ws and not real_scratch.startswith(real_ws + os.sep):
            argv += ["--bind", real_scratch, real_scratch]
    return argv


def _sandbox_argv(backend: str, workspace: str, scratch: str, cmd: str) -> list:
    """The argv that runs `cmd` under `backend` (or plain, for none/inherited)."""
    if backend == "seatbelt":
        profile = _seatbelt_profile(workspace, scratch)
        return ["/usr/bin/sandbox-exec", "-p", profile, core._SHELL, "-c", cmd]
    if backend == "bubblewrap":
        return _bwrap_argv(workspace, scratch) + [core._SHELL, "-c", cmd]
    return [core._SHELL, "-c", cmd]


def _scrub_env() -> dict:
    """A minimal host allowlist plus the claim's own variables."""
    env = {k: os.environ[k] for k in core._KEEP_ENV if k in os.environ}
    env.setdefault("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")
    return env


# -- Running a process, bounded, and killing the whole tree on timeout --


def _kill_tree(proc: subprocess.Popen) -> None:
    """Kill `proc` and every descendant it spawned."""
    try:
        pgid = os.getpgid(proc.pid)
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
        except OSError:
            pass


def _run(argv: list, cwd: str, env: dict, timeout: float) -> dict:
    """Run `argv`, bounded by `timeout`; never raises for a timeout."""
    proc = subprocess.Popen(
        argv, cwd=cwd, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        out, err = proc.communicate(timeout=timeout)
        return {"returncode": proc.returncode, "stdout": out, "stderr": err,
                "timed_out": False}
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        out, err = proc.communicate()
        return {"returncode": None, "stdout": out, "stderr": err,
                "timed_out": True}


def gate_timeout(recipe) -> float:
    """The declared ceiling IS the ceiling: it may raise past any default,
    and a gate past it still times out (`spec/claim-format.md`).
    """
    claim = (recipe or {}).get("claim", {})
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


def run_gate(cmd: str, workspace: str, recipe=None) -> dict:
    """Run one gate: scrubbed env, sandboxed, bounded (`spec/claim-format.md`)."""
    backend = sandbox_backend()
    timeout = gate_timeout(recipe)
    env = _scrub_env()

    scratch = os.path.join(workspace, core.STORE, "room")
    os.makedirs(scratch, exist_ok=True)
    if backend not in ("none", "inherited"):
        env["TMPDIR"] = scratch
        env["HOME"] = scratch
        env[core._JAILED] = "1"

    argv = _sandbox_argv(backend, workspace, scratch, cmd)
    result = _run(argv, workspace, env, timeout)

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
        "stdout": result["stdout"].decode("utf-8", "replace"),
        "stderr": result["stderr"].decode("utf-8", "replace"),
    }


# -- The environment contract: `requires`, and furnishing `environment` --


def _have(name: str) -> bool:
    """Is `name` available: a binary on `PATH`, or an importable module?"""
    if shutil.which(name):
        return True
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError, ModuleNotFoundError):
        return False


def _version_tuple(s: str) -> tuple:
    """Dotted version text to a tuple of ints, ignoring non-numeric suffixes."""
    parts = []
    for chunk in s.split("."):
        digits = ""
        for ch in chunk:
            if ch.isdigit():
                digits += ch
            else:
                break
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def _version_ok(actual: str, op: str, required: str) -> bool:
    """Does `actual` satisfy `op required` under the pinned `_REQ_OPS`?"""
    if op == "~=":
        at = _version_tuple(actual)
        rt = _version_tuple(required)
        if len(rt) < 2:
            return at[: len(rt)] == rt
        return at[: len(rt) - 1] == rt[:-1] and at >= rt
    fn = _VERSION_COMPARE.get(op)
    if fn is None:
        raise ClaimError(f"unknown version operator {op!r}")
    return fn(_version_tuple(actual), _version_tuple(required))


def _tool_version(name: str):
    """Best-effort version of `name`: package metadata, `--version`, or
    `__version__`. `None` if it cannot be determined.
    """
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        pass
    path = shutil.which(name)
    if path:
        try:
            out = subprocess.run(
                [path, "--version"], stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, timeout=5, text=True,
            )
            m = re.search(r"\d+(?:\.\d+)+", out.stdout)
            if m:
                return m.group(0)
        except (OSError, subprocess.SubprocessError):
            pass
    try:
        mod = importlib.import_module(name)
        v = getattr(mod, "__version__", None)
        if v:
            return str(v)
    except ImportError:
        pass
    return None


def _split_requirement(req: str):
    """`"name>=1.2"` to `("name", ">=", "1.2")`; `("name", None, None)` if bare."""
    for op in _REQ_OPS:
        idx = req.find(op)
        if idx != -1:
            return req[:idx].strip(), op, req[idx + len(op):].strip()
    return req.strip(), None, None


def preflight(recipe: dict) -> list:
    """Which of the claim's declared `requires` are missing on this host."""
    claim = (recipe or {}).get("claim", {})
    missing = []
    for req in claim.get("requires", []):
        name, op, version = _split_requirement(req)
        if not _have(name):
            missing.append(req)
            continue
        if op and version:
            actual = _tool_version(name)
            if actual is None or not _version_ok(actual, op, version):
                missing.append(req)
    return missing


def _env_cache_dir() -> str:
    """Where furnished venvs are cached, host residue outside identity."""
    override = os.environ.get(core._ENV_CACHE)
    if override:
        return override
    return os.path.join(os.path.expanduser("~"), ".cache", "reticuli", "envs")


def furnish(recipe: dict, d: str):
    """Build (or reuse) a private venv for the claim's declared `environment`.

    `None` when the claim declares none. Cached per (file digest,
    interpreter, platform). A room that cannot be furnished refuses as a
    `ClaimError` -- an environment failure, never a verdict
    (`spec/claim-format.md`).
    """
    claim = (recipe or {}).get("claim", {})
    env_file = claim.get("environment")
    if not env_file:
        return None

    path = core._safe(d, env_file)
    if not os.path.isfile(path):
        raise ClaimError(f"environment file not found: {env_file!r}")

    digest = core._hash_file(path)
    key = "-".join((
        digest, platform.python_version(), platform.system().lower(),
        platform.machine(),
    ))
    cache_dir = os.path.join(_env_cache_dir(), key)
    venv_bin = os.path.join(cache_dir, "bin")
    if os.path.isdir(venv_bin):
        return venv_bin

    os.makedirs(_env_cache_dir(), exist_ok=True)
    tmp_dir = cache_dir + ".tmp"
    shutil.rmtree(tmp_dir, ignore_errors=True)
    try:
        subprocess.run(
            [sys.executable, "-m", "venv", tmp_dir],
            check=True, timeout=core.FURNISH_TIMEOUT,
        )
        pip = os.path.join(tmp_dir, "bin", "pip")
        subprocess.run(
            [pip, "install", "--require-hashes", "--only-binary=:all:",
             "-r", path],
            check=True, timeout=core.FURNISH_TIMEOUT,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise ClaimError(f"cannot furnish environment {env_file!r}: {e}") from e

    os.replace(tmp_dir, cache_dir)
    return venv_bin


# -- Producer independence (observational, never enforced) --------------


def _independence_line(established: bool, m1_vendor, m3_vendor) -> str:
    if not m1_vendor or not m3_vendor:
        return "independence unestablished: producer vendor not recorded"
    if not established:
        return f"independence unestablished: same vendor ({m3_vendor})"
    return f"independence established: {m1_vendor} vs {m3_vendor}"


def independence(m1: dict, m3: dict) -> dict:
    """Declared producer independence of a crosscheck: recorded, not enforced."""
    v1 = (m1 or {}).get("vendor")
    v3 = (m3 or {}).get("vendor")
    established = bool(v1) and bool(v3) and v1 != v3
    return {
        "established": established,
        "m1_vendor": v1,
        "m3_vendor": v3,
        "line": _independence_line(established, v1, v3),
    }


# -- The cost ledger ------------------------------------------------------


def _ledger_path(d: str) -> str:
    return core._safe(d, core.LEDGER)


def ledger(d: str, entry: dict) -> None:
    """Append one entry to the claim's cost ledger."""
    path = _ledger_path(d)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    record = dict(entry)
    record.setdefault("when", core._now())
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True))
        f.write("\n")


def ledger_events(d: str) -> list:
    """Every entry recorded in the claim's cost ledger, in order."""
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
    """Ledger totals per unit; `None` if nothing was measured.

    `seconds` is the kernel's own measurement and is never accepted from a
    producer-reported (`kind == "producer"`) entry.
    """
    totals = {}
    for e in ledger_events(d):
        for key in ("usd", "tokens", "calls"):
            v = e.get(key)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                totals[key] = totals.get(key, 0) + v
        if e.get("kind") != "producer":
            v = e.get("seconds")
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                totals["seconds"] = totals.get("seconds", 0) + v
    return totals or None
