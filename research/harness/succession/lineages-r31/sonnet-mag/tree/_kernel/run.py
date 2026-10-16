"""Kernel run: confined gate execution, environment contract, cost ledger.

A gate runs under a platform sandbox (seatbelt on macOS, bubblewrap on Linux)
that is probed *functionally*; a host with no working sandbox reports `none`
honestly, and a process already inside one reports `inherited`. Gates run
with a scrubbed environment and a wall-clock bound.
"""
import hashlib
import importlib.util
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time

from . import core
from .core import ClaimError

_REQ_OPS = ("<=", ">=", "==", "!=", "~=", "<", ">")
_BWRAP_OK = None          # cached functional probe of bubblewrap
_SB_OK = None             # cached functional probe of seatbelt

_FALLBACK_PATH = "/usr/local/bin:/usr/bin:/bin"


# --------------------------------------------------------------- helpers

def _have(name: str) -> bool:
    """True if `name` is a binary on PATH or an importable Python module."""
    if not isinstance(name, str) or not name:
        return False
    if shutil.which(name):
        return True
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError, AttributeError):
        return False


def _version_tuple(text) -> tuple:
    """Leading dotted integers of a version string, e.g. '1.2.3rc1' -> (1,2,3)."""
    m = re.search(r"\d+(?:\.\d+)*", str(text))
    if not m:
        return ()
    return tuple(int(x) for x in m.group(0).split("."))


def _tool_version(name: str):
    """Best-effort version string of a binary or module, or None."""
    exe = shutil.which(name)
    if exe:
        for flag in ("--version", "-V", "version"):
            try:
                done = subprocess.run([exe, flag], capture_output=True,
                                      text=True, timeout=20, check=False,
                                      stdin=subprocess.DEVNULL)
            except (OSError, subprocess.SubprocessError):
                continue
            out = (done.stdout or "") + " " + (done.stderr or "")
            if _version_tuple(out):
                return ".".join(str(x) for x in _version_tuple(out))
    try:
        from importlib import metadata
        return metadata.version(name)
    except Exception:
        pass
    try:
        mod = importlib.import_module(name)
        v = getattr(mod, "__version__", None)
        return str(v) if v is not None else None
    except Exception:
        return None


def _pad(a: tuple, b: tuple):
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)), b + (0,) * (n - len(b))


def _version_ok(found, op: str, wanted) -> bool:
    """Does version `found` satisfy `op wanted`?"""
    f, w = _version_tuple(found), _version_tuple(wanted)
    if not f or not w:
        return False
    fp, wp = _pad(f, w)
    if op == "<=":
        return fp <= wp
    if op == ">=":
        return fp >= wp
    if op == "==":
        return fp == wp
    if op == "!=":
        return fp != wp
    if op == "<":
        return fp < wp
    if op == ">":
        return fp > wp
    if op == "~=":
        if fp < wp:
            return False
        prefix = w[:-1] if len(w) > 1 else w
        return f[:len(prefix)] == prefix
    return False


def _split_req(req: str):
    """'name>=1.2' -> ('name', '>=', '1.2'); 'name' -> ('name', None, None)."""
    for i, ch in enumerate(req):
        if ch in "<>=!~":
            for op in _REQ_OPS:
                if req.startswith(op, i):
                    return req[:i].strip(), op, req[i + len(op):].strip()
            break
    return req.strip(), None, None


def preflight(recipe) -> list:
    """The `requires` the host cannot provide (empty list: all present)."""
    claim = recipe.get("claim", {}) if isinstance(recipe, dict) else {}
    missing = []
    for req in (claim.get("requires") or []) if isinstance(claim, dict) else []:
        name, op, want = _split_req(req)
        if not name or not _have(name):
            missing.append(req)
        elif op is not None and not _version_ok(_tool_version(name), op, want):
            missing.append(req)
    return missing


def _in_band(base, other, tolerance=core.TOLERANCE) -> bool:
    """Is `other` within `tolerance` times `base` (in either direction)?"""
    try:
        base, other, tolerance = float(base), float(other), float(tolerance)
    except (TypeError, ValueError):
        return False
    if base <= 0 or other <= 0:
        return base == other
    ratio = other / base
    return 1.0 / tolerance <= ratio <= tolerance


