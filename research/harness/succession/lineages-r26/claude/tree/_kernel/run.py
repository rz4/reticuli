"""Running a gate: scrubbed environment, sandboxed, bounded.

`run_gate` runs one gate command under a platform sandbox -- macOS
`sandbox-exec` ("seatbelt") or Linux `bwrap` ("bubblewrap"), functionally
probed rather than merely detected, falling back to `none` where neither
works and to `inherited` where this process is itself already jailed
(`RETICULI_JAILED`), so sandboxes never nest. The environment handed to the
gate is scrubbed to a small host allowlist; where a sandbox is actually
applied, `HOME`/`TMPDIR` are redirected to scratch space inside the claim's
own store, because a confined gate that reaches for the host's temp
directory fails only on hosts where confinement is real.

`ledger`/`ledger_events`/`cost` are the production-cost bookkeeping:
`ledger` appends one JSON line per event to `.reticuli/ledger.jsonl`,
`ledger_events` reads them back, and `cost` totals the four cost keys
(`usd`/`tokens`/`calls`/`seconds`) across every event that named them --
an absent key is unmeasured, never zero, so a total omits what no event
ever reported. `gate_timeout` makes a claim's declared `gate_timeout` the
ceiling in both directions: it is read before any host default and is
never undercut by one.

`furnish` builds (and caches) a private venv from a hash-pinned
requirements file for claims that declare `[claim] environment`.
`preflight` reports which of a claim's declared `requires` are missing on
this host. `independence` and `sandbox`/`sandbox_backend` are the small
observational primitives the layers above compose into the three-machine
test.

Stdlib only, never the network.
"""
import importlib
import json
import operator
import os
import platform
import shutil
import signal
import subprocess
import tempfile

from . import core

# -- requirement-string operators (order matters: longer operators first,
# so a two-character operator is never mistaken for its one-character
# prefix when scanning a string like "python>=3.8") --------------------

_REQ_OPS = ("<=", ">=", "==", "!=", "~=", "<", ">")

_OP_FUNCS = {
    "<=": operator.le,
    ">=": operator.ge,
    "==": operator.eq,
    "!=": operator.ne,
    "<": operator.lt,
    ">": operator.gt,
}

# -- cached functional probes of the host sandboxes ----------------------

_BWRAP_OK = None
_SEATBELT_OK = None


def _in_band() -> bool:
    """Whether this process is itself already inside a jail."""
    return bool(os.environ.get(core._JAILED))


def _have(name: str) -> bool:
    """Whether `name` is a runnable binary on PATH, or an importable module."""
    if shutil.which(name):
        return True
    try:
        importlib.import_module(name)
        return True
    except ImportError:
        return False


def _bwrap_usable() -> bool:
    """A functional probe of `bwrap`: present is not the same as working."""
    global _BWRAP_OK
    if _BWRAP_OK is None:
        try:
            probe = subprocess.run(
                ["bwrap", "--ro-bind", "/", "/", "--unshare-net", "--", "true"],
                capture_output=True, timeout=5,
            )
            _BWRAP_OK = probe.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            _BWRAP_OK = False
    return _BWRAP_OK


def _seatbelt_usable() -> bool:
    """A functional probe of `sandbox-exec`: present is not the same as working."""
    global _SEATBELT_OK
    if _SEATBELT_OK is None:
        try:
            probe = subprocess.run(
                ["/usr/bin/sandbox-exec", "-p", "(version 1)(allow default)", "/usr/bin/true"],
                capture_output=True, timeout=5,
            )
            _SEATBELT_OK = probe.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            _SEATBELT_OK = False
    return _SEATBELT_OK


def sandbox_backend() -> str:
    """Which confinement applies here: `none`, `seatbelt`, `bubblewrap`, `inherited`."""
    if _in_band():
        return "inherited"
    system = platform.system()
    if system == "Darwin" and _have("sandbox-exec") and _seatbelt_usable():
        return "seatbelt"
    if system == "Linux" and _have("bwrap") and _bwrap_usable():
        return "bubblewrap"
    return "none"


def sandbox() -> dict:
    """A functional probe of the host sandbox."""
    return {"backend": sandbox_backend()}


# -- building the room a gate runs in -------------------------------------


