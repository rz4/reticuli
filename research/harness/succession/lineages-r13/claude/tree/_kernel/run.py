"""Kernel-run: gate execution, confined and timed, and the cost ledger.

`run_gate` runs one gate under a platform sandbox: a scrubbed environment, a
functionally-probed confinement (macOS `sandbox-exec` / Linux `bwrap`, "none"
when neither works), and a wall-clock bound that `gate_timeout` derives from
the claim's own declaration -- the declared ceiling, not an implementation
default that might undercut it. `ledger` appends what a run cost; `cost`
totals the ledger. `furnish` builds the private venv a declared `environment`
asks for. `preflight` checks the claim's `requires` against this host.
"""
import importlib
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import tempfile

from . import core

SANDBOXES = frozenset({"none", "seatbelt", "bubblewrap", "inherited"})

_REQ_OPS = ('<=', '>=', '==', '!=', '~=', '<', '>')

# Functional-probe caches: None until the first probe, then sticky.
_BWRAP_OK = None
_SEATBELT_OK = None


# ---------------------------------------------------------------- sandbox --

def _in_band() -> bool:
    """Whether this process is already running inside a sandbox -- the
    signal a wrapped gate must inherit rather than nest under."""
    return bool(os.environ.get(core._JAILED))


def _quote_sb(s: str) -> str:
    """Quote a literal for an SBPL double-quoted string."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _seatbelt_profile(writable) -> str:
    """An SBPL profile: deny by default, but permit everything the jail's
    floor requires -- subprocess spawn, /dev sinks, reads anywhere (the
    interpreter and the host live out there) -- and permit writes only under
    the given paths. Network stays denied by the default-deny; nothing here
    allows it."""
    lines = [
        "(version 1)",
        "(deny default)",
        "(allow process-fork)",
        "(allow process-exec)",
        "(allow signal)",
        "(allow sysctl-read)",
        "(allow mach-lookup)",
        "(allow iokit-open)",
        "(allow file-read*)",
        '(allow file-write-data file-ioctl (subpath "/dev"))',
    ]
    for path in writable:
        lines.append('(allow file-write* (subpath "%s"))' % _quote_sb(path))
    return "\n".join(lines)


def _seatbelt_usable() -> bool:
    """Functional probe: sandbox-exec must both let a gate write where it
    should and refuse where it should not. A present-but-broken sandbox
    counts as none, honestly reported."""
    global _SEATBELT_OK
    if _SEATBELT_OK is not None:
        return _SEATBELT_OK
    if platform.system() != "Darwin" or not shutil.which("sandbox-exec"):
        _SEATBELT_OK = False
        return False
    probe = tempfile.mkdtemp(prefix="reticuli-sbprobe-")
    try:
        real = os.path.realpath(probe)
        profile = _seatbelt_profile([real])
        try:
            allowed = subprocess.run(
                ["/usr/bin/sandbox-exec", "-p", profile, "/bin/sh", "-c",
                 "printf x > ok"],
                cwd=real, capture_output=True, timeout=10,
            )
            denied = subprocess.run(
                ["/usr/bin/sandbox-exec", "-p", profile, "/bin/sh", "-c",
                 "printf x > /denied-by-reticuli-probe"],
                cwd=real, capture_output=True, timeout=10,
            )
            _SEATBELT_OK = (
                allowed.returncode == 0
                and os.path.isfile(os.path.join(real, "ok"))
                and denied.returncode != 0
            )
        except (OSError, subprocess.TimeoutExpired):
            _SEATBELT_OK = False
    finally:
        shutil.rmtree(probe, ignore_errors=True)
    return _SEATBELT_OK


def _bwrap_usable() -> bool:
    """Functional probe for Linux bubblewrap, cached in `_BWRAP_OK`."""
    global _BWRAP_OK
    if _BWRAP_OK is not None:
        return _BWRAP_OK
    if not shutil.which("bwrap"):
        _BWRAP_OK = False
        return False
    try:
        r = subprocess.run(
            ["bwrap", "--unshare-net", "--ro-bind", "/", "/", "--", "/bin/true"],
            capture_output=True, timeout=10,
        )
        _BWRAP_OK = (r.returncode == 0)
    except (OSError, subprocess.TimeoutExpired):
        _BWRAP_OK = False
    return _BWRAP_OK


def sandbox() -> dict:
    """A functional probe of the host sandbox."""
    if _in_band():
        return {"backend": "inherited"}
    system = platform.system()
    if system == "Darwin" and _seatbelt_usable():
        return {"backend": "seatbelt"}
    if system == "Linux" and _bwrap_usable():
        return {"backend": "bubblewrap"}
    return {"backend": "none"}


def sandbox_backend() -> str:
    """Which sandbox backend `run_gate` will apply (or "inherited" / "none")."""
    return sandbox()["backend"]


def _bwrap_argv(real: str, home: str, tmp: str) -> list:
    return [
        "bwrap",
        "--unshare-net",
        "--die-with-parent",
        "--dev", "/dev",
        "--proc", "/proc",
        "--ro-bind", "/", "/",
        "--bind", real, real,
        "--bind", home, home,
        "--bind", tmp, tmp,
        "--chdir", real,
        "--",
    ]


def _sandbox_argv(backend: str, argv: list, d: str, home: str, tmp: str) -> list:
    """Wrap `argv` to run confined under `backend`; "none"/"inherited" pass
    it through unchanged."""
    real = os.path.realpath(d)
    if backend == "seatbelt":
        profile = _seatbelt_profile([real])
        return ["/usr/bin/sandbox-exec", "-p", profile] + list(argv)
    if backend == "bubblewrap":
        return _bwrap_argv(real, home, tmp) + list(argv)
    return list(argv)


def _scrub_env(home=None, tmp=None) -> dict:
    """A minimal host allowlist; HOME/TMPDIR are redirected only when a real
    sandbox is applied (inheriting the host's would hand the gate paths the
    sandbox forbids it to write)."""
    env = {k: os.environ[k] for k in core._KEEP_ENV if k in os.environ}
    if home is not None:
        env["HOME"] = home
    if tmp is not None:
        env["TMPDIR"] = tmp
    return env


# -------------------------------------------------------------- execution --

def _kill_tree(pid: int) -> None:
    """Kill a timed-out gate and everything it spawned."""
    try:
        os.killpg(os.getpgid(pid), signal.SIGKILL)
        return
    except (ProcessLookupError, PermissionError, OSError):
        pass
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


def _run(argv: list, cwd: str, env: dict, timeout: float):
    """Run `argv`, bounded by `timeout`. Returns (returncode, stdout, stderr,
    timed_out); `returncode` is `None` exactly when `timed_out` is true."""
    proc = subprocess.Popen(
        argv, cwd=cwd, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        out, err = proc.communicate(timeout=timeout)
        return proc.returncode, out, err, False
    except subprocess.TimeoutExpired:
        _kill_tree(proc.pid)
        try:
            out, err = proc.communicate(timeout=5)
        except Exception:
            out, err = b"", b""
        return None, out, err, True


def gate_timeout(recipe) -> float:
    """The effective wall-clock bound: the claim's declared `gate_timeout`
    IS the ceiling (it may raise or lower the implementation default), capped
    only by `RETICULI_GATE_TIMEOUT` when the host sets one."""
    claim = ((recipe or {}).get("claim") or {})
    declared = claim.get("gate_timeout")
    base = float(declared) if declared is not None else core.GATE_TIMEOUT
    cap = os.environ.get(core._ENV_TIMEOUT)
    if cap is not None:
        try:
            return min(base, float(cap))
        except ValueError:
            pass
    return base


def run_gate(cmd: str, d: str, recipe) -> dict:
    """One gate: scrubbed env, sandboxed, bounded by `gate_timeout`."""
    timeout = gate_timeout(recipe)
    backend = sandbox_backend()
    real = os.path.realpath(d)
    real_jail = backend in ("seatbelt", "bubblewrap")

    home = tmp = None
    if real_jail:
        room = os.path.join(real, core.STORE, "room")
        home = os.path.join(room, "home")
        tmp = os.path.join(room, "tmp")
        os.makedirs(home, exist_ok=True)
        os.makedirs(tmp, exist_ok=True)

    env = _scrub_env(home, tmp)
    if real_jail:
        env[core._JAILED] = "1"

    argv = _sandbox_argv(backend, [core._SHELL, "-c", cmd], real, home, tmp)
    code, out, err, timed_out = _run(argv, real, env, timeout)

    if timed_out:
        status = "timeout"
    elif code == 0:
        status = "ok"
    else:
        status = "failed"

    return {
        "status": status,
        "quarantine": backend,
        "stdout": out.decode("utf-8", "replace"),
        "stderr": err.decode("utf-8", "replace"),
    }


# --------------------------------------------------------------- ledger --

def _ledger_path(d: str) -> str:
    return os.path.join(d, core.LEDGER)


def ledger(d: str, entry: dict) -> None:
    """Append one ledger entry: what a run cost."""
    path = _ledger_path(d)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    record = dict(entry)
    record.setdefault("when", core._now())
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True))
        f.write("\n")


def ledger_events(d: str) -> list:
    """Every ledger entry recorded so far, in append order."""
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
    """Ledger totals per unit; `None` if nothing was measured. Totals carry
    only the keys the ledger names -- an unmeasured unit is never guessed at."""
    totals = {}
    for event in ledger_events(d):
        for key in core.COST_KEYS:
            value = event.get(key)
            if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            totals[key] = totals.get(key, 0) + value
    return totals or None


# ------------------------------------------------------------ environment --

def _env_cache_dir() -> str:
    """Where furnished venvs are cached, keyed by (file digest, interpreter,
    platform) by the caller -- host residue, never identity."""
    cache = os.environ.get(core._ENV_CACHE)
    if cache:
        return cache
    return os.path.join(tempfile.gettempdir(), "reticuli-envs")


def furnish(d: str, recipe) -> dict:
    """Build (or reuse) a private venv from the claim's declared
    `environment` file. No declaration means nothing to furnish."""
    claim = ((recipe or {}).get("claim") or {})
    env_file = claim.get("environment")
    if not env_file:
        return {"status": "ok", "venv": None}

    try:
        path = core._safe(d, env_file)
    except core.ClaimError as exc:
        return {"status": "environment", "reason": str(exc)}
    if not os.path.isfile(path):
        return {"status": "environment",
                 "reason": f"missing environment file {env_file!r}"}

    import sys as _sys
    digest = core._hash_file(path)
    key = "-".join([
        digest,
        f"{_sys.implementation.name}{_sys.version_info[0]}.{_sys.version_info[1]}",
        platform.system().lower(),
        platform.machine(),
    ])
    venv_dir = os.path.join(_env_cache_dir(), key)
    if os.path.isdir(venv_dir):
        return {"status": "ok", "venv": venv_dir}

    try:
        os.makedirs(_env_cache_dir(), exist_ok=True)
        subprocess.run([_sys.executable, "-m", "venv", venv_dir],
                        check=True, capture_output=True, timeout=core.FURNISH_TIMEOUT)
        pip = os.path.join(venv_dir, "bin", "pip")
        subprocess.run([pip, "install", "--require-hashes", "--only-binary=:all:",
                         "-r", path],
                        check=True, capture_output=True, timeout=core.FURNISH_TIMEOUT)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        shutil.rmtree(venv_dir, ignore_errors=True)
        return {"status": "environment", "reason": str(exc)}
    return {"status": "ok", "venv": venv_dir}


def _have(name: str) -> bool:
    """Whether a binary (on PATH) or an importable Python module is present."""
    if shutil.which(name):
        return True
    try:
        importlib.import_module(name)
        return True
    except ImportError:
        return False


def _split_requirement(req: str):
    """Split "name<op>version" on the first operator found; a bare name has
    no operator. Two-character operators are tried before one-character ones
    so "python>=3.8" doesn't split on a bare ">"."""
    for op in _REQ_OPS:
        idx = req.find(op)
        if idx != -1:
            return req[:idx].strip(), op, req[idx + len(op):].strip()
    return req.strip(), None, None