def _independence_line(info) -> str:
    """One human line for an independence record."""
    vendor = (info or {}).get("vendor") if isinstance(info, dict) else None
    model = (info or {}).get("model") if isinstance(info, dict) else None
    if isinstance(info, dict) and info.get("established"):
        return (f"independence declared: producer {vendor or '?'}"
                f"/{model or '?'} differs from the original")
    if isinstance(info, dict) and info.get("declared"):
        return (f"independence unestablished: same vendor "
                f"({vendor or '?'}/{model or '?'})")
    return "independence unestablished: producer not declared"


def independence(m3=None, original=None) -> dict:
    """Declared producer independence of a crosscheck (observed, not enforced)."""
    def norm(x):
        if isinstance(x, dict):
            return {"vendor": x.get("vendor"), "model": x.get("model")}
        if isinstance(x, str) and x:
            return {"vendor": x, "model": None}
        return {"vendor": None, "model": None}
    a, b = norm(m3), norm(original)
    declared = bool(a["vendor"])
    established = bool(declared and b["vendor"] and a["vendor"] != b["vendor"])
    out = {"vendor": a["vendor"], "model": a["model"], "declared": declared,
           "established": established}
    out["line"] = _independence_line(out)
    return out


# ---------------------------------------------------------------- ledger

def _ledger_path(d: str) -> str:
    return core._safe(d, core.LEDGER)


def ledger(d: str, event: dict) -> dict:
    """Append one event to the claim's cost ledger."""
    if not isinstance(event, dict):
        raise ClaimError("a ledger event must be an object")
    entry = dict(event)
    entry.setdefault("at", core._now())
    entry.setdefault("host", core._judging_host())
    path = _ledger_path(d)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())
    return entry


def ledger_events(d: str) -> list:
    """Every event in the ledger, in order (unreadable lines are skipped)."""
    path = _ledger_path(d)
    events = []
    try:
        with open(path, "rb") as f:
            raw = f.read().decode("utf-8", "replace")
    except OSError:
        return events
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if isinstance(e, dict):
            events.append(e)
    return events


def cost(d: str):
    """Ledger totals per unit; None if nothing was measured."""
    totals = {}
    for e in ledger_events(d):
        for key in core.COST_KEYS:
            v = e.get(key)
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                continue
            totals[key] = totals.get(key, 0) + v
    return totals or None


# --------------------------------------------------------------- timeout

def gate_timeout(recipe) -> float:
    """The wall-clock ceiling: the claim's declaration, else the host default."""
    claim = recipe.get("claim") if isinstance(recipe, dict) else None
    if isinstance(claim, dict):
        v = claim.get("gate_timeout")
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
            return v
    raw = os.environ.get(core._ENV_TIMEOUT)
    if raw:
        try:
            v = float(raw)
            if v > 0:
                return v
        except ValueError:
            pass
    return core.GATE_TIMEOUT


# --------------------------------------------------------------- process

