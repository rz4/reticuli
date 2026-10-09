"""Kernel-run: gate execution, the host sandbox, and the cost ledger.

`run_gate` runs a claim's gate under a platform sandbox (macOS `sandbox-exec`
/ Linux `bwrap`), with a scrubbed environment and a bounded wall-clock, and
reports its status and which sandbox actually applied -- functionally
probed, never assumed from a binary's mere presence (`spec/claim-format.md`,
"Gate execution contract"). `sandbox_backend` / `sandbox` expose that probe.
`ledger` / `ledger_events` / `cost` are the production-cost bookkeeping
(`spec/verification.md`, "Cost ledger"). `gate_timeout` turns a claim's
declared `gate_timeout` into the effective ceiling -- the declaration IS the
bound, never min()'d against an implementation default in either direction.
`preflight` checks a claim's `requires` against the host. `furnish` builds
the private venv a declared `environment` needs before a gate runs
(`spec/claim-format.md`). `independence` records (never enforces) whether a
crosscheck's legs came from the same producer.

Stdlib only, never the network (furnish is the one caller-invoked exception
to "never the network", and only by installing exactly the named, hashed
artifacts).
"""
import importlib
import json
import os
import platform
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile

from . import core, recipe
from .core import ClaimError

_REQ_OPS = ('<=', '>=', '==', '!=', '~=', '<', '>')

_BWRAP_OK = None
_SEATBELT_OK = None


# -- binaries and versions on the host contract ---------------------------

def _have(tool: str) -> bool:
    """Whether `tool` resolves on PATH."""
    return shutil.which(tool) is not None


