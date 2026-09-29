"""reticuli._kernel.run -- executing a gate: sandboxed, scrubbed, bounded.

Every gate runs the same way, no matter which verb invoked it
(`spec/claim-format.md`, "Gate execution contract"): a scrubbed
environment, confinement under whatever sandbox this host actually
supports -- probed *functionally*, never assumed present -- and a
wall-clock bound. `run_gate` is the one entry point that does all three.

`ledger` / `ledger_events` / `cost` are the adjoining cost-accounting
primitives (`spec/verification.md`, "Cost ledger"); `preflight` is the
environment contract (`[claim] requires`); `furnish` builds the private
venv a `[claim] environment` pin describes (`spec/claim-format.md`,
"The environment"); `independence` records declared producer
independence for a crosscheck (`spec/verification.md`).
"""
import importlib
import importlib.metadata
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile

from . import core

# ---------------------------------------------------------------------------
# Sandbox: probed functionally, never assumed from mere presence.
# ---------------------------------------------------------------------------
_BWRAP_OK = None  # cached probe result; None until first probed


def _have(name: str) -> bool:
    """Whether `name` is available on this host: a binary, or a python module."""
    if shutil.which(name) is not None:
        return True
    try:
        importlib.import_module(name)
        return True
    except ImportError:
        return False


def _bwrap_usable() -> bool:
    """Functionally probe `bwrap`: present on PATH is not enough."""
    global _BWRAP_OK
    if _BWRAP_OK is None:
        ok = False
        if shutil.which("bwrap"):
            try:
                done = subprocess.run(
                    ["bwrap", "--ro-bind", "/", "/", "--unshare-net", "true"],
                    capture_output=True, timeout=10, check=False,
                )
                ok = done.returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                ok = False
        _BWRAP_OK = ok
    return _BWRAP_OK


def sandbox_backend() -> str:
    """Which sandbox this host will actually apply.

    `inherited` when already jailed (`RETICULI_JAILED` -- do not nest);
    otherwise `seatbelt` or `bubblewrap` when a functional probe of the
    platform-native sandbox succeeds; `none` otherwise, honestly.
    """
    if os.environ.get(core._JAILED):
        return "inherited"
    if sys.platform == "darwin" and shutil.which("sandbox-exec"):
        try:
            done = subprocess.run(
                ["sandbox-exec", "-p", "(version 1)(allow default)", "/usr/bin/true"],
                capture_output=True, timeout=10, check=False,
            )
            if done.returncode == 0:
                return "seatbelt"
        except (OSError, subprocess.TimeoutExpired):
            pass
    if sys.platform.startswith("linux") and _bwrap_usable():
        return "bubblewrap"
    return "none"


def sandbox() -> dict:
    """A functional probe of the host sandbox: `{backend}` at minimum."""
    return {"backend": sandbox_backend()}


def _quote_sb(path: str) -> str:
    """Escape `path` for embedding in a seatbelt profile string literal."""
    return path.replace("\\", "\\\\").replace('"', '\\"')


def _sandbox_argv(backend: str, argv: list, d: str, scratch: str) -> list:
    """The literal argv to invoke, wrapping `argv` in `backend`'s confinement."""
    if backend == "seatbelt":
        profile = (
            "(version 1)(allow default)(deny network*)"
            f'(allow file-write* (subpath "{_quote_sb(os.path.realpath(d))}"))'
            f'(allow file-write* (subpath "{_quote_sb(os.path.realpath(scratch))}"))'
        )
        return ["sandbox-exec", "-p", profile] + argv
    if backend == "bubblewrap":
        return [
            "bwrap",
            "--ro-bind", "/", "/",
            "--dev", "/dev",
            "--proc", "/proc",
            "--bind", d, d,
            "--bind", scratch, scratch,
            "--unshare-net",
            "--die-with-parent",
            "--",
        ] + argv
    return argv


# ---------------------------------------------------------------------------
# Environment: scrubbed, and (where confined) given scratch space.
# ---------------------------------------------------------------------------
def _scrub_env() -> dict:
    """A minimal host allowlist plus the claim's own (`RETICULI_*`) variables."""
    env = {k: v for k, v in os.environ.items() if k in core._KEEP_ENV}
    for k, v in os.environ.items():
        if k.startswith("RETICULI_"):
            env[k] = v
    return env


