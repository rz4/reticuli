"""The kernel's run layer: confined, timed, scrubbed gate execution, furnishing, and the cost ledger."""
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import time

from .core import (
    _ENV_CACHE,
    _ENV_TIMEOUT,
    _JAILED,
    _KEEP_ENV,
    _SHELL,
    COST_UNITS,
    FURNISH_TIMEOUT,
    GATE_TIMEOUT,
    LEDGER,
    STORE,
    ClaimError,
    _hash_file,
    _judging_host,
    _safe,
)
from .identity import (  # noqa: F401
    root,
)
from .recipe import (  # noqa: F401
    gates,
)
from .seal import (  # noqa: F401
    seal,
)

# ----------------------------------------------------------- the environment

def preflight(recipe) -> list:
    """What this host lacks of everything the claim declared it `requires`.

    A missing requirement is an ENVIRONMENT failure, never a verdict: the gate
    was not run, so nothing was proven and nothing was disproven.
    """
    claim = (recipe or {}).get("claim") or {}
    required = claim.get("requires") or []
    if isinstance(required, str):
        required = [required]
    if not isinstance(required, list):
        raise ClaimError("[claim] requires must be a list of tools")
    missing = []
    for want in required:
        if not isinstance(want, str) or not want.strip():
            missing.append(str(want))
            continue
        if not _have(want.strip()):
            missing.append(want)
    return missing


_REQ_OPS = ("<=", ">=", "==", "!=", "~=", "<", ">")


def _have(requirement: str) -> bool:
    name, op, want = requirement, None, None
    for candidate in _REQ_OPS:
        at = requirement.find(candidate)
        if at > 0:
            name = requirement[:at].strip()
            op = candidate
            want = requirement[at + len(candidate):].strip()
            break
    if not name:
        return False
    if name in ("python", "python3", "cpython"):
        have = ".".join(str(part) for part in sys.version_info[:3])
    else:
        if shutil.which(name) is None:
            return False
        if op is None:
            return True
        have = _tool_version(name)
        if have is None:
            return True               # present but unparseable: not "missing"
    if op is None:
        return True
    return _version_ok(have, op, want)


