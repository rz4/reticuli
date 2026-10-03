"""Gate execution and the cost ledger (spec/claim-format.md, "Gate execution
contract"; spec/verification.md, "Cost ledger").

`run_gate` runs one gate command with a scrubbed environment, under a
functionally-probed sandbox, bounded by a wall-clock timeout, and reports
which confinement actually applied -- a present-but-nonfunctional sandbox
honestly reports `none` rather than pretending. `sandbox`/`sandbox_backend`
do that probing; `preflight`/`furnish` cover the environment contract
(host `requires`, and the hash-pinned `[claim] environment` venv).
`ledger`/`ledger_events`/`cost` are the on-disk cost record a rebuild
appends to and a crosscheck totals.
"""
import importlib.util
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time

from . import core
from .core import ClaimError

# Comparison operators a `requires` version spec may use, longest first so a
# two-character operator is matched before its single-character prefix.
_REQ_OPS = ('<=', '>=', '==', '!=', '~=', '<', '>')

# Cached result of the bubblewrap functional probe: None until first probed.
_BWRAP_OK = None


# -- plain host helpers -----------------------------------------------------


def _have(binary: str) -> bool:
    """Whether `binary` resolves on `PATH`."""
    return shutil.which(binary) is not None


def _in_band(fn, *args, **kwargs):
    """Call `fn`, turning any exception into a `ClaimError` with a reason --
    the refusal vocabulary, never a raw crash, for code that touches the
    host (subprocess, filesystem).
    """
    try:
        return fn(*args, **kwargs)
    except ClaimError:
        raise
    except Exception as exc:
        raise ClaimError(str(exc)) from exc


def _kill_tree(proc) -> None:
    """Kill `proc` and every descendant on a timeout. `_run` starts it in
    its own process group (`start_new_session=True`), so a plain
    `proc.kill()` -- which only reaches the direct child -- would leave
    grandchildren running.
    """
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
        except Exception:
            pass