def _room_dir(d: str) -> str:
    """Scratch space inside the claim's own store -- never a declared file."""
    room = os.path.join(d, core.STORE, "room")
    os.makedirs(room, exist_ok=True)
    return room


def _scrub_env(d: str, room: str, apply_sandbox: bool) -> dict:
    """A minimal host allowlist plus the claim's own confinement signal."""
    env = {k: os.environ[k] for k in core._KEEP_ENV if k in os.environ}
    if apply_sandbox:
        env["HOME"] = room
        env["TMPDIR"] = room
        env[core._JAILED] = "1"
    return env


def _quote_sb(s: str) -> str:
    """Escape a path for embedding as a Scheme string literal in an SBPL profile."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _seatbelt_profile(d: str) -> str:
    path = _quote_sb(d)
    return "\n".join([
        "(version 1)",
        "(deny default)",
        "(allow process-fork)",
        "(allow process-exec)",
        "(allow signal (target self))",
        "(allow file-read*)",
        f'(allow file-write* (subpath "{path}"))',
        '(allow file-write* (literal "/dev/null"))',
        "(allow sysctl-read)",
        "(allow mach-lookup)",
        "(allow iokit-open)",
        "",
    ])


def _sandbox_argv(cmd: str, d: str, backend: str) -> list:
    """The argv that wraps `cmd` under `backend`; a bare shell where none applies."""
    if backend == "seatbelt":
        return ["/usr/bin/sandbox-exec", "-p", _seatbelt_profile(d),
                core._SHELL, "-c", cmd]
    if backend == "bubblewrap":
        return [
            "bwrap",
            "--ro-bind", "/", "/",
            "--dev-bind", "/dev", "/dev",
            "--proc", "/proc",
            "--bind", d, d,
            "--unshare-net",
            "--die-with-parent",
            "--",
            core._SHELL, "-c", cmd,
        ]
    return [core._SHELL, "-c", cmd]


# -- running the wrapped command, bounded ----------------------------------


def _kill_tree(proc: subprocess.Popen) -> None:
    """Kill the whole process group a timed-out gate spawned."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
        except OSError:
            pass


def _run(argv: list, cwd: str, env: dict, timeout: float) -> dict:
    """Spawn `argv`, bounded by `timeout`; never raises on timeout or exit."""
    try:
        proc = subprocess.Popen(
            argv, cwd=cwd, env=env, start_new_session=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
    except OSError as e:
        return {"returncode": 127, "timed_out": False, "stderr": str(e)}
    try:
        _, err = proc.communicate(timeout=timeout)
        return {"returncode": proc.returncode, "timed_out": False, "stderr": err}
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        try:
            proc.communicate(timeout=5)
        except Exception:
            pass
        return {"returncode": None, "timed_out": True, "stderr": b""}


def gate_timeout(parsed) -> float:
    """A claim's declared `gate_timeout` IS the ceiling, read before any host default."""
    if parsed:
        declared = parsed.get("claim", {}).get("gate_timeout")
        if declared is not None:
            return float(declared)
    env = os.environ.get(core._ENV_TIMEOUT)
    if env is not None:
        try:
            return float(env)
        except ValueError:
            pass
    return core.GATE_TIMEOUT


def run_gate(cmd: str, d: str, parsed) -> dict:
    """Run one gate command: scrubbed env, sandboxed, bounded."""
    d = os.path.realpath(d)
    backend = sandbox_backend()
    apply_sandbox = backend not in ("none", "inherited")
    room = _room_dir(d)
    env = _scrub_env(d, room, apply_sandbox)
    argv = _sandbox_argv(cmd, d, backend)
    timeout = gate_timeout(parsed)
    result = _run(argv, d, env, timeout)
    if result["timed_out"]:
        status = "timeout"
    elif result["returncode"] == 0:
        status = "ok"
    else:
        status = "failed"
    return {"status": status, "quarantine": backend}


# -- the cost ledger --------------------------------------------------------


def _ledger_path(d: str) -> str:
    return os.path.join(d, core.LEDGER)


def ledger(d: str, event: dict) -> None:
    """Append one JSON-lines event to the claim's cost ledger."""
    path = _ledger_path(d)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, sort_keys=True) + "\n")


def ledger_events(d: str) -> list:
    """Every event recorded in the claim's cost ledger, in append order."""
    path = _ledger_path(d)
    events = []
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(json.loads(line))
    return events