def _version_tuple(version: str) -> tuple:
    """A dotted version string as a tuple of leading-digit ints, stopping at
    the first component that carries no digits."""
    parts = []
    for piece in version.split("."):
        digits = ""
        for ch in piece:
            if ch.isdigit():
                digits += ch
            else:
                break
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def _tool_version(name: str):
    """The installed version of `name`, read from its own `--version` output."""
    for flag in ("--version", "-version", "-V"):
        try:
            r = subprocess.run([name, flag], capture_output=True, timeout=10, text=True)
        except (OSError, subprocess.TimeoutExpired):
            continue
        text = (r.stdout or "") + (r.stderr or "")
        match = re.search(r"\d+(?:\.\d+)+", text)
        if match:
            return match.group(0)
    return None


def _version_ok(installed: str, op: str, required: str) -> bool:
    a, b = _version_tuple(installed), _version_tuple(required)
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
        return len(b) >= 1 and a[:len(b) - 1] == b[:-1] and a >= b
    return True


def preflight(recipe) -> dict:
    """The environment contract: which of the claim's `requires` entries are
    missing on this host."""
    requires = ((recipe or {}).get("claim") or {}).get("requires", []) or []
    missing = []
    for req in requires:
        name, op, version = _split_requirement(req)
        if not _have(name):
            missing.append(req)
            continue
        if op is not None and version:
            installed = _tool_version(name)
            if installed is None or not _version_ok(installed, op, version):
                missing.append(req)
    return {"ok": not missing, "missing": missing}


# ------------------------------------------------------------ independence --

def _independence_line(established: bool) -> str:
    return "independent producer" if established else "independence unestablished"


def independence(m1, m3) -> dict:
    """Declared producer independence of a crosscheck: recorded, never
    enforced -- content cannot prove blindness."""
    m1 = m1 or {}
    m3 = m3 or {}
    same_vendor = bool(m1.get("vendor")) and m1.get("vendor") == m3.get("vendor")
    same_model = bool(m1.get("model")) and m1.get("model") == m3.get("model")
    established = not (same_vendor and same_model)
    return {"established": established, "note": _independence_line(established)}