def _env_cache_dir() -> str:
    """Where furnished venvs are cached: host residue, never identity."""
    override = os.environ.get(core._ENV_CACHE)
    if override:
        return override
    return os.path.join(tempfile.gettempdir(), "reticuli-envs")


# ---------------------------------------------------------------------------
# Process execution and timeouts
# ---------------------------------------------------------------------------
def _kill_tree(pid: int) -> None:
    """Kill the process group rooted at `pid`."""
    try:
        os.killpg(pid, signal.SIGKILL)
    except OSError:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


def _run(argv: list, cwd: str, env: dict, timeout: float):
    """Run `argv`; return `(returncode, timed_out)`, killing the whole tree on timeout."""
    proc = subprocess.Popen(
        argv, cwd=cwd, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        proc.communicate(timeout=timeout)
        return proc.returncode, False
    except subprocess.TimeoutExpired:
        _kill_tree(proc.pid)
        proc.communicate()
        return proc.returncode, True


def gate_timeout(declared=None) -> float:
    """The effective wall-clock bound: `min(declared, host ceiling)`."""
    ceiling = core.GATE_TIMEOUT
    if declared is None:
        return ceiling
    try:
        declared = float(declared)
    except (TypeError, ValueError) as exc:
        raise core.ClaimError(f"gate_timeout must be a number, got {declared!r}") from exc
    return min(declared, ceiling)


def run_gate(cmd: str, d: str, timeout=None) -> dict:
    """Run one gate command: scrubbed environment, sandboxed, bounded.

    `cmd` is a shell command string, run with `d` as the working directory.
    Returns `{status, quarantine}`: `quarantine` names the sandbox backend
    actually applied; `status` is `"ok"` on a clean exit, `"failed"` on a
    nonzero exit, `"timeout"` if the wall-clock bound was exceeded.
    """
    backend = sandbox_backend()
    eff_timeout = gate_timeout(timeout)
    env = _scrub_env()

    scratch_root = os.path.join(d, core.STORE, "scratch")
    os.makedirs(scratch_root, exist_ok=True)
    scratch = tempfile.mkdtemp(dir=scratch_root)
    try:
        base_argv = ["/bin/sh", "-c", cmd]
        if backend in ("seatbelt", "bubblewrap"):
            env["TMPDIR"] = scratch
            env["HOME"] = scratch
            argv = _sandbox_argv(backend, base_argv, d, scratch)
        else:
            argv = base_argv
        returncode, timed_out = _run(argv, d, env, eff_timeout)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    if timed_out:
        status = "timeout"
    elif returncode == 0:
        status = "ok"
    else:
        status = "failed"
    return {"status": status, "quarantine": backend}


# ---------------------------------------------------------------------------
# The environment contract: `[claim] requires`, pip-style version specifiers
# ---------------------------------------------------------------------------
_REQ_OPS = ('<=', '>=', '==', '!=', '~=', '<', '>')
_REQ_RE = re.compile(
    r'^(?P<name>[A-Za-z0-9_.\-]+)\s*(?P<op>' + '|'.join(re.escape(o) for o in _REQ_OPS)
    + r')\s*(?P<version>[A-Za-z0-9_.\-]+)$'
)


def _in_band(name: str) -> bool:
    """Whether `name` is checked in-process (a python module) rather than by
    shelling out to a binary."""
    if re.search(r'[\\/]', name) or shutil.which(name):
        return False
    try:
        importlib.import_module(name)
        return True
    except ImportError:
        return False


def _version_tuple(version: str) -> tuple:
    """A version string as a tuple of ints/strings, for ordered comparison."""
    parts = re.split(r'[.\-]', version)
    return tuple(int(p) if p.isdigit() else p for p in parts)


def _version_ok(installed: str, op: str, required: str) -> bool:
    """Whether `installed <op> required` holds, comparing parsed version tuples."""
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
        return a[:-1] == b[:-1] and a >= b
    raise core.ClaimError(f"unknown requirement operator {op!r}")


def _tool_version(name: str) -> str:
    """The installed version of `name` -- a python module or a binary."""
    if _in_band(name):
        try:
            return importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            module = sys.modules.get(name) or importlib.import_module(name)
            found = getattr(module, "__version__", None)
            if found:
                return str(found)
            raise core.ClaimError(f"no version found for module {name!r}")
    path = shutil.which(name)
    if not path:
        raise core.ClaimError(f"tool {name!r} not found on PATH")
    done = subprocess.run([name, "--version"], capture_output=True, text=True,
                          timeout=10, check=False)
    text = (done.stdout or done.stderr or "").strip()
    found = re.search(r'\d+(?:\.\d+){0,3}', text)
    if not found:
        raise core.ClaimError(f"could not parse a version from `{name} --version`: {text!r}")
    return found.group(0)


def preflight(recipe: dict) -> list:
    """The claim's declared `requires` entries that are missing on this host."""
    missing = []
    for entry in recipe.get("claim", {}).get("requires", []):
        m = _REQ_RE.match(entry)
        if not m:
            if not _have(entry):
                missing.append(entry)
            continue
        name, op, version = m.group("name"), m.group("op"), m.group("version")
        if not _have(name):
            missing.append(entry)
            continue
        try:
            if not _version_ok(_tool_version(name), op, version):
                missing.append(entry)
        except core.ClaimError:
            missing.append(entry)
    return missing


# ---------------------------------------------------------------------------
# `[claim] environment`: a private venv from a hash-pinned requirements file
# ---------------------------------------------------------------------------
def furnish(requirements_path: str, d: str) -> str:
    """Build (or reuse) a private venv from a hash-pinned requirements file.

    Cached per (file digest, interpreter, platform) under `_env_cache_dir()`.
    `--require-hashes` so nothing unnamed can arrive; `--only-binary=:all:`
    so nothing executes at install time.
    """
    digest = core._hash_file(core._safe(d, requirements_path))
    key = f"{digest}-{sys.platform}-{sys.version_info.major}.{sys.version_info.minor}"
    venv_dir = os.path.join(_env_cache_dir(), key)
    if not os.path.isdir(venv_dir):
        os.makedirs(_env_cache_dir(), exist_ok=True)
        subprocess.run([sys.executable, "-m", "venv", venv_dir],
                       check=True, timeout=core.FURNISH_TIMEOUT)
        pip = os.path.join(venv_dir, "bin", "pip")
        subprocess.run(
            [pip, "install", "--require-hashes", "--only-binary=:all:",
             "-r", core._safe(d, requirements_path)],
            check=True, timeout=core.FURNISH_TIMEOUT,
        )
    return venv_dir


# ---------------------------------------------------------------------------
# Cost ledger
# ---------------------------------------------------------------------------
_COST_UNITS = ("usd", "tokens", "calls", "seconds")


def _ledger_path(d: str) -> str:
    return core._safe(d, core.LEDGER)


def ledger(d: str, event: dict) -> dict:
    """Append one JSON event to `d`'s ledger; returns the stamped event."""
    path = _ledger_path(d)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    stamped = dict(event)
    stamped.setdefault("when", core._now())
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(stamped, sort_keys=True))
        f.write("\n")
    return stamped


def ledger_events(d: str) -> list:
    """All events recorded in `d`'s ledger, oldest first."""
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

    Totals carry only the keys the ledger names -- an unmeasured unit is
    omitted, never reported as zero.
    """
    totals = {}
    for event in ledger_events(d):
        for key in _COST_UNITS:
            value = event.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                totals[key] = totals.get(key, 0) + value
    return totals


# ---------------------------------------------------------------------------
# Producer independence: recorded, never enforced
# ---------------------------------------------------------------------------
def _independence_line(m1_producer: dict, m3_producer: dict) -> str:
    """A human-readable independence line for two producer declarations."""
    if not m1_producer or not m3_producer:
        return "independence unestablished"
    if m1_producer.get("vendor") and m1_producer.get("vendor") == m3_producer.get("vendor"):
        return "independence unestablished"
    return "independent"


def independence(m1_producer: dict, m3_producer: dict) -> dict:
    """Declared producer independence between M1 and M3. An observation,
    never a hard condition: content cannot prove blindness."""
    return {
        "line": _independence_line(m1_producer, m3_producer),
        "same_vendor": bool(
            m1_producer and m3_producer
            and m1_producer.get("vendor") == m3_producer.get("vendor")
        ),
    }
