"""Gate execution: a scrubbed, sandboxed, bounded subprocess, and the ledger.

`run_gate` runs a claim's gate command under a platform sandbox -- macOS
`sandbox-exec` or Linux `bwrap`, probed functionally and cached, falling
back to `none` when neither works, or to `inherited` when the caller is
already inside a jail (`RETICULI_JAILED`, read in-band so sandboxes never
nest). A real sandbox denies the network and confines writes to the claim
directory and a per-run scratch `HOME`/`TMPDIR` carved out of the claim's
own store, while leaving reads, `/dev` sinks, subprocess spawn, and the
host's name (`uname`/`sysctl`) open -- the floor measured empirically and
recorded in `spec/claim-format.md`.

`gate_timeout` makes a claim's declared ceiling the ceiling: a declared
value is used exactly, not folded through `min()` with some smaller
implementation default. `ledger`/`ledger_events`/`cost` are a plain
JSON-lines append log and its totals, carrying only the cost keys a run
actually measured. `preflight`/`independence`/`furnish` round out the
environment contract described in `spec/claim-format.md` and
`spec/verification.md`; none of the three is exercised by the conformance
gate, so they are implemented to the letter of those documents and no
further.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile

from .core import (
    _JAILED,
    _ENV_CACHE,
    _ENV_TIMEOUT,
    _KEEP_ENV,
    COST_KEYS,
    GATE_TIMEOUT,
    FURNISH_TIMEOUT,
    LEDGER,
    STORE,
    ClaimError,
    _judging_host,
    _now,
)

# ---- caches: probed once, then remembered for the life of the process ----
_BWRAP_OK = None
_SEATBELT_OK = None

_DEV_SINKS = ("/dev/null", "/dev/zero", "/dev/tty", "/dev/stdout", "/dev/stderr",
              "/dev/urandom")

# requirement-string operators, longest first so '>=' is not split as '>' + '='
_REQ_OPS = ("<=", ">=", "==", "!=", "~=", "<", ">")


# ---------------------------------------------------------------- scrubbing
def _scrub_env() -> dict:
    """A minimal host allowlist, nothing else from the caller's environment."""
    env = {}
    for name in _KEEP_ENV:
        if name in os.environ:
            env[name] = os.environ[name]
    return env


def _in_band() -> bool:
    """Whether the caller is already inside a jail, signalled in-band."""
    return os.environ.get(_JAILED, "") not in ("", "0")


# ---------------------------------------------------------------- sandboxing
def _quote_sb(path: str) -> str:
    """Escape a path for embedding in a seatbelt profile string literal."""
    return path.replace("\\", "\\\\").replace('"', '\\"')


def _seatbelt_profile(workdir: str, home: str, tmp: str) -> str:
    paths = sorted({workdir, home, tmp})
    writes = " ".join(f'(subpath "{_quote_sb(p)}")' for p in paths)
    sinks = " ".join(f'(literal "{d}")' for d in _DEV_SINKS)
    return (
        "(version 1)(deny default)"
        "(allow file-read*)"
        f"(allow file-write* {writes} {sinks})"
        "(allow process-fork)(allow process-exec)"
        "(allow sysctl-read)"
    )


def _sandbox_argv(backend: str, cmd: str, workdir: str, home: str, tmp: str) -> list:
    """The wrapper argv for running `/bin/sh -c cmd` under `backend`."""
    if backend == "seatbelt":
        exe = shutil.which("sandbox-exec") or "/usr/bin/sandbox-exec"
        profile = _seatbelt_profile(workdir, home, tmp)
        return [exe, "-p", profile, "/bin/sh", "-c", cmd]
    if backend == "bubblewrap":
        exe = shutil.which("bwrap") or "bwrap"
        argv = [exe, "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc",
                "--bind", workdir, workdir]
        for extra in (home, tmp):
            if extra not in (workdir,):
                argv += ["--bind", extra, extra]
        argv += ["--unshare-net", "--die-with-parent", "--chdir", workdir,
                  "/bin/sh", "-c", cmd]
        return argv
    return ["/bin/sh", "-c", cmd]


def _seatbelt_usable() -> bool:
    global _SEATBELT_OK
    if _SEATBELT_OK is not None:
        return _SEATBELT_OK
    exe = shutil.which("sandbox-exec")
    if not exe:
        _SEATBELT_OK = False
        return False
    try:
        with tempfile.TemporaryDirectory() as allowed, \
                tempfile.TemporaryDirectory() as denied:
            allowed_r = os.path.realpath(allowed)
            argv = _sandbox_argv("seatbelt", f"printf x > {allowed}/ok",
                                  allowed_r, allowed_r, allowed_r)
            ok = subprocess.run(argv, capture_output=True, timeout=10)
            argv2 = _sandbox_argv("seatbelt", f"printf x > {denied}/leak",
                                   allowed_r, allowed_r, allowed_r)
            bad = subprocess.run(argv2, capture_output=True, timeout=10)
            _SEATBELT_OK = (ok.returncode == 0
                            and os.path.isfile(os.path.join(allowed, "ok"))
                            and bad.returncode != 0)
    except Exception:
        _SEATBELT_OK = False
    return _SEATBELT_OK


