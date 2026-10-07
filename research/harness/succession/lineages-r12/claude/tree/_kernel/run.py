"""Gate execution: scrubbed, sandboxed, bounded (spec/claim-format.md).

`run_gate` runs one gate command under a functionally-probed platform
sandbox (macOS `sandbox-exec`, Linux `bwrap`, or `none` when neither is
usable -- `inherited` when already jailed, so sandboxes never nest), with a
scrubbed environment and a wall-clock bound. `ledger`/`ledger_events`/`cost`
are the cost bookkeeping a rebuild appends to and a crosscheck totals.
`gate_timeout` resolves the effective per-gate ceiling: a claim's own
declaration IS that ceiling, in both directions -- it may raise the bound
past this module's default, and a run past it still times out; only an
operator-set host cap (`RETICULI_GATE_TIMEOUT`) can pull it back down.
`preflight`/`furnish` are the environment contract (`[claim] requires`,
`[claim] environment`); `independence` is the crosscheck's declared-not-
enforced producer-independence observation.

Stdlib only, never the network.
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

_REQ_OPS = ("<=", ">=", "==", "!=", "~=", "<", ">")
_REQ_RE = re.compile(
    r"^([A-Za-z0-9_.+\-]+)\s*(?:(<=|>=|==|!=|~=|<|>)\s*([A-Za-z0-9_.\-]+))?$"
)

# Memoized result of the functional bwrap probe; None until first probed.
_BWRAP_OK = None


# -- host-facing primitives -------------------------------------------------

def _have(name: str) -> bool:
    """Is `name` present on this host -- a binary on PATH, or an importable
    Python module?"""
    if shutil.which(name):
        return True
    try:
        import importlib.util
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError, ModuleNotFoundError):
        return False


def _version_tuple(v: str) -> tuple:
    """A dotted version string as a tuple, numeric components compared
    numerically."""
    out = []
    for part in v.split("."):
        try:
            out.append(int(part))
        except ValueError:
            out.append(part)
    return tuple(out)


def _version_ok(have: str, op: str, want: str) -> bool:
    """Does an installed version satisfy one pip-style requirement operator?"""
    h, w = _version_tuple(have), _version_tuple(want)
    try:
        if op == "==":
            return h == w
        if op == "!=":
            return h != w
        if op == "<=":
            return h <= w
        if op == ">=":
            return h >= w
        if op == "<":
            return h < w
        if op == ">":
            return h > w
        if op == "~=":
            return h[:-1] == w[:-1] and h >= w
    except TypeError:
        return have == want
    return True


def _parse_requirement(req: str):
    """One `[claim] requires` entry as `(name, op, version)`; `op`/`version`
    are `None` when the entry is a bare name."""
    m = _REQ_RE.match(req.strip())
    if not m:
        return req.strip(), None, None
    name, op, want = m.groups()
    if op is not None and op not in _REQ_OPS:
        return name, None, None
    return name, op, want


def _tool_version(name: str):
    """The installed version of a Python module or a binary's `--version`
    output; `None` when it cannot be determined."""
    try:
        import importlib.metadata
        return importlib.metadata.version(name)
    except Exception:
        pass
    exe = shutil.which(name)
    if not exe:
        return None
    for flag in ("--version", "-V"):
        try:
            done = subprocess.run([exe, flag], capture_output=True, text=True,
                                   timeout=10, check=False)
        except OSError:
            continue
        m = re.search(r"\d+(?:\.\d+)+", done.stdout + done.stderr)
        if m:
            return m.group(0)
    return None


def _in_band(fn, *args, **kwargs):
    """Call `fn`, turning an unexpected host-level failure into a `ClaimError`
    -- a refusal belongs in band, with a reason, never as a raw traceback."""
    try:
        return fn(*args, **kwargs)
    except core.ClaimError:
        raise
    except (OSError, subprocess.SubprocessError, ValueError) as e:
        raise core.ClaimError(f"refused: {e}") from e


def preflight(recipe: dict) -> list:
    """Missing `[claim] requires` entries -- the host cannot judge this
    claim; distinct from the claim being wrong (spec/verification.md)."""
    claim = (recipe or {}).get("claim", {})
    missing = []
    for req in claim.get("requires", []):
        name, op, want = _parse_requirement(req)
        if not _have(name):
            missing.append(req)
            continue
        if op and want:
            got = _tool_version(name)
            if got is None or not _version_ok(got, op, want):
                missing.append(req)
    return missing


def _env_cache_dir(d: str) -> str:
    """Where furnished venvs are cached: host residue, never identity."""
    base = os.environ.get(core._ENV_CACHE) or os.path.join(
        os.path.expanduser("~"), ".cache", "reticuli", "env"
    )
    os.makedirs(base, exist_ok=True)
    return base


def furnish(d: str, recipe: dict) -> dict:
    """Build (or reuse) a private venv for `[claim] environment`.

    `--require-hashes`, `--only-binary=:all:` -- nothing unnamed can arrive,
    nothing executes at install time. Returns `{"path": <bin dir>}` to put
    first on the gate's `PATH`, or `{}` when the claim declares no
    environment. A furnish failure is a `ClaimError`; the caller classifies
    that as an `environment` gate outcome, never a verdict.
    """
    claim = (recipe or {}).get("claim", {})
    env_file = claim.get("environment")
    if not env_file:
        return {}
    full = core._safe(d, env_file)
    digest = core._hash_file(full)
    interp = f"{platform.python_implementation()}-{platform.python_version()}"
    venv_dir = os.path.join(_env_cache_dir(d), f"{digest}-{interp}-{sys.platform}")
    bin_dir = os.path.join(venv_dir, "bin")
    if os.path.isdir(venv_dir):
        return {"path": bin_dir}
    tmp_venv = venv_dir + ".tmp"
    shutil.rmtree(tmp_venv, ignore_errors=True)
    try:
        subprocess.run([sys.executable, "-m", "venv", tmp_venv],
                        check=True, capture_output=True,
                        timeout=core.FURNISH_TIMEOUT)
        pip = os.path.join(tmp_venv, "bin", "pip")
        subprocess.run(
            [pip, "install", "--require-hashes", "--only-binary=:all:",
             "-r", full],
            check=True, capture_output=True, timeout=core.FURNISH_TIMEOUT,
        )
    except (subprocess.CalledProcessError, OSError, subprocess.TimeoutExpired) as e:
        shutil.rmtree(tmp_venv, ignore_errors=True)
        raise core.ClaimError(f"refused: could not furnish environment: {e}") from e
    os.replace(tmp_venv, venv_dir)
    return {"path": bin_dir}


def independence(m1: dict, m3: dict) -> dict:
    """Declared producer independence of a crosscheck: an observation,
    never enforced -- content cannot prove blindness."""
    p1 = (m1 or {}).get("producer", {}) or {}
    p3 = (m3 or {}).get("producer", {}) or {}
    line = _independence_line(p1.get("vendor"), p1.get("model"),
                               p3.get("vendor"), p3.get("model"))
    return {"line": line, "established": line.startswith("independent")}


def _independence_line(vendor1, model1, vendor2, model2) -> str:
    if not vendor1 or not vendor2:
        return "independence unestablished: vendor not declared"
    if vendor1 == vendor2:
        return "independence unestablished: same vendor"
    return f"independent: {vendor1}/{model1} vs {vendor2}/{model2}"


# -- the sandboxes ------------------------------------------------------

def _quote_sb(s: str) -> str:
    """Escape a path for embedding in a seatbelt profile string literal."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _seatbelt_profile(d: str, scratch) -> str:
    paths = [os.path.realpath(d)]
    if scratch:
        paths.append(os.path.realpath(scratch))
    allows = "\n".join(
        f'(allow file-write* (subpath "{_quote_sb(p)}"))' for p in paths
    )
    return (
        "(version 1)\n"
        "(allow default)\n"
        "(deny network*)\n"
        "(deny file-write*)\n"
        f"{allows}\n"
        '(allow file-write* (subpath "/dev"))\n'
    )