def _kill_tree(proc) -> None:
    """Kill a process and everything in its group."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (OSError, AttributeError):
        try:
            proc.kill()
        except OSError:
            pass


def _run(argv, cwd, env, timeout):
    """Run argv bounded. Returns (returncode, output_text, timed_out)."""
    try:
        proc = subprocess.Popen(argv, cwd=cwd, env=env,
                                stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT,
                                start_new_session=True)
    except OSError as e:
        return 127, f"cannot start: {e}", False
    timed_out = False
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_tree(proc)
        try:
            out, _ = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            out = b""
    # reap any stragglers left in the group
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except OSError:
        pass
    text = (out or b"").decode("utf-8", "replace")
    rc = proc.returncode if proc.returncode is not None else -9
    return rc, text, timed_out


# --------------------------------------------------------------- sandbox

def _quote_sb(path: str) -> str:
    """A string literal for a seatbelt profile."""
    return '"' + str(path).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _seatbelt_profile(d: str) -> str:
    root = os.path.realpath(d)
    return "\n".join([
        "(version 1)",
        "(allow default)",
        "(deny network*)",
        "(deny file-write*)",
        f"(allow file-write* (subpath {_quote_sb(root)}))",
        '(allow file-write* (literal "/dev/null") (literal "/dev/zero")'
        ' (literal "/dev/dtracehelper") (regex #"^/dev/tty")'
        ' (regex #"^/dev/fd/") (subpath "/dev/fd"))',
        "",
    ])


def _sandbox_argv(backend: str, d: str, argv: list) -> list:
    """Wrap argv for the backend; unchanged for none/inherited."""
    root = os.path.realpath(d)
    if backend == "bubblewrap":
        return ["bwrap", "--ro-bind", "/", "/", "--dev", "/dev",
                "--bind", root, root, "--unshare-net", "--die-with-parent",
                "--chdir", root, "--"] + list(argv)
    if backend == "seatbelt":
        return ["sandbox-exec", "-p", _seatbelt_profile(d)] + list(argv)
    return list(argv)


def _probe(backend: str) -> bool:
    """Functionally probe a backend: it must run a process, permit writes in
    the workspace, and deny writes outside it and the network."""
    work = tempfile.mkdtemp(prefix="reticuli-probe-")
    outside = tempfile.mkdtemp(prefix="reticuli-probe-out-")
    try:
        env = {"PATH": os.environ.get("PATH") or _FALLBACK_PATH}
        py = sys.executable or "python3"

        def go(cmd, timeout=30):
            argv = _sandbox_argv(backend, work, ["/bin/sh", "-c", cmd])
            return _run(argv, work, env, timeout)

        rc, _, to = go("echo x > /dev/null && printf v > inside")
        if rc != 0 or to or not os.path.isfile(os.path.join(work, "inside")):
            return False
        rc, _, to = go(f"echo leak > {outside}/LEAK")
        if rc == 0 or os.path.exists(os.path.join(outside, "LEAK")):
            return False
        rc, _, to = go(
            f"\"{py}\" -c \"import socket; s = socket.socket(); "
            f"s.bind(('127.0.0.1', 0))\"")
        if rc == 0 or to:
            return False
        return True
    except Exception:
        return False
    finally:
        shutil.rmtree(work, ignore_errors=True)
        shutil.rmtree(outside, ignore_errors=True)


def _bwrap_usable() -> bool:
    global _BWRAP_OK
    if _BWRAP_OK is None:
        _BWRAP_OK = bool(sys.platform.startswith("linux")
                         and shutil.which("bwrap") and _probe("bubblewrap"))
    return _BWRAP_OK


def _seatbelt_usable() -> bool:
    global _SB_OK
    if _SB_OK is None:
        _SB_OK = bool(sys.platform == "darwin"
                      and shutil.which("sandbox-exec") and _probe("seatbelt"))
    return _SB_OK


def sandbox_backend() -> str:
    """none | seatbelt | bubblewrap | inherited."""
    if os.environ.get(core._JAILED):
        return "inherited"
    if sys.platform == "darwin" and _seatbelt_usable():
        return "seatbelt"
    if sys.platform.startswith("linux") and _bwrap_usable():
        return "bubblewrap"
    return "none"


def sandbox() -> dict:
    """Functional probe of the host sandbox."""
    backend = sandbox_backend()
    return {"backend": backend, "confined": backend in ("seatbelt", "bubblewrap"),
            "platform": sys.platform}


# ------------------------------------------------------------------- env

def _scrub_env(d: str, recipe=None, backend: str = "none", extra=None) -> dict:
    """A minimal allowlisted environment plus the claim's own variables."""
    env = {}
    for k in core._KEEP_ENV:
        if k in os.environ:
            env[k] = os.environ[k]
    env.setdefault("PATH", _FALLBACK_PATH)
    if isinstance(recipe, dict):
        claim = recipe.get("claim", {})
        if isinstance(claim, dict) and isinstance(claim.get("name"), str):
            env[core._ENV_CLAIM] = claim["name"]
    if backend in ("seatbelt", "bubblewrap"):
        scratch = os.path.join(os.path.realpath(d), core.STORE, "scratch")
        os.makedirs(scratch, exist_ok=True)
        env["TMPDIR"] = scratch
        env["HOME"] = scratch
        env[core._JAILED] = "1"
    if extra:
        for k, v in extra.items():
            if isinstance(k, str) and isinstance(v, str):
                env[k] = v
    return env


# -------------------------------------------------------------- furnish