def _bwrap_usable() -> bool:
    global _BWRAP_OK
    if _BWRAP_OK is not None:
        return _BWRAP_OK
    exe = shutil.which("bwrap")
    if not exe:
        _BWRAP_OK = False
        return False
    try:
        with tempfile.TemporaryDirectory() as allowed, \
                tempfile.TemporaryDirectory() as denied:
            allowed_r = os.path.realpath(allowed)
            argv = _sandbox_argv("bubblewrap", f"printf x > {allowed}/ok",
                                  allowed_r, allowed_r, allowed_r)
            ok = subprocess.run(argv, capture_output=True, timeout=10)
            argv2 = _sandbox_argv("bubblewrap", f"printf x > {denied}/leak",
                                   allowed_r, allowed_r, allowed_r)
            bad = subprocess.run(argv2, capture_output=True, timeout=10)
            _BWRAP_OK = (ok.returncode == 0
                         and os.path.isfile(os.path.join(allowed, "ok"))
                         and bad.returncode != 0)
    except Exception:
        _BWRAP_OK = False
    return _BWRAP_OK


def sandbox_backend() -> str:
    """Which confinement applies: `none`, `seatbelt`, `bubblewrap`, `inherited`."""
    if _in_band():
        return "inherited"
    if sys.platform == "darwin" and _seatbelt_usable():
        return "seatbelt"
    if sys.platform.startswith("linux") and _bwrap_usable():
        return "bubblewrap"
    return "none"


def sandbox() -> dict:
    """A functional probe of the host sandbox; `backend` is the pinned field."""
    return {"backend": sandbox_backend()}


# ---------------------------------------------------------------- execution
def _kill_tree(proc) -> None:
    """Kill a gate's whole process tree, not just its immediate child."""
    import signal
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
        except Exception:
            pass