def _run(argv, cwd=None, env=None, timeout=None) -> dict:
    """Run `argv`, capturing combined output and bounding wall-clock time.
    Returns `returncode` (`None` on timeout), `stdout`, `timed_out`, and
    `seconds` elapsed.
    """
    start = time.monotonic()
    proc = subprocess.Popen(
        argv, cwd=cwd, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    try:
        out, _ = proc.communicate(timeout=timeout)
        timed_out = False
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        out, _ = proc.communicate()
        timed_out = True
    return {
        "returncode": proc.returncode,
        "stdout": out.decode("utf-8", "replace") if out else "",
        "timed_out": timed_out,
        "seconds": time.monotonic() - start,
    }


def _scrub_env(extra=None) -> dict:
    """The gate's scrubbed environment: the host allowlist
    (`core._KEEP_ENV`) plus whatever this call adds -- inherited secrets
    never reach a gate (spec/claim-format.md, "Gate execution contract").
    """
    env = {k: os.environ[k] for k in core._KEEP_ENV if k in os.environ}
    if extra:
        env.update(extra)
    return env


# -- sandbox probing ---------------------------------------------------------


def _bwrap_usable() -> bool:
    """Functional probe of bubblewrap, cached in `_BWRAP_OK`: present but
    unable to actually run a sandboxed command counts as unusable.
    """
    global _BWRAP_OK
    if _BWRAP_OK is None:
        if not _have("bwrap"):
            _BWRAP_OK = False
        else:
            try:
                done = subprocess.run(
                    ["bwrap", "--ro-bind", "/", "/", "--", "/bin/true"],
                    capture_output=True, timeout=5, check=False,
                )
                _BWRAP_OK = done.returncode == 0
            except OSError:
                _BWRAP_OK = False
    return _BWRAP_OK


def _seatbelt_usable() -> bool:
    """Functional probe of macOS `sandbox-exec`: a trivial permissive
    profile must actually run the wrapped command, not merely exist.
    """
    try:
        done = subprocess.run(
            ["sandbox-exec", "-p", "(version 1)(allow default)", "/usr/bin/true"],
            capture_output=True, timeout=5, check=False,
        )
        return done.returncode == 0
    except OSError:
        return False


def sandbox() -> dict:
    """A functional probe of the host's sandbox backend
    (spec/claim-format.md, "Gate execution contract"). Already running
    inside one (`RETICULI_JAILED`) reports `inherited` -- sandboxes do not
    nest. A present-but-nonfunctional backend reports `none`, honestly.
    """
    if os.environ.get(core._JAILED):
        return {"backend": "inherited"}
    if sys.platform == "darwin" and _have("sandbox-exec") and _seatbelt_usable():
        return {"backend": "seatbelt"}
    if _bwrap_usable():
        return {"backend": "bubblewrap"}
    return {"backend": "none"}


def sandbox_backend() -> str:
    """The sandbox backend `sandbox()` would apply right now."""
    return sandbox()["backend"]


def _quote_sb(path: str) -> str:
    """Escape `path` for a literal string inside a `sandbox-exec` (Scheme)
    profile.
    """
    return path.replace("\\", "\\\\").replace('"', '\\"')


_SEATBELT_PROFILE = """(version 1)
(deny default)
(allow process-fork)
(allow process-exec)
(allow file-read*)
(allow file-write* (subpath "{room}"))
(allow file-write* (subpath "{scratch}"))
(allow mach-lookup)
(allow sysctl-read)
"""


def _sandbox_argv(backend: str, argv, room: str, scratch: str) -> list:
    """Wrap `argv` to run under `backend`, confined to `room` (the gate's
    working directory) and `scratch` (its `HOME`/`TMPDIR`) -- the only
    paths it may write (spec/claim-format.md, "Gate execution contract").
    """
    if backend in ("none", "inherited"):
        return list(argv)
    if backend == "seatbelt":
        profile = _SEATBELT_PROFILE.format(
            room=_quote_sb(os.path.realpath(room)),
            scratch=_quote_sb(os.path.realpath(scratch)),
        )
        return ["sandbox-exec", "-p", profile, *argv]
    if backend == "bubblewrap":
        return [
            "bwrap",
            "--ro-bind", "/", "/",
            "--dev", "/dev",
            "--proc", "/proc",
            "--bind", room, room,
            "--bind", scratch, scratch,
            "--unshare-net",
            "--die-with-parent",
            "--",
            *argv,
        ]
    raise ClaimError(f"unknown sandbox backend: {backend!r}")


# -- running a gate -----------------------------------------------------


def gate_timeout(recipe) -> float:
    """The effective per-gate wall-clock bound: the claim's declared
    `gate_timeout` (default `core.GATE_TIMEOUT`), capped at the host
    ceiling (`RETICULI_GATE_TIMEOUT`) when the host sets a tighter one
    (spec/claim-format.md).
    """
    claim = recipe.get("claim", {}) if isinstance(recipe, dict) else {}
    declared = float(claim.get("gate_timeout", core.GATE_TIMEOUT))
    ceiling = os.environ.get(core._ENV_TIMEOUT)
    if ceiling is not None:
        try:
            return min(declared, float(ceiling))
        except ValueError:
            pass
    return declared


def run_gate(cmd: str, d: str, timeout) -> dict:
    """Run one gate command: scrubbed environment, sandboxed, bounded
    (spec/claim-format.md, "Gate execution contract"). `timeout` of `None`
    uses `core.GATE_TIMEOUT`. Returns `status` (`ok` / `failed` / `timeout`)
    and `quarantine`, the sandbox backend actually applied.
    """
    backend = sandbox_backend()
    bound = timeout if timeout is not None else core.GATE_TIMEOUT

    scratch_root = os.path.join(d, core.STORE, "scratch")
    os.makedirs(scratch_root, exist_ok=True)
    scratch = tempfile.mkdtemp(prefix="run-", dir=scratch_root)
    try:
        env = _scrub_env({"HOME": scratch, "TMPDIR": scratch, core._JAILED: "1"})
        argv = _sandbox_argv(backend, [core._SHELL, "-c", cmd], d, scratch)
        result = _run(argv, cwd=d, env=env, timeout=bound)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    if result["timed_out"]:
        status = "timeout"
    elif result["returncode"] == 0:
        status = "ok"
    else:
        status = "failed"

    return {"status": status, "quarantine": backend, "returncode": result["returncode"]}


# -- the environment contract: requires / furnish ------------------------


def _version_tuple(s: str) -> tuple:
    """A version string as a tuple of its integer run components, for
    ordering comparisons.
    """
    return tuple(int(p) for p in re.findall(r"\d+", s))


def _version_ok(version: str, requirement: str) -> bool:
    """Whether `version` satisfies a `<op><version>` requirement, trying
    each operator in `_REQ_OPS` in turn.
    """
    requirement = requirement.strip()
    for op in _REQ_OPS:
        if not requirement.startswith(op):
            continue
        want = _version_tuple(requirement[len(op):])
        have = _version_tuple(version)
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
    return _version_tuple(version) == _version_tuple(requirement)


def _tool_version(binary: str):
    """The version string `binary --version` reports, or `None` when the
    binary cannot be run or reports nothing that looks like a version.
    """
    try:
        done = subprocess.run(
            [binary, "--version"], capture_output=True, text=True,
            timeout=5, check=False,
        )
    except OSError:
        return None
    text = (done.stdout or done.stderr or "").strip()
    match = re.search(r"\d+(?:\.\d+)+", text)
    return match.group(0) if match else None


def preflight(recipe) -> list:
    """Which of the claim's declared `[claim] requires` are missing on this
    host (spec/claim-format.md, "The environment contract"): a bare binary
    or Python module name, or a binary with a `<op><version>` requirement
    suffix.
    """
    claim = recipe.get("claim", {}) if isinstance(recipe, dict) else {}
    missing = []
    for req in claim.get("requires", []):
        name, op, want = req, None, None
        for candidate in _REQ_OPS:
            idx = req.find(candidate)
            if idx > 0:
                name, op, want = req[:idx], candidate, req[idx + len(candidate):]
                break

        if _have(name):
            if op is not None:
                version = _tool_version(name)
                if version is None or not _version_ok(version, op + want):
                    missing.append(req)
            continue
        if importlib.util.find_spec(name) is not None:
            continue
        missing.append(req)
    return missing


def _env_cache_dir() -> str:
    """Where furnished venvs are cached -- host residue, never identity
    (spec/claim-format.md, "The environment"). Honors `RETICULI_ENV_CACHE`;
    otherwise a directory under the platform's temp root.
    """
    override = os.environ.get(core._ENV_CACHE)
    if override:
        return override
    path = os.path.join(tempfile.gettempdir(), "reticuli-envs")
    os.makedirs(path, exist_ok=True)
    return path


def furnish(d: str, recipe):
    """Build a private venv from the claim's hash-pinned `[claim]
    environment` file (spec/claim-format.md): `--require-hashes
    --only-binary=:all:`, cached per (file digest, interpreter, platform).
    Returns the venv's `bin` directory to prepend onto a gate's `PATH`, or
    `None` when the claim declares no environment.
    """
    claim = recipe.get("claim", {}) if isinstance(recipe, dict) else {}
    env_file = claim.get("environment")
    if env_file is None:
        return None

    path = core._safe(d, env_file)
    digest = core._hash_file(path)
    key = f"{digest}-{sys.implementation.name}{sys.version_info[0]}{sys.version_info[1]}-{sys.platform}"
    venv_dir = os.path.join(_env_cache_dir(), key)

    if not os.path.isdir(venv_dir):
        _in_band(
            subprocess.run, [sys.executable, "-m", "venv", venv_dir],
            check=True, capture_output=True, timeout=core.FURNISH_TIMEOUT,
        )
        pip = os.path.join(venv_dir, "bin", "pip")
        _in_band(
            subprocess.run,
            [pip, "install", "--require-hashes", "--only-binary=:all:",
             "-r", path],
            check=True, capture_output=True, timeout=core.FURNISH_TIMEOUT,
        )
    return os.path.join(venv_dir, "bin")


# -- declared producer independence --------------------------------------


def _independence_line(producer) -> str:
    """A one-line "vendor/model" label for a producer declaration."""
    if not isinstance(producer, dict):
        return "unknown"
    return f"{producer.get('vendor', 'unknown')}/{producer.get('model', 'unknown')}"


def independence(m1_producer, m3_producer) -> dict:
    """Declared producer independence between two crosscheck legs
    (spec/verification.md): an observation, never enforced -- content
    cannot prove blindness. Same vendor on both legs is marked
    `independence unestablished`.
    """
    m1 = m1_producer if isinstance(m1_producer, dict) else {}
    m3 = m3_producer if isinstance(m3_producer, dict) else {}
    same_vendor = bool(m1.get("vendor")) and m1.get("vendor") == m3.get("vendor")
    return {
        "m1": _independence_line(m1),
        "m3": _independence_line(m3),
        "established": not same_vendor,
        "note": "independence unestablished" if same_vendor else None,
    }


# -- the cost ledger -------------------------------------------------------


def _ledger_path(d: str) -> str:
    return os.path.join(d, core.LEDGER)


def ledger(d: str, entry: dict) -> None:
    """Append one entry to the claim's cost ledger, creating the store
    directory if needed (spec/verification.md, "Cost ledger").
    """
    path = _ledger_path(d)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True))
        f.write("\n")


def ledger_events(d: str) -> list:
    """Every entry appended to the claim's cost ledger, in order; an empty
    list when none exists yet.
    """
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
    """Ledger totals per unit (spec/kernel-api.md): sums `usd`/`tokens`/
    `calls`/`seconds` across every ledger entry that reports them. `None`
    when nothing was measured at all -- totals carry only the keys the
    ledger names, never a guessed zero.
    """
    totals = {}
    for event in ledger_events(d):
        for key in core.COST_KEYS:
            value = event.get(key)
            if value is None or isinstance(value, bool):
                continue
            if isinstance(value, (int, float)):
                totals[key] = totals.get(key, 0) + value
    return totals or None
