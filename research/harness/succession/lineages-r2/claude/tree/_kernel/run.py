"""Gate execution: confined runs and the cost ledger (spec/claim-format.md).

`run_gate` runs one gate command under a scrubbed environment, sandboxed
where the host offers a functional sandbox, bounded by `gate_timeout`.
`sandbox_backend`/`sandbox` probe *functionally*: a present-but-nonfunctional
sandbox counts as none, honestly reported. `preflight` checks the claim's
`requires` against the host; `furnish` builds the private venv named by
`[claim] environment`. `ledger`/`ledger_events`/`cost` are the append-only
production-cost record and its totals (spec/verification.md). `independence`
records, never enforces, whether two producers were declared distinct.

Stdlib only.
"""
import importlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import venv

from . import core

# --- version-constraint operators for `[claim] requires` (longest first when
#     parsing, so "<=" is not mistaken for "<") --------------------------
_REQ_OPS = ('<=', '>=', '==', '!=', '~=', '<', '>')

# --- memoized functional probes --------------------------------------------
_BWRAP_OK = None


def _have(name: str) -> bool:
    """Whether a binary named `name` is on `PATH`."""
    return shutil.which(name) is not None


def _in_band(fn, *args, **kwargs):
    """Call `fn`; turn any exception into `(False, reason)` rather than a crash.

    Returns `(True, result)` on success -- the environment-probing analogue of
    "a refusal with a reason, never a raw crash" (spec/claim-format.md).
    """
    try:
        return True, fn(*args, **kwargs)
    except Exception as e:  # noqa: BLE001 -- probing untrusted host state
        return False, str(e)


def _probe_bwrap() -> bool:
    if not _have("bwrap"):
        return False
    ok, _ = _in_band(
        lambda: subprocess.run(
            ["bwrap", "--die-with-parent", "--ro-bind", "/", "/", "--", "/bin/true"],
            capture_output=True, timeout=5, check=False,
        ).returncode == 0
    )
    return bool(ok and _)


def _bwrap_usable() -> bool:
    """Whether bubblewrap is present *and* functional, memoized in `_BWRAP_OK`."""
    global _BWRAP_OK
    if _BWRAP_OK is None:
        _BWRAP_OK = _probe_bwrap()
    return _BWRAP_OK


def _seatbelt_usable() -> bool:
    """Whether macOS `sandbox-exec` actually runs a trivial profile."""
    ok, result = _in_band(
        lambda: subprocess.run(
            ["/usr/bin/sandbox-exec", "-p", "(version 1)\n(allow default)\n",
             "/bin/sh", "-c", "exit 0"],
            capture_output=True, timeout=5, check=False,
        ).returncode
    )
    return ok and result == 0


def sandbox_backend() -> str:
    """Which confinement applies here: `none`/`seatbelt`/`bubblewrap`/`inherited`.

    `inherited` means a sandbox is already applied outside this process
    (`RETICULI_JAILED` set) -- the receiving half of "sandboxes do not nest"
    (spec/verification.md).
    """
    if os.environ.get(core._JAILED):
        return "inherited"
    if sys.platform == "darwin" and _have("sandbox-exec") and _seatbelt_usable():
        return "seatbelt"
    if sys.platform.startswith("linux") and _bwrap_usable():
        return "bubblewrap"
    return "none"


def sandbox() -> dict:
    """A functional probe of the host sandbox (v1: `jail`)."""
    backend = sandbox_backend()
    return {"backend": backend, "available": backend not in ("none", "inherited")}


def _scrub_env(scratch: str = None) -> dict:
    """A minimal host allowlist (`spec/claim-format.md`), never inherited secrets.

    When `scratch` is given (a real sandbox applies), `TMPDIR`/`HOME` point
    there instead of the host's, so a gate cannot be handed paths its own
    confinement forbids it to write.
    """
    env = {k: os.environ[k] for k in core._KEEP_ENV if k in os.environ}
    if scratch is not None:
        env["TMPDIR"] = scratch
        env["HOME"] = scratch
    env[core._JAILED] = "1"
    return env