def _tool_version(name: str):
    try:
        proc = subprocess.run([name, "--version"], capture_output=True,
                              timeout=20, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    text = (proc.stdout or b"").decode("utf-8", "replace") + \
           (proc.stderr or b"").decode("utf-8", "replace")
    found = re.search(r"\d+(?:\.\d+)*", text)
    return found.group(0) if found else None


def _version_tuple(text: str) -> tuple:
    return tuple(int(part) for part in re.findall(r"\d+", text or "")[:4]) or (0,)


def _version_ok(have: str, op: str, want: str) -> bool:
    a, b = _version_tuple(have), _version_tuple(want)
    width = max(len(a), len(b))
    a = a + (0,) * (width - len(a))
    b = b + (0,) * (width - len(b))
    if op == ">=":
        return a >= b
    if op == ">":
        return a > b
    if op == "<=":
        return a <= b
    if op == "<":
        return a < b
    if op == "!=":
        return a != b
    return a == b                      # "==" and "~=" both mean "this version"


# ---------------------------------------------------------- the sandbox

_BWRAP_OK = None


def _bwrap_usable() -> bool:
    global _BWRAP_OK
    if _BWRAP_OK is None:
        if not shutil.which("bwrap"):
            _BWRAP_OK = False
        else:
            try:
                probe = subprocess.run(
                    ["bwrap", "--ro-bind", "/", "/", "--unshare-net", "true"],
                    capture_output=True, check=False, timeout=30)
                _BWRAP_OK = probe.returncode == 0
            except (OSError, subprocess.SubprocessError):
                _BWRAP_OK = False
    return _BWRAP_OK


def sandbox_backend() -> str:
    """Which jail a gate will be judged in, here, now.

    Sandboxes do not nest: inside one already (RETICULI_JAILED), the honest
    answer is `inherited` -- run the gate unwrapped and say so.  Re-applying a
    sandbox inside a sandbox refuses, which would turn every verdict into a
    platform artefact.
    """
    if os.environ.get(_JAILED):
        return "inherited"
    if sys.platform == "darwin" and shutil.which("sandbox-exec"):
        return "seatbelt"
    if _bwrap_usable():
        return "bubblewrap"
    return "none"


def _env_cache_dir() -> str:
    """Where furnished environments live -- readable even under strict."""
    return os.environ.get(_ENV_CACHE) or os.path.join(
        os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"),
        "reticuli", "envs")


def _quote_sb(path: str) -> str:
    return path.replace("\\", "\\\\").replace('"', '\\"')


def _sandbox_argv(command: str, workdir: str, strict: bool = False):
    """The jail's argv.  STRICT additionally masks the user's own files.

    The standard tier confines writes to the workspace and denies the
    network; reads stay open, because the interpreter, its libraries, and
    the system all live outside the workspace.  Strict keeps that and masks
    the HOME GROUND -- the user's files, which is where the ssh keys and the
    documents are -- allowing back only the workspace and the
    furnished-environment cache.  System paths stay readable: that is what
    keeps strict robust enough to be on by default for received claims, and
    the threat model says so rather than implying more.
    """
    backend = sandbox_backend()
    inner = [_SHELL, "-c", command]
    work = os.path.realpath(workdir)
    if backend == "seatbelt":
        profile = ('(version 1)(allow default)(deny network*)(deny file-write*)'
                   f'(allow file-write* (subpath "{_quote_sb(work)}") (subpath "/dev"))')
        if strict:
            cache = os.path.realpath(_env_cache_dir())
            profile += ('(deny file-read* (subpath "/Users") (subpath "/Volumes"))'
                        f'(allow file-read* (subpath "{_quote_sb(work)}")'
                        f' (subpath "{_quote_sb(cache)}"))')
        return ["sandbox-exec", "-p", profile] + inner, backend
    if backend == "bubblewrap":
        argv = ["bwrap", "--ro-bind", "/", "/", "--dev-bind", "/dev", "/dev",
                "--proc", "/proc"]
        if strict:
            # Mask the home ground with empty filesystems, then re-bind the
            # one thing a gate legitimately needs from it: the furnished
            # cache. The workspace bind below re-opens the room itself.
            cache = os.path.realpath(_env_cache_dir())
            argv += ["--tmpfs", "/home", "--tmpfs", "/root"]
            if os.path.isdir(cache):
                argv += ["--ro-bind", cache, cache]
        argv += ["--bind", work, work, "--unshare-net",
                 "--die-with-parent", "--chdir", work]
        return argv + inner, backend
    return inner, backend


def _scrub_env(extra=None) -> dict:
    """The environment a gate may see: an allowlist, nothing inherited."""
    env = {}
    for name in _KEEP_ENV:
        value = os.environ.get(name)
        if value:
            env[name] = value
    env.setdefault("PATH", os.defpath)
    if extra:
        env.update({k: str(v) for k, v in extra.items() if v is not None})
    return env


def _kill_tree(proc) -> None:
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (OSError, AttributeError):
        try:
            proc.kill()
        except OSError:
            pass


def _run(argv, cwd=None, env=None, timeout=None, fsize=None) -> dict:
    """Run to completion or kill the whole process group at the ceiling.

    The group matters: `sh -c "sleep 30 && ..."` forks, so killing the shell
    alone leaves the child holding the pipes and the verifier hangs anyway.
    `fsize` caps how large any single file the process writes may grow --
    disk-fill protection for strictly jailed gates.
    """
    preexec = None
    if fsize:
        import resource

        def preexec():
            resource.setrlimit(resource.RLIMIT_FSIZE, (int(fsize), int(fsize)))
    started = time.monotonic()
    try:
        proc = subprocess.Popen(argv, cwd=cwd, env=env,
                                stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                start_new_session=True,
                                # the kernel is single-threaded, and rlimits
                                # have no other pre-exec mechanism
                                preexec_fn=preexec)  # noqa: PLW1509
    except OSError as exc:
        raise ClaimError(f"cannot execute {argv[0]!r}: {exc}") from None
    timed_out = False
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_tree(proc)
        try:
            out, err = proc.communicate(timeout=10)
        except (subprocess.TimeoutExpired, OSError, ValueError):
            out, err = b"", b""
    elapsed = time.monotonic() - started
    code = proc.returncode
    return {
        "status": "timeout" if timed_out else ("ok" if code == 0 else "failed"),
        "returncode": code,
        "seconds": elapsed,
        "stdout": (out or b"").decode("utf-8", "replace"),
        "stderr": (err or b"").decode("utf-8", "replace"),
        "timed_out": timed_out,
    }


def sandbox(command: str, workdir: str, timeout=None, env=None, strict=False):
    """Run `command` in `workdir` under whatever jail this host has.

    Returns (result, backend).  The backend is reported even when it is
    "none" -- the ledger tells the truth about the sandbox either way.
    `strict` masks the user's files too (see _sandbox_argv) and caps file
    growth; the backend NAME is unchanged, because strictness is the
    caller's policy while the backend is the host's fact.
    """
    argv, backend = _sandbox_argv(command, workdir, strict=strict)
    env = _scrub_env() if env is None else env
    if backend in ("seatbelt", "bubblewrap"):
        # SAY that a sandbox was applied. "Sandboxes do not nest" is only half a
        # contract if the wrapper never tells the wrapped process it is inside
        # one: a gate that itself runs claims would re-apply the sandbox and die
        # ("sandbox_apply: Operation not permitted"). Setting the signal here is
        # what lets a nested kernel inherit instead of nesting -- the same thing
        # this kernel's own check does when it re-execs itself.
        env = {**env, _JAILED: backend}
        # A REAL sandbox permits writes only inside the claim, but TMPDIR and
        # HOME are inherited from the host and point outside it -- so anything
        # the gate does with tempfile, or any tool that wants a home, is denied.
        # Hand the gate a scratch directory it can actually write. It lives in
        # the store, so it is residue: outside the root, and never a declared
        # file.
        scratch = os.path.join(os.path.realpath(workdir), STORE, "tmp")
        try:
            os.makedirs(scratch, exist_ok=True)
            env = {**env, "TMPDIR": scratch, "HOME": scratch}
        except OSError:
            pass                        # unwritable claim: let the gate report it
    fsize = None
    if strict:
        try:
            fsize = int(os.environ.get("RETICULI_STRICT_FSIZE")
                        or 512 * 1024 * 1024)
        except ValueError:
            fsize = 512 * 1024 * 1024
    result = _run(argv, cwd=workdir, env=env, timeout=timeout, fsize=fsize)
    result["quarantine"] = backend
    return result, backend


def gate_timeout(recipe=None, override=None) -> float:
    """A gate's wall-clock ceiling: declarable, capped by the environment."""
    claim = (recipe or {}).get("claim") or {}
    declared = override if override is not None else claim.get("gate_timeout")
    try:
        limit = float(declared) if declared is not None else GATE_TIMEOUT
    except (TypeError, ValueError):
        limit = GATE_TIMEOUT
    cap = os.environ.get(_ENV_TIMEOUT)
    if cap:
        try:
            limit = min(limit, float(cap))
        except (TypeError, ValueError):
            pass
    return max(limit, 0.001)


def run_gate(command: str, claimdir: str, recipe=None, timeout=None,
             extra_path=None, strict=False) -> dict:
    """THE GATE ENTRY POINT.  Everywhere a gate runs, it runs through here.

    Scrubbed environment (a hostile gate must not read an inherited secret and
    seal it into a verdict), a wall-clock ceiling (it must not hang the
    verifier), and the platform sandbox (it is not your shell).  `extra_path`
    prepends a directory to the scrubbed PATH -- how a furnished environment's
    interpreter reaches the gate without anything else leaking in.
    """
    _judging_host()
    if not isinstance(command, str) or not command.strip():
        raise ClaimError("a gate needs a run command")
    limit = gate_timeout(recipe, timeout)
    env = _scrub_env()
    if extra_path:
        env["PATH"] = extra_path + os.pathsep + env["PATH"]
    result, backend = sandbox(command, claimdir, timeout=limit, env=env,
                              strict=strict)
    result["quarantine"] = backend
    result["command"] = command
    result["timeout"] = limit
    return result


# ------------------------------------------------------- the environment (2)

def furnish(recipe, workdir: str):
    """Build the claim's declared environment in a room, or say why not.

    A recipe may declare `[claim] environment = "<file>"`: a standard
    hash-pinned requirements file, pinned into the root, because dependency
    versions decide what "passes" means.  Furnishing happens BETWEEN
    materializing a room and judging in it: a private venv is built from
    exactly the named artifacts -- hashes required, wheels only, so nothing
    executes at install time and nothing unnamed can arrive -- and the gate
    then runs with that venv first on its PATH, network denied as always.

    Returns the venv's bin directory, or None when no environment is
    declared.  A failure to furnish raises in band and is an ENVIRONMENT
    failure for the caller: the room could not be prepared, so nothing was
    proven and nothing was disproven.

    Environments are cached on the host, keyed by the environment file's
    digest plus the interpreter and platform -- mutation testing audits the
    same claim dozens of times, and the room's furniture does not change.
    The cache is residue: it never touches identity.
    """
    claim = (recipe or {}).get("claim") or {}
    env_name = claim.get("environment")
    if not env_name:
        return None
    env_path = _safe(workdir, env_name)
    digest = _hash_file(env_path)
    base = os.environ.get(_ENV_CACHE) or os.path.join(
        os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"),
        "reticuli", "envs")
    tag = (f"{digest[:16]}-py{sys.version_info[0]}.{sys.version_info[1]}"
           f"-{sys.platform}-{platform.machine()}")
    venv_dir = os.path.join(base, tag)
    bin_dir = os.path.join(venv_dir, "bin")
    marker = os.path.join(venv_dir, ".furnished")
    if os.path.isfile(marker):
        return bin_dir

    os.makedirs(base, exist_ok=True)
    shutil.rmtree(venv_dir, ignore_errors=True)   # a half-built room is razed
    made = _run([sys.executable, "-m", "venv", venv_dir],
                timeout=FURNISH_TIMEOUT)
    if made["status"] != "ok":
        shutil.rmtree(venv_dir, ignore_errors=True)
        raise ClaimError("environment: could not create a venv for "
                         f"{env_name}: {(made['stderr'] or made['stdout'])[-300:]}")
    # Hashes REQUIRED: only the exact artifacts the claim names can arrive.
    # Wheels ONLY: installing a wheel unpacks files and executes nothing, so
    # a hostile package's code runs no earlier than the gate, inside the
    # sandbox, which is trust the gate already had.
    installed = _run([os.path.join(bin_dir, "python3"), "-m", "pip",
                      "install", "--quiet", "--no-input", "--require-hashes",
                      "--only-binary=:all:", "-r", env_path],
                     cwd=os.path.dirname(env_path), timeout=FURNISH_TIMEOUT)
    if installed["status"] != "ok":
        shutil.rmtree(venv_dir, ignore_errors=True)
        raise ClaimError(
            f"environment: could not furnish {env_name}: "
            f"{(installed['stderr'] or installed['stdout'])[-400:]}")
    with open(marker, "w", encoding="utf-8") as f:
        f.write(digest + "\n")
    return bin_dir


# ----------------------------------------------------------------- the ledger

def _ledger_path(claimdir: str) -> str:
    return os.path.join(claimdir, LEDGER)


def ledger(claimdir: str, event: dict) -> None:
    """Append one line of residue.  Residue lives outside the root."""
    path = _ledger_path(claimdir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, sort_keys=True) + "\n")