def cost(d: str):
    """Ledger totals per unit; `None` if nothing was measured.

    Totals carry only the keys the ledger names -- an unmeasured machine is
    reported, never guessed at.
    """
    totals = {}
    for event in ledger_events(d):
        for key in core.COST_KEYS:
            value = event.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                totals[key] = totals.get(key, 0) + value
    return totals or None


# -- the environment contract: `[claim] requires` --------------------------


def _version_tuple(s: str) -> tuple:
    """A dotted version string as a tuple of ints, trailing non-digits dropped."""
    parts = []
    for piece in s.split("."):
        digits = ""
        for ch in piece:
            if ch.isdigit():
                digits += ch
            else:
                break
        parts.append(int(digits) if digits else 0)
    return tuple(parts) or (0,)


def _version_ok(current: tuple, op: str, required: tuple) -> bool:
    if op == "~=":
        return required[:-1] == current[:len(required) - 1] and current >= required
    fn = _OP_FUNCS.get(op)
    return fn(current, required) if fn else False


def _tool_version(name: str):
    """The first digit-bearing token of `name --version`'s output, or `None`."""
    try:
        out = subprocess.run([name, "--version"], capture_output=True,
                              text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    for token in (out.stdout + " " + out.stderr).split():
        if any(ch.isdigit() for ch in token):
            return token.strip(",v")
    return None


def _split_requirement(req: str):
    for op in _REQ_OPS:
        if op in req:
            name, _, required = req.partition(op)
            return name.strip(), op, required.strip()
    return req.strip(), None, None


def preflight(parsed) -> list:
    """Which of a claim's declared `requires` are missing on this host."""
    missing = []
    requires = (parsed or {}).get("claim", {}).get("requires", [])
    for req in requires:
        name, op, required = _split_requirement(req)
        if not _have(name):
            missing.append(req)
            continue
        if op is not None:
            found = _tool_version(name)
            if found is None or not _version_ok(
                _version_tuple(found), op, _version_tuple(required)
            ):
                missing.append(req)
    return missing


# -- furnishing a declared environment -------------------------------------


def _env_cache_dir() -> str:
    """Where furnished venvs are cached, keyed by the caller elsewhere."""
    override = os.environ.get(core._ENV_CACHE)
    if override:
        return override
    return os.path.join(tempfile.gettempdir(), "reticuli", "envs")


def furnish(d: str, parsed) -> dict:
    """Build (or reuse) a private venv for a claim's declared `environment`."""
    env_file = (parsed or {}).get("claim", {}).get("environment")
    if not env_file:
        return {"ok": True, "path": None}
    resolved = core._safe(d, env_file)
    if not os.path.isfile(resolved):
        return {"ok": False, "reason": f"missing environment file: {env_file!r}"}
    digest = core._hash_file(resolved)
    key = f"{digest}-{platform.python_implementation()}-{platform.python_version()}-{platform.system()}"
    venv_dir = os.path.join(_env_cache_dir(), key)
    bindir = os.path.join(venv_dir, "bin")
    if not os.path.isdir(venv_dir):
        os.makedirs(_env_cache_dir(), exist_ok=True)
        try:
            subprocess.run(["python3", "-m", "venv", venv_dir],
                            check=True, timeout=core.FURNISH_TIMEOUT, capture_output=True)
            subprocess.run(
                [os.path.join(bindir, "pip"), "install",
                 "--require-hashes", "--only-binary=:all:", "-r", resolved],
                check=True, timeout=core.FURNISH_TIMEOUT, capture_output=True,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
            shutil.rmtree(venv_dir, ignore_errors=True)
            return {"ok": False, "reason": str(e)}
    return {"ok": True, "path": bindir}


# -- declared producer independence ----------------------------------------


def _independence_line(m1: dict, m3: dict) -> str:
    vendor1, vendor3 = m1.get("vendor"), m3.get("vendor")
    if not vendor1 or not vendor3:
        return "independence unestablished"
    if vendor1 == vendor3 and m1.get("model") == m3.get("model"):
        return "independence unestablished"
    return "independent"


def independence(m1, m3) -> str:
    """Declared producer independence of a crosscheck between two `producer` blocks."""
    return _independence_line(m1 or {}, m3 or {})
