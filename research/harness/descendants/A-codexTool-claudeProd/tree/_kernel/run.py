"""Confined gate execution, the cost ledger, and the environment contract.

Every gate runs the same way, whichever verb invoked it (`spec/claim-format.md`,
*Gate execution contract*): a scrubbed environment, so a hostile gate cannot
read an inherited secret and seal it into a verdict; inside a platform
sandbox where the host has a functional one, probed functionally rather than
by looking for a binary; bounded by wall-clock; and handed a TMPDIR and HOME
it can actually write, inside the claim's own store.

That last clause is not a convenience.  A real sandbox permits writes only
inside the claim, so a TMPDIR inherited from the host names paths the gate is
forbidden to touch — and any gate using `tempfile` would then fail ONLY where
confinement is real, passing on every host without a sandbox and failing on
every host with one.

Sandboxes do not nest, and BOTH halves of that contract live here: given
`RETICULI_JAILED` this layer inherits rather than re-applying, and when it
DOES apply one it tells the wrapped process which backend it is inside — a
gate that is itself a claim runner needs to know, or it tries to nest and
dies with `sandbox_apply: Operation not permitted`.

The jail's FLOOR is a property, not a profile: a legitimate gate must survive
it.  A gate may sink to `/dev/null`, spawn a subprocess, read the host it
runs on, ask the host its name, and look up the user it runs as; the network
and writes beyond the workspace stay denied.  Each plank was added because a
deny-by-default jail refused a TRUE criterion and reported no reason.
"""
import hashlib
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import time

from .core import (COST_KEYS, ClaimError, FURNISH_TIMEOUT, GATE_TIMEOUT,
                   LEDGER, SCRATCH, STORE, _ENV_CACHE, _ENV_TIMEOUT, _JAILED,
                   _KEEP_ENV, _SHELL, _finite, _judging_host, _now)

#: The comparison operators a `requires` entry may carry.
_REQ_OPS = ("<=", ">=", "==", "!=", "~=", "<", ">")

#: Whether this host's bwrap actually works — probed once, then remembered.
#: bwrap on a PATH where user namespaces are blocked is not a sandbox anyone
#: declined, so presence is never taken for function.
_BWRAP_OK = None

_VERSION_RE = re.compile(r"(\d+(?:\.\d+)*)")

#: The functional sandbox probe's answer, remembered per backend.  Whether a
#: backend works is a property of the HOST, not of the claim in front of it,
#: and re-probing per gate turned a linear deep audit into a visibly slower
#: one for no information.
_PROBED: dict = {}


# -- the ledger -------------------------------------------------------------


def _ledger_path(claimdir: str) -> str:
    return os.path.join(claimdir, LEDGER)