def _env_cache_dir(digest: str) -> str:
    """Host cache directory for a furnished environment."""
    base = os.environ.get(core._ENV_CACHE)
    if not base:
        home = os.path.expanduser("~")
        base = os.path.join(home, ".cache", "reticuli", "env")
    key = "-".join([digest, platform.python_version(), sys.platform,
                    platform.machine() or "any"])
    return os.path.join(base, key)


def furnish(d: str, recipe) -> str:
    """Build (or reuse) the private venv named by `[claim] environment`.

    Returns the venv's bin directory, or None when no environment is declared.
    Raises ClaimError when the room cannot be furnished."""
    claim = recipe.get("claim", {}) if isinstance(recipe, dict) else {}
    name = claim.get("environment") if isinstance(claim, dict) else None
    if not name:
        return None
    path = core._safe(d, name)
    try:
        with open(path, "rb") as f:
            digest = hashlib.sha256(f.read()).hexdigest()
    except OSError as e:
        raise ClaimError(f"cannot read environment file {name!r}: {e}")
    venv = _env_cache_dir(digest)
    bindir = os.path.join(venv, "Scripts" if os.name == "nt" else "bin")
    marker = os.path.join(venv, ".furnished")
    if os.path.isfile(marker) and os.path.isdir(bindir):
        return bindir
    shutil.rmtree(venv, ignore_errors=True)
    os.makedirs(os.path.dirname(venv), exist_ok=True)
    env = {k: v for k, v in os.environ.items()
           if k in core._KEEP_ENV or k.upper().endswith("_PROXY")
           or k in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "PIP_INDEX_URL",
                    "PIP_EXTRA_INDEX_URL")}
    env.setdefault("PATH", _FALLBACK_PATH)
    timeout = core.FURNISH_TIMEOUT
    rc, out, to = _run([sys.executable, "-m", "venv", venv], d, env, timeout)
    if rc != 0 or to:
        shutil.rmtree(venv, ignore_errors=True)
        raise ClaimError(f"cannot create environment: {out.strip()[-300:]}")
    py = os.path.join(bindir, "python")
    rc, out, to = _run([py, "-m", "pip", "install", "--require-hashes",
                        "--only-binary=:all:", "--no-input",
                        "--disable-pip-version-check", "-r", path],
                       d, env, timeout)
    if rc != 0 or to:
        shutil.rmtree(venv, ignore_errors=True)
        raise ClaimError("cannot furnish environment: "
                         + ("timed out" if to else out.strip()[-300:]))
    with open(marker, "w", encoding="utf-8") as f:
        f.write(digest + "\n")
    return bindir


# -------------------------------------------------------------- run_gate

def run_gate(command: str, d: str, recipe=None, env=None) -> dict:
    """Run one gate command in claim dir `d`: scrubbed, sandboxed, bounded.

    Status: ok | failed | timeout | environment."""
    backend = sandbox_backend()
    result = {"status": "failed", "quarantine": backend, "returncode": None,
              "seconds": 0.0, "output": ""}
    if not isinstance(command, str) or not command.strip():
        result["output"] = "empty gate command"
        return result

    missing = preflight(recipe) if isinstance(recipe, dict) else []
    if missing:
        result["status"] = "environment"
        result["output"] = "missing requirements: " + ", ".join(missing)
        result["missing"] = missing
        return result

    venv_bin = None
    if isinstance(recipe, dict):
        try:
            venv_bin = furnish(d, recipe)
        except ClaimError as e:
            result["status"] = "environment"
            result["output"] = str(e)
            return result

    genv = _scrub_env(d, recipe, backend, env)
    if venv_bin:
        genv["PATH"] = venv_bin + os.pathsep + genv.get("PATH", _FALLBACK_PATH)
        genv["VIRTUAL_ENV"] = os.path.dirname(venv_bin)

    root = os.path.realpath(d)
    argv = _sandbox_argv(backend, d, [core._SHELL, "-c", command])
    t0 = time.monotonic()
    rc, out, timed_out = _run(argv, root, genv, gate_timeout(recipe))
    result["seconds"] = time.monotonic() - t0
    result["returncode"] = rc
    result["output"] = out[-4000:]
    if timed_out:
        result["status"] = "timeout"
    elif rc == 0:
        result["status"] = "ok"
    else:
        result["status"] = "failed"
    return result