def _seatbelt_usable() -> bool:
    exe = "/usr/bin/sandbox-exec"
    if not os.path.isfile(exe):
        return False
    try:
        done = subprocess.run(
            [exe, "-p", "(version 1)(allow default)", "/bin/sh", "-c", "true"],
            capture_output=True, timeout=10, check=False,
        )
        return done.returncode == 0
    except OSError:
        return False


def _bwrap_usable() -> bool:
    """Functional probe of Linux `bwrap`, memoized in `_BWRAP_OK`."""
    global _BWRAP_OK
    if _BWRAP_OK is None:
        _BWRAP_OK = _probe_bwrap()
    return _BWRAP_OK


def _probe_bwrap() -> bool:
    if not shutil.which("bwrap"):
        return False
    try:
        done = subprocess.run(
            ["bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "--unshare-net",
             "--die-with-parent", "true"],
            capture_output=True, timeout=10, check=False,
        )
        return done.returncode == 0
    except OSError:
        return False


def sandbox_backend() -> str:
    """Which confinement applies here: `none` / `seatbelt` / `bubblewrap` /
    `inherited` (already inside a jail -- never nest)."""
    if os.environ.get(core._JAILED):
        return "inherited"
    if sys.platform == "darwin" and _seatbelt_usable():
        return "seatbelt"
    if sys.platform.startswith("linux") and _bwrap_usable():
        return "bubblewrap"
    return "none"


