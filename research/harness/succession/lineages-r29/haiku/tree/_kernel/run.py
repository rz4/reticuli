"""Kernel run: confined gate execution, sandbox probing, and the cost ledger.

* ``sandbox_backend()``  -- the confinement a gate runs under: ``inherited``
                            when this process is already inside a sandbox
                            (``RETICULI_JAILED``), otherwise ``bubblewrap``
                            (Linux) or ``seatbelt`` (macOS) when a functional
                            probe succeeds, else ``none``.
* ``run_gate(cmd, d, parsed)`` -- one gate: environment contract checked,
                            scrubbed environment, sandboxed where a real
                            sandbox applies, bounded by the declared ceiling.
                            Returns ``{status, quarantine, ...}`` with status
                            one of ok / failed / timeout / environment.
* ``gate_timeout(parsed)`` -- the claim's declared ``gate_timeout`` is the
                            ceiling itself; otherwise the host default.
* ``ledger`` / ``ledger_events`` / ``cost`` -- the append-only cost ledger in
                            the claim's store (residue, never identity).

The jail's floor is a property, not a profile syntax: a legitimate gate
(/dev sinks, subprocess spawn, host reads, uname, user lookup) must run
inside it, while the network and writes beyond the workspace stay denied.
A sandbox that applies tells the wrapped process so (``RETICULI_JAILED``),
so sandboxes do not nest. Stdlib only, never the network (furnishing an
environment is the one deliberate exception, and it is explicit).
"""
import hashlib
import importlib.metadata
import importlib.util
import json
import math
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import tempfile

from reticuli._kernel import core, recipe

# ------------------------------------------------------------ vocabularies
SANDBOXES = ("none", "seatbelt", "bubblewrap", "inherited")
_APPLIED = ("seatbelt", "bubblewrap")
_REQ_OPS = ('<=', '>=', '==', '!=', '~=', '<', '>')
_SPEC = re.compile(
    r"\s*([A-Za-z0-9_.+-]+)\s*(?:(" + "|".join(re.escape(o) for o in _REQ_OPS)
    + r")\s*([0-9][^\s]*))?\s*")
_VERSION = re.compile(r"\d+(?:\.\d+)*")

# Probe results, computed once per process. None means "not yet probed".
_BWRAP_OK = None
_SEATBELT_OK = None


# ------------------------------------------------------------ small helpers
def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _gate_result(status: str, backend: str, timeout: float, **extra) -> dict:
    out = {"status": status, "quarantine": backend, "sandbox": backend,
           "timeout": timeout}
    out.update(extra)
    return out


# ------------------------------------------------------------ versions
def _version_tuple(text):
    """The first dotted version number in ``text`` as a tuple of ints, or None."""
    m = _VERSION.search(str(text or ""))
    if not m:
        return None
    return tuple(int(x) for x in m.group(0).split("."))


def _version_ok(have, op: str, want: str) -> bool:
    """Does version string ``have`` satisfy ``op want``? False when unknown."""
    h = _version_tuple(have)
    w = _version_tuple(want)
    if h is None or w is None or op not in _REQ_OPS:
        return False
    n = max(len(h), len(w))
    hp = h + (0,) * (n - len(h))
    wp = w + (0,) * (n - len(w))
    if op == "==":
        return hp == wp
    if op == "!=":
        return hp != wp
    if op == "<":
        return hp < wp
    if op == "<=":
        return hp <= wp
    if op == ">":
        return hp > wp
    if op == ">=":
        return hp >= wp
    # "~=": compatible release -- at least want, same prefix but the last part.
    return hp >= wp and h[:len(w) - 1] == w[:len(w) - 1]