def ledger_events(claimdir: str):
    """Every well-formed event on the ledger, or None if there is no ledger."""
    path = _ledger_path(claimdir)
    if not os.path.isfile(path):
        return None
    events = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except ValueError:
                    continue               # a damaged line is not an event
                if isinstance(event, dict):
                    events.append(event)
    except OSError:
        return None
    return events


def cost(claimdir: str):
    """What the redo cost, totalled from its ledger -- or None if unmeasured.

    Totals start at zero and carry only the keys the ledger actually names: an
    unmeasured machine is reported, never guessed at.

    An event stamped with a `scope` is TESTIMONY OF A DIFFERENT KIND -- the
    authoring session's discovery bill, deliberately larger than a targeted
    redo -- so it never enters the unit totals the cost band compares. It is
    aggregated under `discovery` instead: reported beside the band, priced
    against nothing. Feeding it to the band once rejected a valid proof for
    exhibiting exactly the gap the measurement exists to show.
    """
    events = ledger_events(claimdir)
    if events is None:
        return None
    totals = {}
    discovery = {}
    for event in events:
        bucket = discovery if event.get("scope") else totals
        for key in COST_UNITS:
            value = event.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            bucket[key] = bucket.get(key, 0) + value
    if discovery:
        totals["discovery"] = discovery
    return totals or None


def _in_band(a, b, tolerance: float) -> bool:
    """Comparability is a BAND, [1/tol, tol] -- not equality."""
    if a == 0 and b == 0:
        return True
    if a == 0 or b == 0:
        return False
    ratio = float(a) / float(b)
    return (1.0 / tolerance) <= ratio <= tolerance


def independence(claimdir: str) -> dict:
    """What the redo DECLARED about who produced it.  A declaration, not proof."""
    declaration = {"vendor": None, "model": None, "blind": None, "declared": False}
    for event in ledger_events(claimdir) or []:
        if event.get("event") == "producer":
            declaration = {
                "vendor": event.get("vendor"),
                "model": event.get("model"),
                "blind": event.get("blind"),
                "declared": True,
            }
    return declaration


def _independence_line(decl) -> str:
    vendor, model = decl.get("vendor"), decl.get("model")
    if not (isinstance(vendor, str) and vendor and isinstance(model, str) and model):
        return ("unestablished: content-independence cannot be established "
                "from content alone")
    blind = "blind workspace" if decl.get("blind") else "workspace not blind"
    return (f"declared: {vendor}/{model}, {blind} "
            f"(a declaration on the redo's ledger, not proven)")