def _quote_sb(s: str) -> str:
    """Escape a path for embedding in a sandbox-exec S-expression string."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _seatbelt_profile(writable) -> str:
    """A macOS sandbox-exec profile: full access, network denied."""
    lines = ["(version 1)", "(allow default)"]
    for path in writable:
        lines.append(f'(allow file-write* (subpath "{_quote_sb(path)}"))')
    lines.append("(deny network*)")
    return "\n".join(lines)


def _sandbox_argv(backend: str, cmd: str, d: str, scratch: str = None) -> list:
    """The argv that runs shell command `cmd` under sandbox `backend`."""
    if backend == "seatbelt":
        writable = [d] + ([scratch] if scratch else [])
        return ["/usr/bin/sandbox-exec", "-p", _seatbelt_profile(writable),
                core._SHELL, "-c", cmd]
    if backend == "bubblewrap":
        argv = ["bwrap", "--die-with-parent", "--unshare-net",
                "--ro-bind", "/", "/", "--dev-bind", "/dev", "/dev",
                "--proc", "/proc", "--bind", d, d]
        if scratch:
            argv += ["--bind", scratch, scratch]
        argv += ["--", core._SHELL, "-c", cmd]
        return argv
    return [core._SHELL, "-c", cmd]


def _kill_tree(proc: subprocess.Popen) -> None:
    """Kill `proc`'s whole process group -- best-effort, used on timeout."""
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
        except OSError:
            pass


def _run(argv: list, cwd: str, env: dict, timeout: float) -> dict:
    """Run `argv`, bounded by `timeout`; kills the whole tree on expiry."""
    proc = subprocess.Popen(argv, cwd=cwd, env=env, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True,
                             start_new_session=True)
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
        return {"returncode": proc.returncode, "stdout": stdout,
                "stderr": stderr, "timed_out": False}
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        stdout, stderr = proc.communicate()
        return {"returncode": proc.returncode, "stdout": stdout,
                "stderr": stderr, "timed_out": True}


def gate_timeout(parsed: dict = None) -> float:
    """The effective bound: `min(declared, host ceiling)` (spec/claim-format.md)."""
    declared = core.GATE_TIMEOUT
    if parsed:
        declared = parsed.get("claim", {}).get("gate_timeout", core.GATE_TIMEOUT)
    ceiling = float(os.environ.get(core._ENV_TIMEOUT, core.GATE_TIMEOUT))
    return min(float(declared), ceiling)


def run_gate(cmd: str, d: str, parsed: dict = None, timeout: float = None) -> dict:
    """One gate: scrubbed env, sandboxed, bounded (spec/claim-format.md).

    Runs `cmd` (a shell command) with cwd `d`. Returns `{"status": one of
    "ok"/"failed"/"timeout", "quarantine": the sandbox backend applied,
    "returncode", "stdout", "stderr"}`.
    """
    backend = sandbox_backend()
    bound = timeout if timeout is not None else gate_timeout(parsed)

    scratch = None
    if backend not in ("none",):
        run_store = os.path.join(d, core.STORE, "run")
        os.makedirs(run_store, exist_ok=True)
        scratch = tempfile.mkdtemp(prefix="room-", dir=run_store)

    try:
        env = _scrub_env(scratch)
        argv = _sandbox_argv(backend, cmd, d, scratch)
        result = _run(argv, cwd=d, env=env, timeout=bound)
    finally:
        if scratch is not None:
            shutil.rmtree(scratch, ignore_errors=True)

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


def _version_tuple(s: str) -> tuple:
    """Parse a dotted version string into a tuple of leading-digit ints."""
    parts = []
    for chunk in s.split("."):
        digits = ""
        for ch in chunk:
            if not ch.isdigit():
                break
            digits += ch
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def _version_ok(have: tuple, op: str, want: tuple) -> bool:
    """Compare two version tuples with a requirement operator from `_REQ_OPS`."""
    if op == "==":
        return have == want
    if op == "!=":
        return have != want
    if op == "<=":
        return have <= want
    if op == ">=":
        return have >= want
    if op == "<":
        return have < want
    if op == ">":
        return have > want
    if op == "~=":
        prefix = want[:-1]
        return have >= want and have[:len(prefix)] == prefix
    raise core.ClaimError(f"unknown requirement operator: {op!r}")


def _tool_version(name: str):
    """A binary's self-reported version string, or `None` if undeterminable."""
    import re

    for flag in ("--version", "-V", "-v"):
        ok, done = _in_band(
            subprocess.run, [name, flag], capture_output=True, text=True,
            timeout=5, check=False,
        )
        if not ok:
            continue
        text = (done.stdout or "") + (done.stderr or "")
        match = re.search(r"\d+(?:\.\d+)+", text)
        if match:
            return match.group(0)
    return None


def _parse_requirement(req: str):
    """Split `"name>=1.2"` into `(name, op, version)`; `(name, None, None)` bare."""
    for op in sorted(_REQ_OPS, key=len, reverse=True):
        if op in req:
            name, _, version = req.partition(op)
            return name.strip(), op, version.strip()
    return req.strip(), None, None


def _meets_requirement(name: str, op, version) -> bool:
    if _have(name):
        if op is None:
            return True
        have = _tool_version(name)
        return have is not None and _version_ok(_version_tuple(have), op, _version_tuple(version))
    try:
        mod = importlib.import_module(name)
    except ImportError:
        return False
    if op is None:
        return True
    have = getattr(mod, "__version__", None)
    return bool(have) and _version_ok(_version_tuple(have), op, _version_tuple(version))