def sandbox() -> dict:
    """A functional probe of the host sandbox (v1: `jail`)."""
    return {"backend": sandbox_backend()}


def _sandbox_argv(backend: str, d: str, scratch, argv: list) -> list:
    """Wrap `argv` to run confined under `backend`, or return it unwrapped."""
    if backend == "seatbelt":
        profile = _seatbelt_profile(d, scratch)
        return ["/usr/bin/sandbox-exec", "-p", profile] + argv
    if backend == "bubblewrap":
        real_d = os.path.realpath(d)
        wrapped = [
            "bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc",
            "--bind", real_d, real_d,
        ]
        if scratch:
            real_scratch = os.path.realpath(scratch)
            wrapped += ["--bind", real_scratch, real_scratch]
        wrapped += ["--unshare-net", "--die-with-parent", "--chdir", real_d]
        return wrapped + argv
    return argv


# -- running a gate -------------------------------------------------------

def _scrub_env(extra=None) -> dict:
    """A minimal host allowlist plus the claim's own variables; inherited
    secrets never reach a gate (spec/claim-format.md)."""
    env = {k: os.environ[k] for k in core._KEEP_ENV if k in os.environ}
    if extra:
        env.update(extra)
    return env


def _kill_tree(pid: int) -> None:
    """Kill the process group rooted at `pid`, best effort."""
    try:
        os.killpg(os.getpgid(pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass


def _run(argv: list, cwd=None, env=None, timeout=None) -> dict:
    """Run `argv` in its own process group so a timeout can kill the whole
    tree, not just the immediate child. Returns `{"returncode", "timed_out"}`."""
    proc = subprocess.Popen(
        argv, cwd=cwd, env=env, start_new_session=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        proc.wait(timeout=timeout)
        return {"returncode": proc.returncode, "timed_out": False}
    except subprocess.TimeoutExpired:
        _kill_tree(proc.pid)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        return {"returncode": proc.returncode, "timed_out": True}


def gate_timeout(recipe) -> float:
    """The effective per-gate wall-clock bound.

    A claim's declared `gate_timeout` IS the ceiling: it may raise the
    bound past this module's default, and a run past it still times out.
    Only an operator-set host cap (`RETICULI_GATE_TIMEOUT`) pulls it back
    down -- the effective bound is `min(declared or default, host cap)`.
    """
    claim = (recipe or {}).get("claim", {}) if recipe else {}
    declared = claim.get("gate_timeout")
    base = float(declared) if declared is not None else core.GATE_TIMEOUT
    cap = os.environ.get(core._ENV_TIMEOUT)
    if cap is not None:
        try:
            return min(base, float(cap))
        except ValueError:
            return base
    return base


def run_gate(cmd: str, d: str, recipe=None) -> dict:
    """Run one gate command: scrubbed environment, sandboxed, bounded.

    Returns `{"status", "quarantine"}`: `status` is `ok` / `failed` /
    `timeout` (failure classes beyond these are the caller's to assign --
    `mismatch`/`environment` depend on what the gate pins, not on how it
    ran); `quarantine` names the sandbox backend that applied.
    """
    backend = sandbox_backend()
    timeout = gate_timeout(recipe)
    extra_env = {}
    scratch = None
    if backend in ("seatbelt", "bubblewrap"):
        room = os.path.join(d, core.STORE, "room")
        os.makedirs(room, exist_ok=True)
        scratch = tempfile.mkdtemp(dir=room)
        extra_env["TMPDIR"] = scratch
        extra_env["HOME"] = scratch
    if backend != "inherited":
        extra_env[core._JAILED] = "1"
    env = _scrub_env(extra_env)
    argv = _sandbox_argv(backend, d, scratch, [core._SHELL, "-c", cmd])
    result = _in_band(_run, argv, cwd=d, env=env, timeout=timeout)
    if result["timed_out"]:
        status = "timeout"
    elif result["returncode"] == 0:
        status = "ok"
    else:
        status = "failed"
    return {"status": status, "quarantine": backend}


# -- the cost ledger -------------------------------------------------------

def _ledger_path(d: str) -> str:
    return os.path.join(d, core.LEDGER)


def ledger(d: str, entry: dict) -> None:
    """Append one JSON entry to the claim's cost ledger."""
    path = _ledger_path(d)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def ledger_events(d: str) -> list:
    """Every entry appended to the claim's ledger, in order."""
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
    """Ledger totals per unit (usd/tokens/calls/seconds).

    A key no ledger entry ever reported is absent from the result, never
    guessed at as zero -- an unmeasured machine is reported, not assumed.
    """
    totals = {}
    for event in ledger_events(d):
        for key in core.COST_KEYS:
            value = event.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                totals[key] = totals.get(key, 0) + value
    return totals