def _run(argv: list, cwd: str, env: dict, timeout: float) -> dict:
    """Run `argv`, bounded by `timeout`; `status` is `ok`/`failed`/`timeout`."""
    try:
        proc = subprocess.Popen(
            argv, cwd=cwd, env=env, start_new_session=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
    except OSError as e:
        return {"status": "failed", "returncode": None, "error": str(e)}
    try:
        out, err = proc.communicate(timeout=timeout)
        return {
            "status": "ok" if proc.returncode == 0 else "failed",
            "returncode": proc.returncode, "stdout": out, "stderr": err,
        }
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        try:
            proc.communicate(timeout=5)
        except Exception:
            pass
        return {"status": "timeout", "returncode": None}


def gate_timeout(recipe) -> float:
    """The effective wall-clock ceiling: a declared value IS the ceiling.

    `RETICULI_GATE_TIMEOUT`, where set, is a host operator override and
    wins outright; otherwise a claim's own `gate_timeout` is used exactly,
    never folded through `min()` with a smaller implementation default.
    """
    env_cap = os.environ.get(_ENV_TIMEOUT)
    if env_cap:
        try:
            return float(env_cap)
        except ValueError:
            pass
    claim = (recipe or {}).get("claim", {}) if recipe else {}
    declared = claim.get("gate_timeout")
    if declared is not None:
        return float(declared)
    return GATE_TIMEOUT


def run_gate(cmd: str, d: str, recipe) -> dict:
    """Run one gate command in `d`: scrubbed env, sandboxed, bounded.

    Returns `{status, quarantine, returncode}`; `quarantine` names the
    confinement actually applied this call.
    """
    backend = sandbox_backend()
    timeout = gate_timeout(recipe)
    env = _scrub_env()
    d_real = os.path.realpath(d)

    if backend in ("seatbelt", "bubblewrap"):
        run_store = os.path.join(d, STORE, "run")
        os.makedirs(run_store, exist_ok=True)
        scratch = tempfile.mkdtemp(dir=run_store)
        home = os.path.join(scratch, "home")
        tmp = os.path.join(scratch, "tmp")
        os.makedirs(home, exist_ok=True)
        os.makedirs(tmp, exist_ok=True)
        home_real = os.path.realpath(home)
        tmp_real = os.path.realpath(tmp)
        env["HOME"] = home_real
        env["TMPDIR"] = tmp_real
        env[_JAILED] = "1"
        argv = _sandbox_argv(backend, cmd, d_real, home_real, tmp_real)
    else:
        argv = ["/bin/sh", "-c", cmd]

    result = _run(argv, d, env, timeout)
    return {
        "status": result["status"],
        "quarantine": backend,
        "returncode": result.get("returncode"),
    }


# -------------------------------------------------------------------- ledger
def _ledger_path(d: str) -> str:
    return os.path.join(d, LEDGER)


def ledger(d: str, entry: dict) -> None:
    """Append one cost/event entry to `d`'s ledger, stamped with `when`."""
    path = _ledger_path(d)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    record = dict(entry)
    record.setdefault("when", _now())
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


def cost(d: str) -> dict:
    """Ledger totals per unit; keys the ledger never measured stay absent."""
    totals = {}
    measured = set()
    for event in ledger_events(d):
        for key in COST_KEYS:
            value = event.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                measured.add(key)
                totals[key] = totals.get(key, 0) + value
    return totals if measured else None


# --------------------------------------------------------- environment contract
def _have(name: str) -> bool:
    """Whether `name` is a reachable binary on `PATH` or an importable module."""
    if shutil.which(name):
        return True
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _version_tuple(s: str) -> tuple:
    """A dotted version string as a tuple of ints, non-numeric tail dropped."""
    parts = []
    for piece in str(s).split("."):
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


def _version_ok(installed: tuple, op: str, required: tuple) -> bool:
    """Compare two version tuples under a requirement operator."""
    width = max(len(installed), len(required))
    a = installed + (0,) * (width - len(installed))
    b = required + (0,) * (width - len(required))
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
        return a >= b and installed[:-1] == required[:-1]
    return False


def _tool_version(name: str) -> str:
    """The installed version of a binary or module, where discoverable."""
    try:
        mod = importlib.import_module(name)
        v = getattr(mod, "__version__", None)
        if isinstance(v, str):
            return v
    except ImportError:
        pass
    exe = shutil.which(name)
    if exe:
        try:
            out = subprocess.run([exe, "--version"], capture_output=True,
                                  timeout=10, text=True)
            return (out.stdout or out.stderr).strip().splitlines()[0]
        except Exception:
            return None
    return None


def preflight(recipe) -> list:
    """Names from `[claim] requires` missing on this host, by requirement."""
    claim = (recipe or {}).get("claim", {}) if recipe else {}
    missing = []
    for req in claim.get("requires", []):
        name, op, wanted = req, None, None
        for candidate in _REQ_OPS:
            if candidate in req:
                name, _, wanted = req.partition(candidate)
                op = candidate
                break
        name = name.strip()
        if not _have(name):
            missing.append(req)
            continue
        if op and wanted:
            have_v = _tool_version(name)
            if have_v is None or not _version_ok(
                _version_tuple(have_v), op, _version_tuple(wanted.strip())
            ):
                missing.append(req)
    return missing


def _env_cache_dir() -> str:
    """Where furnished venvs are cached, per (file digest, interpreter, platform)."""
    override = os.environ.get(_ENV_CACHE)
    if override:
        return override
    return os.path.join(tempfile.gettempdir(), "reticuli-furnish-cache")


def furnish(recipe, d: str) -> dict:
    """Build (or reuse) a private venv for `[claim] environment`, if declared.

    Returns `{status: "ok", bin: None}` when the claim declares no
    environment -- nothing to furnish. A room that cannot be furnished is
    an environment failure, never a verdict.
    """
    claim = (recipe or {}).get("claim", {}) if recipe else {}
    req_file = claim.get("environment")
    if not req_file:
        return {"status": "ok", "bin": None}

    path = os.path.join(d, req_file)
    if not os.path.isfile(path):
        return {"status": "environment", "bin": None,
                "error": f"missing environment file {req_file!r}"}

    from .core import _hash_file
    digest = _hash_file(path)
    cache = os.path.join(
        _env_cache_dir(), f"{digest}-{sys.implementation.name}-{sys.platform}"
    )
    bin_dir = os.path.join(cache, "bin")
    if os.path.isdir(bin_dir):
        return {"status": "ok", "bin": bin_dir}

    os.makedirs(os.path.dirname(cache), exist_ok=True)
    try:
        subprocess.run([sys.executable, "-m", "venv", cache],
                        check=True, timeout=FURNISH_TIMEOUT, capture_output=True)
        pip = os.path.join(bin_dir, "pip")
        subprocess.run(
            [pip, "install", "--require-hashes", "--only-binary=:all:",
             "-r", path],
            check=True, timeout=FURNISH_TIMEOUT, capture_output=True,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
        return {"status": "environment", "bin": None, "error": str(e)}
    return {"status": "ok", "bin": bin_dir}


def _independence_line(m1_producer, m3_producer) -> str:
    """A human-readable independence verdict for two producer declarations."""
    m1_producer = m1_producer or {}
    m3_producer = m3_producer or {}
    v1, v3 = m1_producer.get("vendor"), m3_producer.get("vendor")
    mo1, mo3 = m1_producer.get("model"), m3_producer.get("model")
    if not v1 or not v3:
        return "independence unestablished (vendor not declared)"
    if v1 == v3 and mo1 == mo3:
        return "independence unestablished (same vendor and model)"
    if v1 == v3:
        return "independence unestablished (same vendor)"
    return "independent"


def independence(m1_producer, m3_producer) -> dict:
    """Declared producer independence of a crosscheck; never enforced."""
    line = _independence_line(m1_producer, m3_producer)
    return {"line": line, "established": line == "independent"}