def preflight(parsed: dict) -> list:
    """The environment contract: which of `[claim] requires` are missing here.

    A requirement is a binary name or an importable Python module, optionally
    followed by a version constraint (`"name>=1.2.3"`, an op from `_REQ_OPS`).
    """
    requires = parsed.get("claim", {}).get("requires", [])
    missing = []
    for req in requires:
        name, op, version = _parse_requirement(req)
        ok, satisfied = _in_band(_meets_requirement, name, op, version)
        if not ok or not satisfied:
            missing.append(req)
    return missing


def _env_cache_dir() -> str:
    """Where furnished venvs are cached: `RETICULI_ENV_CACHE`, else a user cache dir."""
    override = os.environ.get(core._ENV_CACHE)
    if override:
        return override
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    path = os.path.join(base, "reticuli", "envs")
    os.makedirs(path, exist_ok=True)
    return path


def furnish(d: str, parsed: dict) -> dict:
    """Build (or reuse) a private venv from `[claim] environment`.

    Hash-pinned, `--require-hashes --only-binary=:all:`, cached per (file
    digest, interpreter, platform). Returns `{"ok": True, "bin": <dir>}` or
    `{"ok": False, "reason": ...}` -- a room that cannot be furnished is an
    **environment** failure, never a verdict (spec/claim-format.md).
    """
    env_file = parsed.get("claim", {}).get("environment")
    if env_file is None:
        return {"ok": True, "bin": None}

    req_path = os.path.join(d, env_file)
    if not os.path.isfile(req_path):
        return {"ok": False, "reason": f"no environment file at {req_path!r}"}

    digest = core._hash_file(req_path)
    tag = f"{digest}-{sys.version_info[0]}.{sys.version_info[1]}-{sys.platform}"
    venv_dir = os.path.join(_env_cache_dir(), tag)
    if os.path.isdir(venv_dir):
        return {"ok": True, "bin": os.path.join(venv_dir, "bin")}

    building = venv_dir + ".building"
    shutil.rmtree(building, ignore_errors=True)
    try:
        venv.create(building, with_pip=True)
        pip = os.path.join(building, "bin", "pip")
        done = subprocess.run(
            [pip, "install", "--require-hashes", "--only-binary=:all:", "-r", req_path],
            capture_output=True, text=True, timeout=core.FURNISH_TIMEOUT, check=False,
        )
        if done.returncode != 0:
            return {"ok": False, "reason": (done.stderr or done.stdout).strip()[-500:]}
        os.replace(building, venv_dir)
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"ok": False, "reason": str(e)}
    finally:
        shutil.rmtree(building, ignore_errors=True)
    return {"ok": True, "bin": os.path.join(venv_dir, "bin")}


def _independence_line(same_vendor: bool, same_model: bool) -> str:
    if same_vendor and same_model:
        return "same vendor and model: independence unestablished"
    if same_vendor:
        return "same vendor: independence unestablished"
    return "distinct vendor: independence declared"


def independence(m1_producer: dict, m3_producer: dict) -> dict:
    """Declared producer independence of a crosscheck.

    Recorded, never enforced -- content cannot prove blindness
    (spec/verification.md). Same-vendor rebuilds are marked as such.
    """
    m1_producer = m1_producer or {}
    m3_producer = m3_producer or {}
    vendor1, vendor3 = m1_producer.get("vendor"), m3_producer.get("vendor")
    model1, model3 = m1_producer.get("model"), m3_producer.get("model")
    same_vendor = bool(vendor1) and vendor1 == vendor3
    same_model = bool(model1) and model1 == model3
    return {
        "same_vendor": same_vendor,
        "same_model": same_model,
        "note": _independence_line(same_vendor, same_model),
    }


def _ledger_path(d: str) -> str:
    return os.path.join(d, core.LEDGER)


def ledger(d: str, entry: dict) -> None:
    """Append one entry to the claim's cost ledger (residue, outside the root)."""
    path = _ledger_path(d)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def ledger_events(d: str) -> list:
    """Every entry recorded in the claim's ledger, in append order."""
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
    """Ledger totals per unit (usd/tokens/calls/seconds); `None` if unmeasured.

    Totals carry only the keys the ledger names -- an unmeasured machine is
    reported, never guessed at (`spec/kernel-api.md`).
    """
    totals = {}
    for event in ledger_events(d):
        for key in core.COST_KEYS:
            value = event.get(key)
            if value is not None and not isinstance(value, bool):
                totals[key] = totals.get(key, 0) + value
    return totals or None