def ledger(claimdir: str, event: dict) -> None:
    """Append one event to the claim's ledger — residue, outside the root."""
    path = _ledger_path(claimdir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    line = json.dumps(dict(event), sort_keys=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def locked_append(path: str, line: str) -> None:
    """Append a line to a residue file, creating its parent."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(line.rstrip("\n") + "\n")


def ledger_events(claimdir: str) -> list:
    """Every event the ledger holds; damaged lines are skipped, never fatal."""
    path = _ledger_path(claimdir)
    if not os.path.isfile(path):
        return []
    out = []
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if isinstance(event, dict):
                    out.append(event)
    except (OSError, UnicodeDecodeError):
        return out
    return out


def cost(claimdir: str):
    """Ledger totals per unit, or None when nothing was measured.

    Totals carry only the keys the ledger NAMES: an unmeasured machine is
    reported, never guessed at, so a reader can always tell "free" from
    "unknown".  A boolean or a non-finite number is not a measurement and
    does not enter a total — a total is what a declared ceiling is compared
    against.  Discovery-scoped events (an authoring session's own bill) total
    separately: they are testimony beside the band, never inside it.
    """
    events = ledger_events(claimdir)
    if not events:
        return None
    totals: dict = {}
    discovery: dict = {}
    for event in events:
        bucket = discovery if event.get("scope") == "discovery" else totals
        for key in COST_KEYS:
            value = event.get(key)
            if _finite(value):
                bucket[key] = bucket.get(key, 0) + value
    out = dict(totals)
    if discovery:
        out["discovery"] = discovery
    return out


def _in_band(a: float, b: float, tolerance: float) -> bool:
    """Is a/b inside the CLOSED band [1/tolerance, tolerance]?

    Closed on purpose: an open interval would refuse a redo whose ratio sits
    exactly on the declared tolerance, so two conforming implementations
    would disagree about a verdict at the boundary.
    """
    try:
        a, b, tolerance = float(a), float(b), float(tolerance)
    except (TypeError, ValueError):
        return False
    if tolerance <= 0 or b == 0:
        return a == b
    ratio = a / b
    eps = 1e-9 * max(1.0, tolerance)
    return (1.0 / tolerance) - eps <= ratio <= tolerance + eps


# -- the environment contract -----------------------------------------------


def _version_tuple(text: str) -> tuple:
    found = _VERSION_RE.search(text or "")
    if not found:
        return ()
    return tuple(int(p) for p in found.group(1).split("."))


def _tool_version(name: str):
    """The version a required tool reports, or None if it will not say."""
    if name in ("python", "python3"):
        return platform.python_version()
    binary = shutil.which(name)
    if not binary:
        return None
    for flag in ("--version", "-version", "-V"):
        try:
            done = subprocess.run([binary, flag], capture_output=True,
                                  text=True, timeout=20, check=False)
        except (OSError, subprocess.SubprocessError):
            continue
        text = (done.stdout or "") + (done.stderr or "")
        if _VERSION_RE.search(text):
            return _VERSION_RE.search(text).group(1)
    return None


def _version_ok(have: str, op: str, want: str) -> bool:
    left, right = _version_tuple(have), _version_tuple(want)
    if not left or not right:
        return False
    width = max(len(left), len(right))
    left += (0,) * (width - len(left))
    right += (0,) * (width - len(right))
    if op == ">=":
        return left >= right
    if op == "<=":
        return left <= right
    if op == ">":
        return left > right
    if op == "<":
        return left < right
    if op == "==":
        return left == right
    if op == "!=":
        return left != right
    if op == "~=":                       # compatible release, pip's spelling
        return left >= right and left[:len(right) - 1] == right[:len(right) - 1]
    return False


def _have(requirement: str) -> bool:
    """Is one declared requirement satisfied on this host?

    A requirement names a binary or a Python module, optionally with a
    version constraint.  `requires` asserts PRESENCE, which is why a verdict
    may not depend on a granted value.
    """
    text = (requirement or "").strip()
    if not text:
        return True
    name, op, want = text, None, None
    for candidate in _REQ_OPS:
        if candidate in text:
            name, _, want = text.partition(candidate)
            op, name, want = candidate, name.strip(), want.strip()
            break
    if not name:
        return False
    present = bool(shutil.which(name)) or name in ("python", "python3")
    if not present:
        try:
            import importlib.util
            present = importlib.util.find_spec(name) is not None
        except (ImportError, ValueError, ModuleNotFoundError):
            present = False
    if not present:
        return False
    if op is None:
        return True
    have = _tool_version(name)
    return bool(have) and _version_ok(have, op, want)


def preflight(parsed: dict) -> list:
    """What the host is missing — names, so the refusal is a sentence.

    A missing requirement classifies a gate outcome as `environment`: the
    host cannot judge this claim, which is distinct from the claim being
    wrong.  Nothing is proven and nothing disproven.
    """
    claim = (parsed or {}).get("claim", {}) if isinstance(parsed, dict) else {}
    return [r for r in (claim.get("requires") or []) if not _have(r)]


# -- the sandbox ------------------------------------------------------------


def _quote_sb(path: str) -> str:
    """Quote a path for a seatbelt profile string."""
    return path.replace("\\", "\\\\").replace('"', '\\"')


def _bwrap_usable() -> bool:
    """Probe bwrap FUNCTIONALLY: present-but-blocked counts as no sandbox."""
    global _BWRAP_OK
    if _BWRAP_OK is None:
        if not shutil.which("bwrap"):
            _BWRAP_OK = False
        else:
            try:
                done = subprocess.run(
                    ["bwrap", "--ro-bind", "/", "/", "--unshare-net", "true"],
                    capture_output=True, timeout=30, check=False)
                _BWRAP_OK = done.returncode == 0
            except (OSError, subprocess.SubprocessError):
                _BWRAP_OK = False
    return _BWRAP_OK


def sandbox_backend() -> str:
    """Which confinement this host applies: the honest word, always one of
    `none`, `seatbelt`, `bubblewrap`, `inherited`."""
    if os.environ.get(_JAILED):
        return "inherited"
    if sys.platform == "darwin" and shutil.which("sandbox-exec"):
        return "seatbelt"
    if _bwrap_usable():
        return "bubblewrap"
    return "none"


def _sandbox_argv(backend: str, claim_real: str) -> list:
    """The wrapper that confines a gate to its claim.

    The floor is a PROPERTY — a legitimate gate survives the jail — not a
    profile syntax, so this allows by default and denies the two things that
    matter: the network, and writes beyond the workspace.  A
    deny-by-default allowlist is equally conforming and was measured
    refusing real criteria five separate ways.
    """
    if backend == "seatbelt":
        profile = ("(version 1)(allow default)(deny network*)"
                   "(deny file-write*)"
                   f'(allow file-write* (subpath "{_quote_sb(claim_real)}") '
                   '(subpath "/dev"))')
        return ["sandbox-exec", "-p", profile]
    if backend == "bubblewrap":
        return ["bwrap", "--ro-bind", "/", "/",
                "--dev-bind", "/dev", "/dev", "--proc", "/proc",
                "--bind", claim_real, claim_real,
                "--unshare-net", "--die-with-parent"]
    return []


def _run(argv: list, **kwargs):
    """One subprocess, with text pipes and no inherited stdin."""
    kwargs.setdefault("capture_output", True)
    kwargs.setdefault("text", True)
    kwargs.setdefault("check", False)
    kwargs.setdefault("stdin", subprocess.DEVNULL)
    return subprocess.run(argv, **kwargs)


def sandbox(command: str = "true", claimdir: str = None) -> tuple:
    """Probe the host's sandbox functionally.

    Returns `(ok, backend, detail)`.  A present-but-nonfunctional sandbox
    counts as none and is reported honestly rather than claimed.
    """
    backend = sandbox_backend()
    if backend in ("none", "inherited"):
        return (True, backend, "no sandbox applied")
    if command == "true" and backend in _PROBED:
        return _PROBED[backend]
    where = os.path.realpath(claimdir or os.getcwd())
    argv = _sandbox_argv(backend, where) + [_SHELL, "-c", command]
    try:
        done = _run(argv, cwd=where, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        answer = (False, "none", f"{backend} is present but unusable: {exc}")
        if command == "true":
            _PROBED[backend] = answer
        return answer
    if done.returncode != 0 and command == "true":
        answer = (False, "none",
                  f"{backend} is present but unusable: "
                  f"{(done.stderr or '').strip()[:200]}")
        _PROBED[backend] = answer
        return answer
    answer = (done.returncode == 0, backend, (done.stderr or "").strip()[:200])
    if command == "true":
        _PROBED[backend] = answer
    return answer


def _kill_tree(proc) -> None:
    """Kill the whole process group, not just the direct child.

    A gate whose runaway is a grandchild — spawned through an interpreter,
    outliving the shell the kill first reaches — must be refused on the same
    schedule as one that hangs by itself: the ceiling bounds the WORK.
    """
    for sig in (signal.SIGKILL, signal.SIGKILL):
        try:
            os.killpg(os.getpgid(proc.pid), sig)
        except (OSError, ProcessLookupError):
            try:
                proc.kill()
            except OSError:
                pass
        if proc.poll() is not None:
            return
        time.sleep(0.05)


def gate_timeout(parsed) -> float:
    """The wall-clock ceiling in force for this claim's gates.

    A DECLARED `gate_timeout` IS the ceiling, raisable past any
    implementation default — a kernel that combined the declaration with its
    own default by `min()` was structurally unable to audit the repository
    that declares its own window.  The host ceiling
    (`RETICULI_GATE_TIMEOUT`) still caps it: a verifier may tighten, never
    loosen.
    """
    declared = None
    if isinstance(parsed, dict):
        claim = parsed.get("claim")
        if isinstance(claim, dict):
            declared = claim.get("gate_timeout")
    limit = float(declared) if (_finite(declared) and declared > 0) \
        else float(GATE_TIMEOUT)
    host = os.environ.get(_ENV_TIMEOUT)
    if host:
        try:
            limit = min(limit, float(host))
        except (TypeError, ValueError):
            pass
    return limit


def _scrub_env(claimdir: str, backend: str, scratch: str,
               extra: dict = None) -> dict:
    """A gate's environment: a minimal host allowlist, nothing inherited.

    Secrets never reach a gate, so a hostile one cannot exfiltrate them and
    an honest one cannot accidentally seal one into a verdict.  Where a
    sandbox is applied, TMPDIR and HOME point inside the claim's store, and
    the backend's own name is handed over so a gate that itself runs claims
    inherits rather than nesting.
    """
    env = {key: os.environ[key] for key in _KEEP_ENV if key in os.environ}
    env.setdefault("PATH", os.defpath)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if scratch:
        env["TMPDIR"] = scratch
        env["HOME"] = scratch
    if backend in ("seatbelt", "bubblewrap"):
        env[_JAILED] = backend
    if extra:
        env.update({k: v for k, v in extra.items() if v is not None})
    return env


def _scratch_dir(claim_real: str) -> str:
    where = os.path.join(claim_real, SCRATCH)
    try:
        os.makedirs(where, exist_ok=True)
    except OSError:
        return ""
    return os.path.realpath(where)


def run_gate(command: str, claimdir: str, parsed, timeout: float = None,
             strict: bool = True, venv: str = None, env_extra: dict = None,
             record: bool = False) -> dict:
    """Run one gate: scrubbed, sandboxed, bounded — and say which jail.

    The outcome is classified, because "it failed" is never the whole
    verdict: `ok` ran clean, `failed` exited nonzero, `timeout` exceeded the
    ceiling.  `mismatch` and `environment` are decided one layer out, where
    the pinned bytes and the host contract are known.
    """
    claim_real = os.path.realpath(claimdir)
    probe_ok, backend, detail = sandbox(claimdir=claim_real) \
        if strict else (True, "none", "sandbox declined by the caller")
    if not probe_ok:
        backend = "none"
    scratch = _scratch_dir(claim_real)
    extra = dict(env_extra or {})
    env = _scrub_env(claim_real, backend, scratch, extra)
    if venv:
        env["PATH"] = os.path.join(venv, "bin") + os.pathsep + env["PATH"]
        env["VIRTUAL_ENV"] = venv
    limit = timeout if timeout is not None else gate_timeout(parsed)
    argv = _sandbox_argv(backend, claim_real) + [_SHELL, "-c", command]

    started = time.monotonic()
    status, out, err = "ok", "", ""
    try:
        proc = subprocess.Popen(argv, cwd=claim_real, env=env,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                stdin=subprocess.DEVNULL,
                                text=True, start_new_session=True)
    except OSError as exc:
        return {"status": "failed", "quarantine": backend, "stdout": "",
                "stderr": f"the gate could not be started: {exc}",
                "command": command, "seconds": 0.0, "code": None}
    try:
        out, err = proc.communicate(timeout=limit)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        try:
            out, err = proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            out, err = "", ""
        status = "timeout"
    if status != "timeout":
        status = "ok" if proc.returncode == 0 else "failed"
    elapsed = time.monotonic() - started

    outcome = {"status": status, "quarantine": backend,
               "stdout": out or "", "stderr": err or "",
               "command": command, "seconds": elapsed,
               "code": proc.returncode, "sandbox_detail": detail}
    if record:
        ledger(claimdir, {"event": "gate", "command": command,
                          "status": status, "quarantine": backend,
                          "seconds": elapsed, "when": _now()})
    return outcome


def confinement(claimdir: str, strict: bool = True,
                scratch: str = None) -> dict:
    """The wrapper argv and scrubbed environment a confined child needs.

    Exposed because a layer above the kernel sometimes has to run a child
    ITSELF rather than through `run_gate` — the launcher must hand the
    entrypoint's stdout straight through, byte for byte, and a captured pipe
    cannot do that.  What it must not do is reinvent the confinement, so the
    shape is handed out from the one place that owns it.
    """
    claim_real = os.path.realpath(claimdir)
    if strict:
        probe_ok, backend, detail = sandbox(claimdir=claim_real)
        if not probe_ok:
            backend = "none"
    else:
        backend, detail = "off", "confinement declined by the caller"
    where = scratch or _scratch_dir(claim_real)
    env = _scrub_env(claim_real, backend if backend != "off" else "none",
                     where)
    return {"argv": _sandbox_argv(backend, claim_real) if strict else [],
            "quarantine": backend, "env": env, "cwd": claim_real,
            "detail": detail}


# -- the declared environment: furnish --------------------------------------


def _env_cache_dir() -> str:
    """Where furnished environments are cached — host residue, never identity."""
    where = os.environ.get(_ENV_CACHE)
    if not where:
        where = os.path.join(os.path.expanduser("~"), ".cache", "reticuli",
                             "environments")
    os.makedirs(where, exist_ok=True)
    return where


def _lock_requirements(text: str) -> list:
    out = []
    for line in text.splitlines():
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        token = entry.split()[0]
        if token.startswith("-"):
            continue
        out.append(token)
    return out


def furnish(parsed: dict, claimdir: str) -> dict:
    """Build the private venv a claim's `[claim] environment` names.

    Dependency versions decide what "passes" means, so the lock file is a
    criterion and every installable artifact in it is named by its content
    hash: `--require-hashes`, so nothing unnamed can arrive, and
    `--only-binary=:all:`, so nothing executes at install time.  A room that
    cannot be furnished is an `environment` failure — the gates were not
    run, nothing proven, nothing disproven.
    """
    claim = (parsed or {}).get("claim", {})
    declared = claim.get("environment")
    if not declared:
        return {"ok": True, "venv": None, "reason": None}
    from .core import _safe
    lock = _safe(claimdir, declared)
    if not os.path.isfile(lock):
        return {"ok": False, "venv": None,
                "reason": f"the declared environment {declared!r} is missing"}
    with open(lock, "rb") as handle:
        raw = handle.read()
    key = hashlib.sha256(
        raw + f"|{sys.version}|{sys.platform}".encode()).hexdigest()[:32]
    where = os.path.join(_env_cache_dir(), key)
    stamp = os.path.join(where, ".furnished")
    if os.path.isfile(stamp):
        return {"ok": True, "venv": where, "reason": None}
    shutil.rmtree(where, ignore_errors=True)
    try:
        done = _run([sys.executable, "-m", "venv", where],
                    timeout=FURNISH_TIMEOUT)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "venv": None, "reason": f"venv: {exc}"}
    if done.returncode != 0:
        return {"ok": False, "venv": None,
                "reason": f"venv: {(done.stderr or '').strip()[-300:]}"}
    python = os.path.join(where, "bin", "python")
    requirements = _lock_requirements(raw.decode("utf-8", "replace"))
    local_only = bool(requirements) and all(
        r.startswith(("./", "../", "/")) or r.endswith(".whl")
        for r in requirements)
    argv = [python, "-m", "pip", "install", "--no-input",
            "--disable-pip-version-check", "--require-hashes",
            "--only-binary=:all:", "--timeout", "5", "--retries", "0"]
    if local_only:
        # Every artifact is a local file, so no index is consulted; this is
        # also what makes furnishing possible inside a network-denied jail.
        argv += ["--no-index"]
    argv += ["-r", lock]
    try:
        done = _run(argv, cwd=os.path.realpath(claimdir),
                    timeout=FURNISH_TIMEOUT)
    except (OSError, subprocess.SubprocessError) as exc:
        shutil.rmtree(where, ignore_errors=True)
        return {"ok": False, "venv": None, "reason": f"pip: {exc}"}
    if done.returncode != 0:
        shutil.rmtree(where, ignore_errors=True)
        return {"ok": False, "venv": None,
                "reason": f"pip: {(done.stderr or done.stdout or '').strip()[-400:]}"}
    with open(stamp, "w", encoding="utf-8") as handle:
        handle.write(_now() + "\n")
    return {"ok": True, "venv": where, "reason": None}


# -- declared independence --------------------------------------------------


def independence(claimdir: str) -> dict:
    """What the redo's ledger DECLARES about who produced it.

    Declared, never assumed: content cannot prove blindness, so this is
    recorded as a declaration and reported as one.
    """
    out = {"vendor": None, "model": None, "blind": False}
    for event in ledger_events(claimdir):
        if event.get("event") not in ("producer", "oracle"):
            continue
        if event.get("vendor") or event.get("model"):
            out = {"vendor": event.get("vendor"), "model": event.get("model"),
                   "blind": bool(event.get("blind"))}
    return out


def _independence_line(declared: dict) -> str:
    """The sentence a crosscheck reports — a declaration, never proof."""
    if not declared or not (declared.get("vendor") or declared.get("model")):
        return ("unestablished: the redo's ledger names no producer, so "
                "content-independence cannot be read from it")
    vendor = declared.get("vendor") or "unknown"
    model = declared.get("model") or "unknown"
    room = "blind workspace" if declared.get("blind") else "workspace not blind"
    return (f"declared: {vendor}/{model}, {room} — declared by the producer, "
            f"not proven (content cannot prove blindness)")