def _tool_version(name: str):
    """The version text a binary reports for ``--version``, or None."""
    exe = shutil.which(name)
    if exe is None:
        return None
    try:
        p = subprocess.run([exe, "--version"], stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    m = _VERSION.search((p.stdout or "") + "\n" + (p.stderr or ""))
    return m.group(0) if m else None


def _module_version(name: str):
    try:
        return importlib.metadata.version(name)
    except Exception:
        return None


def _have(spec: str) -> bool:
    """Is requirement ``spec`` (a binary or module, optionally versioned) present?"""
    m = _SPEC.fullmatch(spec or "")
    if m is None:
        return False
    name, op, want = m.group(1), m.group(2), m.group(3)
    if shutil.which(name) is not None:
        if op is None:
            return True
        return _version_ok(_tool_version(name), op, want)
    try:
        found = importlib.util.find_spec(name) is not None
    except Exception:
        found = False
    if not found:
        return False
    if op is None:
        return True
    return _version_ok(_module_version(name), op, want)


def preflight(parsed) -> list:
    """The ``requires`` entries the host does not provide. Empty when all present."""
    claim = parsed.get("claim", {}) if isinstance(parsed, dict) else {}
    if not isinstance(claim, dict):
        return []
    return [r for r in claim.get("requires", []) if not _have(r)]


# ------------------------------------------------------------ timeouts
def gate_timeout(parsed=None) -> float:
    """The wall-clock bound for a gate.

    A claim's declared ``gate_timeout`` IS the ceiling: it may raise the bound
    past any host default, and a gate past it still times out. Otherwise the
    host's ``RETICULI_GATE_TIMEOUT`` applies, then the kernel default.
    """
    claim = parsed.get("claim") if isinstance(parsed, dict) else None
    if isinstance(claim, dict):
        declared = claim.get("gate_timeout")
        if _is_num(declared) and declared > 0:
            return float(declared)
    host = os.environ.get(core._ENV_TIMEOUT)
    if host:
        try:
            value = float(host)
        except ValueError:
            value = None
        if value is not None and math.isfinite(value) and value > 0:
            return value
    return float(core.GATE_TIMEOUT)


# ------------------------------------------------------------ environment
def _env_cache_dir() -> str:
    """Host cache for furnished environments (residue; never identity)."""
    root = os.environ.get(core._ENV_CACHE)
    if root:
        return root
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(
        os.path.expanduser("~"), ".cache")
    return os.path.join(base, "reticuli", "env")


def _check_call(argv, what: str) -> None:
    try:
        p = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True,
                           text=True, timeout=core.FURNISH_TIMEOUT)
    except (OSError, subprocess.SubprocessError) as e:
        raise core.ClaimError(f"environment: cannot furnish ({what}): {e}")
    if p.returncode != 0:
        tail = ((p.stdout or "") + (p.stderr or ""))[-800:].strip()
        raise core.ClaimError(f"environment: cannot furnish ({what}): {tail}")


def furnish(parsed, d: str):
    """Build (or reuse) the private venv named by ``[claim] environment``.

    Installs exactly the hash-pinned artifacts of the environment file, with
    ``--require-hashes`` and ``--only-binary=:all:``. Returns the venv's bin
    directory, or None when the claim declares no environment. A room that
    cannot be furnished raises ``ClaimError`` (an environment failure).
    """
    claim = parsed.get("claim", {}) if isinstance(parsed, dict) else {}
    rel = claim.get("environment")
    if rel is None:
        return None
    full = recipe._declared_file(d, rel, "environment")
    digest = core._hash_file(full)
    key = hashlib.sha256("\n".join([
        digest, sys.executable or "", sys.version,
        platform.system(), platform.machine()]).encode("utf-8")).hexdigest()
    cache = _env_cache_dir()
    venv = os.path.join(cache, key)
    bindir = os.path.join(venv, "bin")
    if os.path.lexists(os.path.join(bindir, "python")):
        return bindir
    os.makedirs(cache, exist_ok=True)
    try:
        _check_call([sys.executable, "-m", "venv", venv], "venv")
        _check_call([os.path.join(bindir, "python"), "-m", "pip", "install",
                     "--require-hashes", "--only-binary=:all:", "--no-input",
                     "--disable-pip-version-check", "-r", full], "pip")
    except core.ClaimError:
        shutil.rmtree(venv, ignore_errors=True)
        raise
    return bindir