def _tool_version(tool: str):
    """The first dotted version number `tool --version` prints, or `None`."""
    try:
        out = subprocess.run([tool, "--version"], capture_output=True,
                              text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = (out.stdout or "") + (out.stderr or "")
    m = re.search(r"(\d+(?:\.\d+)+)", text)
    return m.group(1) if m else None


def _version_tuple(s: str) -> tuple:
    """A dotted version string as a tuple of ints, e.g. `"1.2.3"` -> `(1,2,3)`."""
    parts = []
    for p in s.strip().split("."):
        m = re.match(r"\d+", p)
        parts.append(int(m.group()) if m else 0)
    return tuple(parts)


def _version_ok(have: str, op: str, want: str) -> bool:
    """Whether version `have` satisfies `op want`, `op` one of `_REQ_OPS`."""
    h, w = _version_tuple(have), _version_tuple(want)
    n = max(len(h), len(w))
    h = h + (0,) * (n - len(h))
    w = w + (0,) * (n - len(w))
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
        if len(w) < 2:
            return h >= w
        prefix = w[:-1]
        return h[:len(prefix)] == prefix and h >= w
    raise ClaimError(f"unknown requirement operator {op!r}")


def _parse_requirement(req: str):
    """Split a `requires` entry into `(name, op, version)`; `op` is `None`
    when the entry names a bare tool/module with no version constraint."""
    for op in _REQ_OPS:
        idx = req.find(op)
        if idx != -1:
            return req[:idx].strip(), op, req[idx + len(op):].strip()
    return req.strip(), None, None


def preflight(recipe_doc: dict) -> list:
    """The declared `requires` this host cannot satisfy (`spec/kernel-api.md`)."""
    claim = (recipe_doc or {}).get("claim", {}) if isinstance(recipe_doc, dict) else {}
    missing = []
    for req in claim.get("requires") or []:
        name, op, want = _parse_requirement(req)
        if _have(name):
            if op is not None:
                have_ver = _tool_version(name)
                if have_ver is None or not _version_ok(have_ver, op, want):
                    missing.append(req)
            continue
        try:
            importlib.import_module(name)
            continue
        except ImportError:
            pass
        missing.append(req)
    return missing


# -- the private venv a declared `environment` needs -----------------------

def _env_cache_dir(digest: str) -> str:
    """Where a furnished venv for requirements `digest` is cached on this host."""
    base = os.environ.get(core._ENV_CACHE) or os.path.join(
        tempfile.gettempdir(), "reticuli-env-cache")
    tag = f"{digest}-{platform.python_version()}-{sys.platform}-{platform.machine()}"
    return os.path.join(base, tag)


def furnish(d: str, parsed: dict = None) -> dict:
    """Build (or reuse) the private venv `[claim] environment` names.

    A room with no declared `environment` furnishes trivially. A room that
    cannot be furnished -- no network, no wheel for this platform, a hash
    mismatch -- is an `environment` failure: the gates were not run.
    """
    parsed = parsed if parsed is not None else recipe.load_recipe(d)
    claim = parsed.get("claim", {})
    env_file = claim.get("environment")
    if env_file is None:
        return {"status": "ok", "venv": None}

    try:
        path = core._safe(d, env_file)
    except ClaimError as e:
        return {"status": "environment", "reason": str(e)}
    if not os.path.isfile(path):
        return {"status": "environment",
                "reason": f"declared environment file missing: {env_file!r}"}

    digest = core._hash_file(path)
    cache_dir = _env_cache_dir(digest)
    venv_dir = os.path.join(cache_dir, "venv")
    if os.path.isdir(venv_dir):
        return {"status": "ok", "venv": venv_dir}

    try:
        os.makedirs(cache_dir, exist_ok=True)
        subprocess.run([sys.executable, "-m", "venv", venv_dir], check=True,
                        timeout=core.FURNISH_TIMEOUT, capture_output=True)
        pip = os.path.join(venv_dir, "bin", "pip")
        subprocess.run(
            [pip, "install", "--require-hashes", "--only-binary=:all:",
             "-r", path],
            check=True, timeout=core.FURNISH_TIMEOUT, capture_output=True)
    except Exception as e:
        shutil.rmtree(venv_dir, ignore_errors=True)
        return {"status": "environment", "reason": str(e)}
    return {"status": "ok", "venv": venv_dir}


# -- environment scrub and the sandbox argv ---------------------------------

def _scrub_env(extra: dict = None) -> dict:
    """A minimal host allowlist (`core._KEEP_ENV`) plus the gate's own vars."""
    env = {k: os.environ[k] for k in core._KEEP_ENV if k in os.environ}
    if extra:
        env.update(extra)
    return env


def _quote_sb(s: str) -> str:
    """Escape `s` for embedding as an SBPL string literal."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _seatbelt_profile(d_real: str, scratch_real: str) -> str:
    """Allow-by-default, deny what the floor pins deny (network; writes
    outside the room), re-allow the room, the scratch dir, and /dev/null."""
    return (
        "(version 1)\n"
        "(allow default)\n"
        "(deny network*)\n"
        '(deny file-write* (subpath "/"))\n'
        f'(allow file-write* (subpath "{_quote_sb(d_real)}"))\n'
        f'(allow file-write* (subpath "{_quote_sb(scratch_real)}"))\n'
        '(allow file-write* (literal "/dev/null"))\n'
    )


def _sandbox_argv(backend: str, d: str, scratch: str, cmd: str) -> list:
    """The argv that runs `cmd` (a shell line) under `backend` with `d` as
    the room and `scratch` as its writable TMPDIR/HOME."""
    if backend == "seatbelt":
        d_real = os.path.realpath(d)
        scratch_real = os.path.realpath(scratch)
        profile_path = os.path.join(scratch, f".gate-{os.getpid()}.sb")
        with open(profile_path, "w", encoding="utf-8") as f:
            f.write(_seatbelt_profile(d_real, scratch_real))
        return ["sandbox-exec", "-f", profile_path, core._SHELL, "-c", cmd]
    if backend == "bubblewrap":
        d_real = os.path.realpath(d)
        scratch_real = os.path.realpath(scratch)
        return [
            "bwrap",
            "--ro-bind", "/", "/",
            "--dev", "/dev",
            "--proc", "/proc",
            "--tmpfs", "/tmp",
            "--bind", d_real, d_real,
            "--bind", scratch_real, scratch_real,
            "--unshare-net",
            "--die-with-parent",
            "--chdir", d_real,
            "--",
            core._SHELL, "-c", cmd,
        ]
    return [core._SHELL, "-c", cmd]


# -- functional sandbox probes -----------------------------------------------

def _probe_confinement(argv_for) -> bool:
    """Shared shape of the seatbelt/bwrap probes: a write inside a confined
    room must succeed, and a write outside it must be denied -- a sandbox
    that merely exists but enforces nothing is honestly reported as none."""
    probe_dir = tempfile.mkdtemp(prefix="reticuli-sbprobe-")
    outside = tempfile.mkdtemp(prefix="reticuli-sbprobe-outside-")
    try:
        inside_argv = argv_for(probe_dir, "printf x > inside")
        r_inside = subprocess.run(inside_argv, cwd=probe_dir,
                                   capture_output=True, timeout=10)
        inside_ok = (r_inside.returncode == 0
                     and os.path.isfile(os.path.join(probe_dir, "inside")))

        leak_path = os.path.join(outside, "leak")
        outside_argv = argv_for(
            probe_dir, f"printf x > {shlex.quote(leak_path)}")
        r_outside = subprocess.run(outside_argv, cwd=probe_dir,
                                    capture_output=True, timeout=10)
        outside_denied = (r_outside.returncode != 0
                           and not os.path.isfile(leak_path))
        return inside_ok and outside_denied
    except Exception:
        return False
    finally:
        shutil.rmtree(probe_dir, ignore_errors=True)
        shutil.rmtree(outside, ignore_errors=True)


def _seatbelt_usable() -> bool:
    global _SEATBELT_OK
    if _SEATBELT_OK is not None:
        return _SEATBELT_OK
    if not _have("sandbox-exec"):
        _SEATBELT_OK = False
        return False
    _SEATBELT_OK = _probe_confinement(
        lambda room, cmd: _sandbox_argv("seatbelt", room, room, cmd))
    return _SEATBELT_OK


def _bwrap_usable() -> bool:
    global _BWRAP_OK
    if _BWRAP_OK is not None:
        return _BWRAP_OK
    if not _have("bwrap"):
        _BWRAP_OK = False
        return False
    _BWRAP_OK = _probe_confinement(
        lambda room, cmd: _sandbox_argv("bubblewrap", room, room, cmd))
    return _BWRAP_OK


def sandbox_backend() -> str:
    """Which confinement applies here: `none`/`seatbelt`/`bubblewrap`/
    `inherited` -- `inherited` when already inside a sandbox (nesting
    avoided), the others only when functionally probed usable."""
    if os.environ.get(core._JAILED):
        return "inherited"
    if sys.platform == "darwin":
        return "seatbelt" if _seatbelt_usable() else "none"
    if sys.platform.startswith("linux"):
        return "bubblewrap" if _bwrap_usable() else "none"
    return "none"


def sandbox() -> dict:
    """A functional probe of the host sandbox (`spec/kernel-api.md`)."""
    backend = sandbox_backend()
    return {"backend": backend, "functional": backend not in ("none",)}


# -- running one gate ---------------------------------------------------

def _kill_tree(pid: int) -> None:
    """Kill the whole process group a gate (and anything it spawned) runs in."""
    try:
        pgid = os.getpgid(pid)
    except ProcessLookupError:
        return
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _run(argv: list, env: dict, cwd: str, timeout: float) -> dict:
    """Run `argv`, bounded by `timeout`; the whole tree dies together."""
    proc = subprocess.Popen(argv, cwd=cwd, env=env, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, start_new_session=True)
    try:
        out, err = proc.communicate(timeout=timeout)
        return {"returncode": proc.returncode, "timed_out": False,
                "stdout": out, "stderr": err}
    except subprocess.TimeoutExpired:
        _kill_tree(proc.pid)
        try:
            out, err = proc.communicate(timeout=5)
        except Exception:
            out, err = b"", b""
        return {"returncode": None, "timed_out": True,
                "stdout": out, "stderr": err}


def _in_band(exc: Exception, backend: str) -> dict:
    """An OS-level failure to even launch a gate, refused in band, with a
    reason, as an `environment` failure -- the host can't judge, which is
    distinct from the claim being wrong."""
    return {"status": "environment", "quarantine": backend, "reason": str(exc)}


def gate_timeout(recipe_doc) -> float:
    """The effective wall-clock ceiling for a gate (`spec/kernel-api.md`).

    A declared `[claim] gate_timeout` IS the ceiling -- it may raise the
    bound past any implementation default, and a gate past it still times
    out; it is never min()'d against a host default in either direction.
    Absent a declaration, `RETICULI_GATE_TIMEOUT` sets the host's own
    ceiling, and absent that, `core.GATE_TIMEOUT`.
    """
    claim = (recipe_doc or {}).get("claim", {}) if isinstance(recipe_doc, dict) else {}
    declared = claim.get("gate_timeout")
    if declared is not None:
        return declared
    env = os.environ.get(core._ENV_TIMEOUT)
    if env:
        try:
            return float(env)
        except ValueError:
            pass
    return core.GATE_TIMEOUT


def run_gate(cmd: str, d: str, recipe_doc=None) -> dict:
    """Run one gate: scrubbed env, sandboxed, bounded (`spec/kernel-api.md`).

    `cmd` is a shell line, run with `d` as its working directory. Returns
    `{"status": ..., "quarantine": ...}`: status one of `ok` / `failed` /
    `timeout` / `environment`; quarantine the sandbox backend that applied.
    """
    backend = sandbox_backend()
    scratch = os.path.join(d, core.STORE, "scratch")
    os.makedirs(scratch, exist_ok=True)

    extra_env = {}
    if backend in ("seatbelt", "bubblewrap"):
        extra_env["TMPDIR"] = scratch
        extra_env["HOME"] = scratch
        extra_env[core._JAILED] = "1"
    env = _scrub_env(extra_env)

    try:
        argv = _sandbox_argv(backend, d, scratch, cmd)
        timeout = gate_timeout(recipe_doc)
        result = _run(argv, env, d, timeout)
    except OSError as e:
        return _in_band(e, backend)

    if result["timed_out"]:
        status = "timeout"
    elif result["returncode"] == 0:
        status = "ok"
    else:
        status = "failed"
    return {"status": status, "quarantine": backend,
            "returncode": result["returncode"]}


# -- the cost ledger ---------------------------------------------------------

def _ledger_path(d: str) -> str:
    return os.path.join(d, core.LEDGER)


def ledger(d: str, entry: dict) -> None:
    """Append one cost event to `d`'s ledger (`spec/verification.md`)."""
    path = _ledger_path(d)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True))
        f.write("\n")