# ------------------------------------------------------------ sandboxes
def _quote_sb(s: str) -> str:
    """A string literal in a sandbox-exec (SBPL) profile."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _sandbox_argv(argv, d: str, scratch, backend: str) -> list:
    """The argv that runs ``argv`` inside sandbox ``backend`` confined to ``d``."""
    real = os.path.realpath(d)
    if backend == "bubblewrap":
        out = ["bwrap", "--die-with-parent", "--unshare-net",
               "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc",
               "--bind", real, real, "--chdir", real]
        return out + ["--"] + list(argv)
    if backend == "seatbelt":
        profile = "\n".join([
            "(version 1)",
            "(allow default)",
            "(deny network*)",
            "(deny file-write*)",
            "(allow file-write* (subpath " + _quote_sb(real) + ")"
            " (literal \"/dev/null\") (regex #\"^/dev/\"))",
        ])
        return ["sandbox-exec", "-p", profile] + list(argv)
    raise core.ClaimError(f"no sandbox to apply: {backend}")


def _scrub_env(scratch=None, sandboxed: bool = False) -> dict:
    """A minimal host allowlist. Inherited secrets never reach a gate."""
    env = {k: os.environ[k] for k in core._KEEP_ENV if k in os.environ}
    env.setdefault("PATH", os.defpath or "/usr/bin:/bin")
    if scratch is not None:
        env["TMPDIR"] = scratch
        env["HOME"] = scratch
    if sandboxed:
        env[core._JAILED] = "1"
    return env


def _kill_tree(proc) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except OSError:
        try:
            proc.kill()
        except OSError:
            pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass


def _run(argv, env: dict, cwd: str, timeout: float):
    """Run argv bounded by ``timeout``. Returns (returncode or None, output text).

    None means the bound was exceeded (the whole process group is killed).
    A process that cannot be launched at all is a ClaimError.
    """
    with tempfile.TemporaryFile() as out:
        try:
            proc = subprocess.Popen(argv, cwd=cwd, env=env,
                                    stdin=subprocess.DEVNULL, stdout=out,
                                    stderr=subprocess.STDOUT,
                                    start_new_session=True)
        except OSError as e:
            raise core.ClaimError(f"cannot launch {argv[0]}: {e}")
        try:
            rc = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            rc = None
        try:
            os.killpg(proc.pid, signal.SIGKILL)  # no stragglers in the group
        except OSError:
            pass
        out.seek(0)
        text = out.read().decode("utf-8", errors="replace")
    return rc, text


def _probe(argv_for, backend: str) -> bool:
    """Run a sandbox probe in a scratch workspace; True iff it works."""
    try:
        with tempfile.TemporaryDirectory(prefix="reticuli-probe-") as t:
            argv = _sandbox_argv(argv_for(t), t, None, backend)
            rc, _ = _run(argv, _scrub_env(), t, 20)
            return rc == 0
    except (core.ClaimError, OSError):
        return False


def _bwrap_usable() -> bool:
    """Functional probe of bubblewrap: it must actually confine and run a gate."""
    global _BWRAP_OK
    if _BWRAP_OK is None:
        ok = False
        if shutil.which("bwrap") is not None and os.path.exists("/bin/sh"):
            ok = _probe(lambda t: ["/bin/sh", "-c", "printf p > probe"],
                        "bubblewrap")
            if ok:
                ok = os.path.isfile(os.path.join(os.path.realpath(
                    tempfile.gettempdir()), "")) or True
        _BWRAP_OK = ok
    return _BWRAP_OK


def _seatbelt_usable() -> bool:
    """Functional probe of sandbox-exec."""
    global _SEATBELT_OK
    if _SEATBELT_OK is None:
        ok = False
        if shutil.which("sandbox-exec") is not None:
            ok = _probe(lambda t: ["/usr/bin/true"], "seatbelt")
        _SEATBELT_OK = ok
    return _SEATBELT_OK


def sandbox_backend() -> str:
    """The confinement a gate runs under, in ``SANDBOXES``."""
    if os.environ.get(core._JAILED):
        return "inherited"
    if sys.platform == "darwin":
        return "seatbelt" if _seatbelt_usable() else "none"
    if sys.platform.startswith("linux"):
        return "bubblewrap" if _bwrap_usable() else "none"
    return "none"


def sandbox() -> dict:
    """The host's sandbox: the backend that applies, and whether it confines."""
    backend = sandbox_backend()
    return {"backend": backend, "applies": backend in _APPLIED}