def ledger_events(d: str) -> list:
    """Every event appended to `d`'s ledger, in order; `[]` if none yet."""
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

    Totals carry only the keys the ledger names -- an unmeasured unit is
    omitted, never reported as zero (`spec/kernel-api.md`).
    """
    totals = {}
    events = ledger_events(d)
    for key in core.COST_KEYS:
        values = [e[key] for e in events
                  if isinstance(e, dict) and isinstance(e.get(key), (int, float))
                  and not isinstance(e.get(key), bool)]
        if values:
            totals[key] = sum(values)
    return totals or None


# -- declared producer independence of a crosscheck --------------------------

def _independence_line(p1: dict, p3: dict) -> str:
    """Describe what's known about M1 vs. M3 producer independence."""
    v1, m1 = (p1 or {}).get("vendor"), (p1 or {}).get("model")
    v3, m3 = (p3 or {}).get("vendor"), (p3 or {}).get("model")
    if v1 is None or v3 is None:
        return "independence unknown"
    if v1 == v3 and m1 == m3:
        return "independence unestablished (same vendor and model)"
    if v1 == v3:
        return "independence unestablished (same vendor)"
    return "independent"


def _producer_of(x) -> dict:
    if isinstance(x, dict) and isinstance(x.get("producer"), dict):
        return x["producer"]
    return x if isinstance(x, dict) else {}


def independence(m1, m3) -> str:
    """Declared producer independence of a crosscheck's M1 and M3 legs."""
    return _independence_line(_producer_of(m1), _producer_of(m3))