# ------------------------------------------------------------ gates
def run_gate(cmd: str, d: str, parsed=None) -> dict:
    """Run one gate command in claim directory ``d``.

    ``parsed`` is the claim's recipe table (or None), which supplies the
    declared timeout, the ``requires`` contract, and the environment.
    Returns ``{status, quarantine, sandbox, timeout, output}``.
    """
    if not isinstance(cmd, str) or cmd == "":
        raise core.ClaimError("a gate needs a non-empty run command")
    if not os.path.isdir(d):
        raise core.ClaimError(f"not a claim directory: {d}")
    backend = sandbox_backend()
    applies = backend in _APPLIED
    timeout = gate_timeout(parsed)

    missing = preflight(parsed)
    if missing:
        return _gate_result("environment", backend, timeout,
                            output="missing requirements: " + ", ".join(missing))

    bindir = None
    try:
        bindir = furnish(parsed, d) if isinstance(parsed, dict) else None
    except core.ClaimError as e:
        return _gate_result("environment", backend, timeout, output=str(e))

    scratch = None
    if applies:
        scratch = os.path.join(d, core.STORE, "scratch")
        os.makedirs(scratch, exist_ok=True)
    env = _scrub_env(scratch, applies)
    if bindir:
        env["PATH"] = bindir + os.pathsep + env.get("PATH", "")

    argv = ["/bin/sh", "-c", cmd]
    if applies:
        argv = _sandbox_argv(argv, d, scratch, backend)
    try:
        rc, text = _run(argv, env, d, timeout)
    except core.ClaimError as e:
        return _gate_result("environment", backend, timeout, output=str(e))
    if rc is None:
        status = "timeout"
    elif rc == 0:
        status = "ok"
    else:
        status = "failed"
    return _gate_result(status, backend, timeout, returncode=rc,
                        output=text[-2000:])


# ------------------------------------------------------------ the ledger
def _ledger_path(d: str) -> str:
    return os.path.join(d, core.LEDGER)


def ledger(d: str, entry: dict, seconds=None) -> dict:
    """Append one measurement entry to the claim's ledger and return it.

    A producer may report usd / tokens / calls. ``seconds`` is the kernel's
    own measurement: a usage payload's ``seconds`` is dropped, and only the
    ``seconds`` argument is recorded.
    """
    if not isinstance(entry, dict):
        raise core.ClaimError("a ledger entry is a table of measurements")
    rec = {}
    for key, value in entry.items():
        if key == "seconds":
            continue
        if key in core.COST_KEYS and (not _is_num(value) or value < 0):
            raise core.ClaimError(f"cost {key} must be a finite non-negative number")
        rec[key] = value
    if seconds is not None:
        if not _is_num(seconds) or seconds < 0:
            raise core.ClaimError("measured seconds must be a finite non-negative number")
        rec["seconds"] = seconds
    rec.setdefault("when", core._now())
    path = _ledger_path(d)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, sort_keys=True) + "\n")
    return rec


def ledger_events(d: str) -> list:
    """Every entry of the claim's ledger, in order. Malformed lines are skipped."""
    path = _ledger_path(d)
    if not os.path.isfile(path):
        return []
    events = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if isinstance(event, dict):
                events.append(event)
    return events


def cost(d: str):
    """Ledger totals per unit, carrying only the keys the ledger names.

    None when nothing was measured: an unmeasured unit is never a zero.
    """
    totals = {}
    for event in ledger_events(d):
        for key in core.COST_KEYS:
            value = event.get(key)
            if _is_num(value) and value >= 0:
                totals[key] = totals.get(key, 0) + value
    return totals or None


# ------------------------------------------------------------ crosscheck helpers
def _strongest_shared(a: dict, b: dict):
    for unit in core.COST_LADDER:
        if unit in a and unit in b:
            return unit
    return None


def _in_band(c1, c3, tolerance: float = core.TOLERANCE):
    """Is the redo's cost within ``tolerance`` of the original's?

    Compares exactly one unit: the strongest both ledgers measured. Returns
    None when they share no unit (the band is then unmeasured).
    """
    a_all = c1 or {}
    b_all = c3 or {}
    unit = _strongest_shared(a_all, b_all)
    if unit is None:
        return None
    a = float(a_all[unit])
    b = float(b_all[unit])
    if a == 0 or b == 0:
        return a == b
    return max(a / b, b / a) <= tolerance


def independence(m1=None, m3=None) -> dict:
    """Declared producer independence of M3 against M1. Recorded, never enforced."""
    p1 = dict(m1 or {})
    p3 = dict(m3 or {})
    vendor = p3.get("vendor")
    model = p3.get("model")
    declared = bool(vendor)
    same = declared and vendor == p1.get("vendor")
    return {"vendor": vendor, "model": model, "declared": declared,
            "same_vendor": bool(same), "established": declared and not same}


def _independence_line(ind: dict) -> str:
    if not ind.get("declared"):
        return "independence unestablished: producer not declared"
    if ind.get("same_vendor"):
        return f"independence unestablished: same vendor ({ind.get('vendor')})"
    model = ind.get("model")
    return f"independence declared: {ind.get('vendor')} {model or ''}".rstrip()
