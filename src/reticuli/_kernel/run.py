"""The kernel's run layer: confined, timed, scrubbed gate execution, furnishing, and the cost ledger."""
import json
import math
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
_BWRAP_HARD = None
_SEATBELT_OK = None

#: Namespace flags that cost nothing where they work and must never be
#: ASSUMED where they do not.  `--unshare-pid` is the load-bearing one: the
#: jail mounts a procfs, and without its own pid namespace that procfs is the
#: HOST's -- so a gate can read /proc/<pid>/environ of any process with the
#: same uid, including the parent `ret` that is holding a vendor API key for
#: the duration of a rebuild.  The environment scrub (_scrub_env) keeps
#: inherited secrets out of the gate's own variables; without this flag they
#: walk back in through the filesystem, which makes the scrub decorative on
#: Linux.  `--new-session` denies TIOCSTI terminal injection (bwrap's own
#: documented recommendation, and safe here because every gate is spawned
#: with stdin on /dev/null and its output on pipes); `--unshare-ipc` closes
#: the System V / POSIX IPC side channel.
_BWRAP_HARDENING = ("--unshare-pid", "--unshare-ipc", "--new-session")


def _bwrap_probe(extra: tuple = ()) -> bool:
    """Does bwrap actually work on this host with these flags?

    Presence on PATH is not usability: user namespaces are routinely denied
    (unprivileged userns off, nested containers, hardened kernels), and a
    sandbox that is present but non-functional counts as NONE, honestly
    reported, rather than as a jail that silently is not one.

    The probe mirrors the argv it certifies, `--dev-bind` included, so it
    cannot pass on a flag set the real jail does not use.
    """
    try:
        probe = subprocess.run(
            ["bwrap", "--ro-bind", "/", "/", "--dev-bind", "/dev", "/dev",
             "--proc", "/proc", "--unshare-net", *extra, "true"],
            capture_output=True, check=False, timeout=30)
        return probe.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _seatbelt_usable() -> bool:
    """Does seatbelt actually APPLY here, or is it only installed?

    The same rule bwrap has always been held to, and seatbelt was not: a
    present-but-non-functional sandbox counts as none, honestly reported.
    `sandbox_apply` is refused inside an existing seatbelt jail, so on a host
    where some outer confinement is already in force -- a CI runner, another
    tool's sandbox, an operator's own wrapper -- `shutil.which` says yes and
    every gate then dies with `sandbox_apply: Operation not permitted` and
    exit 71. `RETICULI_JAILED` covers the nesting this tool creates itself;
    nothing told us about nesting we did not create. This probe does.

    Measured 2026-10-29: `sandbox-exec -p '(allow default)' python3 -m
    reticuli.launcher run <claim>` exited 71 with the backend reported as
    `seatbelt`, because the launcher's own probe had just been consolidated
    away into `sandbox_backend()`, which had never had one.
    """
    global _SEATBELT_OK
    if _SEATBELT_OK is None:
        if not shutil.which("sandbox-exec"):
            _SEATBELT_OK = False
        else:
            try:
                probe = subprocess.run(
                    ["sandbox-exec", "-p", "(version 1)(allow default)",
                     "/usr/bin/true"],
                    capture_output=True, check=False, timeout=30)
                _SEATBELT_OK = probe.returncode == 0
            except (OSError, subprocess.SubprocessError):
                _SEATBELT_OK = False
    return _SEATBELT_OK


def _bwrap_usable() -> bool:
    global _BWRAP_OK
    if _BWRAP_OK is None:
        _BWRAP_OK = bool(shutil.which("bwrap")) and _bwrap_probe()
    return _BWRAP_OK


def _bwrap_hardening() -> tuple:
    """The hardening flags this host will actually accept, probed not assumed.

    Probed as a unit: if the hardened jail runs, use it; if it does not, fall
    back to the basic one rather than failing a legitimate gate with a
    confusing bwrap error.  The fallback is a weaker jail and the degradation
    is silent in the argv, which is why `sandbox_hardened()` exists for a
    caller (the ledger, a report) that wants to say which tier applied.
    """
    global _BWRAP_HARD
    if _BWRAP_HARD is None:
        _BWRAP_HARD = (_BWRAP_HARDENING
                       if _bwrap_probe(_BWRAP_HARDENING) else ())
    return _BWRAP_HARD


def sandbox_hardened() -> bool:
    """Whether this host's jail closes the /proc and IPC side channels.

    False on seatbelt (which has no namespaces and does not need them -- its
    profile governs reads directly) and on a bwrap host that refuses the
    hardening probe.  Reported rather than assumed, the same way the backend
    name is.
    """
    return sandbox_backend() == "bubblewrap" and bool(_bwrap_hardening())


#: Directories that are the HOST, not a user's files.  Masking one denies the
#: interpreter, the shell, or the system databases a legitimate gate reads,
#: so a derived mask that lands on one is refused and narrowed.
_SYSTEM_DIRS = frozenset((
    "/", "/usr", "/usr/local", "/usr/bin", "/usr/lib", "/usr/share",
    "/opt", "/var", "/private", "/private/var", "/private/tmp", "/tmp",
    "/etc", "/bin", "/sbin", "/lib", "/lib64", "/System", "/Library",
    "/Applications", "/dev", "/proc", "/sys", "/run", "/nix", "/snap",
))


def _within(path: str, parent: str) -> bool:
    """Is `path` inside `parent` (or equal to it)?"""
    if not path or not parent:
        return False
    if parent == os.sep:
        return True
    return path == parent or path.startswith(parent.rstrip(os.sep) + os.sep)


def _maskable(candidate: str) -> bool:
    """May STRICT mask this directory, or is it load-bearing for the host?

    A mask is only correct if it hides user files and nothing the host needs.
    Three ways a derived candidate fails that, all measured 2026-10-29:
    `HOME=/var/root` (root on macOS) derives `/private/var`, which denies
    `/private/var/select/sh` on every gate and injects a foreign error into
    every verdict; `HOME=/opt/app` derives `/opt`, which under bubblewrap
    tmpfs-hides `/opt/homebrew/bin/python3`; `HOME=/usr/local/myhome`
    derives `/usr/local` with the same effect.  A candidate that is a system
    directory, or that contains this interpreter or this shell, is refused.
    """
    if not candidate or candidate == os.sep:
        return False
    if os.path.normpath(candidate) in _SYSTEM_DIRS:
        return False
    for tool in (sys.executable, _SHELL):
        try:
            resolved = os.path.realpath(tool) if tool else ""
        except (OSError, ValueError):
            resolved = tool or ""
        if resolved and _within(resolved, candidate):
            return False
    return True


def _home_ground() -> list[str]:
    """The directories STRICT masks: wherever this host keeps users' files.

    Derived, never hardcoded.  A literal `/home` + `/root` mask is correct on
    a stock distribution and masks NOTHING on the layouts this tool is most
    likely to be audited on -- `/data/home/...` on a cluster, an NFS or
    autofs mount, `/Users` on macOS, a relocated $HOME anywhere.  Strict that
    silently protects nothing is worse than strict that is absent, because
    the report says `strict` either way.

    The PARENT of the home directory is preferred, so one user's jail cannot
    read another's.  Where that parent is the host rather than a place users
    live -- `/` for `/root`, `/private/var` for macOS's `/var/root`, `/opt`
    for a containerised `/opt/app` -- the parent is refused and the home
    directory itself is masked instead.  If even that is load-bearing,
    nothing is derived and only the conventional locations are masked: a
    narrower mask is a weaker promise, never a broken host.
    """
    ground: dict[str, None] = {}
    for base in ("/home", "/root", "/Users"):
        if os.path.isdir(base) and _maskable(base):
            ground.setdefault(base, None)
    try:
        home = os.path.realpath(os.path.expanduser("~"))
    except (OSError, RuntimeError):
        home = ""
    if home and home != os.sep:
        parent = os.path.dirname(home)
        for candidate in (parent, home):
            if _maskable(candidate):
                ground.setdefault(candidate, None)
                break
    return list(ground)


def sandbox_backend() -> str:
    """Which jail a gate will be judged in, here, now.

    Sandboxes do not nest: inside one already (RETICULI_JAILED), the honest
    answer is `inherited` -- run the gate unwrapped and say so.  Re-applying a
    sandbox inside a sandbox refuses, which would turn every verdict into a
    platform artefact.
    """
    if os.environ.get(_JAILED):
        return "inherited"
    if sys.platform == "darwin" and _seatbelt_usable():
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


def _ancestors(*paths: str) -> list[str]:
    """Every proper ancestor of the given paths, deduplicated, order kept."""
    seen: dict[str, None] = {}
    for p in paths:
        d = os.path.dirname(p)
        while len(d) > 1:
            seen.setdefault(d, None)
            d = os.path.dirname(d)
    return list(seen)


def sandbox_wrap(workdir: str, strict: bool = False,
                 system_tmp: bool = False):
    """THE JAIL, as a command prefix: `(backend, argv_prefix)`.

    ONE POLICY, TWO CALLERS.  `_sandbox_argv` appends `sh -c <gate>` to this
    prefix to judge a gate; the launcher appends a claim's entrypoint argv to
    execute one.

    `system_tmp` is the one place those two callers legitimately differ, and
    collapsing it was a defect.  A GATE must not need scratch space outside
    the claim -- `spec/claim-format.md` says so, and the witness is a gate
    piping into `diff -u expected -` that passed on every host without a
    working sandbox and failed on every host with one, because BSD `diff`
    spools non-seekable stdin to the system temp dir.  For a gate that is a
    defect to surface, so the default is False.  An ENTRYPOINT is a program,
    not a criterion: it may legitimately shell out to BSD tools, and those
    read `confstr(_CS_DARWIN_USER_TEMP_DIR)` rather than `TMPDIR`, so
    redirecting the environment does not reach them.  The launcher passes
    True and keeps the write-allow it has always had.  Before 2026-10-29 the launcher carried its own second copy
    of the profile, and a copy is a thing that drifts -- that one had, in
    four ways: it interpolated the claim path into a seatbelt profile with no
    escaping (a directory containing a quote or a backslash corrupted or
    escaped the profile, where this module has had `_quote_sb` all along), it
    passed `abspath` where seatbelt matches RESOLVED paths, so a claim
    reached through a symlink got a write-allow that never matched; its bwrap
    arm omitted `--dev-bind /dev` and `--proc /proc`; and it announced
    `RETICULI_JAILED=1` where this kernel's own criteria pin the value as the
    backend NAME, not a flag.  None of those were reachable from the gate
    path, which is why they survived: the second copy was never the one the
    criteria judged.

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
    work = os.path.realpath(workdir)
    if backend == "seatbelt":
        profile = ('(version 1)(allow default)(deny network*)(deny file-write*)'
                   f'(allow file-write* (subpath "{_quote_sb(work)}") (subpath "/dev"))')
        if system_tmp:
            profile += ('(allow file-write* (subpath "/private/tmp")'
                        ' (subpath "/private/var/folders"))')
        if strict:
            cache = os.path.realpath(_env_cache_dir())
            masked = "".join(f'(subpath "{_quote_sb(p)}")'
                             for p in [*_home_ground(), "/Volumes"])
            profile += (f'(deny file-read* {masked})'
                        f'(allow file-read* (subpath "{_quote_sb(work)}")'
                        f' (subpath "{_quote_sb(cache)}"))')
            # A subpath allow does not open the road TO the subtree:
            # realpath(3) stats every ancestor as its own lookup -- CPython's
            # launcher does exactly that to a furnished venv's python -- and
            # each stat is denied by the /Users mask above. Metadata on the
            # ancestor chain leaks that the directories exist, nothing more.
            profile += "".join(
                f'(allow file-read-metadata (literal "{_quote_sb(a)}"))'
                for a in _ancestors(work, cache))
        return backend, ["sandbox-exec", "-p", profile]
    if backend == "bubblewrap":
        argv = ["bwrap", "--ro-bind", "/", "/", "--dev-bind", "/dev", "/dev",
                "--proc", "/proc", *_bwrap_hardening()]
        if strict:
            # Mask the home ground with empty filesystems, then re-bind the
            # one thing a gate legitimately needs from it: the furnished
            # cache. The workspace bind below re-opens the room itself.
            cache = os.path.realpath(_env_cache_dir())
            for ground in _home_ground():
                argv += ["--tmpfs", ground]
            if os.path.isdir(cache):
                argv += ["--ro-bind", cache, cache]
        argv += ["--bind", work, work, "--unshare-net",
                 "--die-with-parent", "--chdir", work]
        return backend, argv
    return backend, []


def _sandbox_argv(command: str, workdir: str, strict: bool = False):
    """The jail's argv for one GATE: the prefix, then the shell command."""
    backend, prefix = sandbox_wrap(workdir, strict=strict)
    return prefix + [_SHELL, "-c", command], backend


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
            # Finite, for the reader's reason (spec/record.md): a cost is a
            # measurement of work, and NaN reports none while an infinity
            # swallows every other measurement in the sum. Letting one into a
            # total would also make the total unreadable as a record, since
            # the reader now refuses exactly these.
            #
            # NON-NEGATIVE for the same reason, and the two readers of this
            # one quantity disagreed about it until 2026-10-29: the record
            # reader has always required `value >= 0` (attest.record_validate)
            # while this totaller accepted a negative, so a ledger carrying
            # `{"usd": -5}` produced a total no record could ever hold -- and
            # that total went on to decide a cost band and an envelope. A
            # negative cost is not a cheap run; it is a broken instrument,
            # and the envelope it flatters is the one measurement an operator
            # is asked to trust. Skipped like any other unreadable value, so
            # an unmeasured machine stays reported rather than guessed at.
            if isinstance(value, bool) or not isinstance(value, (int, float)) \
                    or not math.isfinite(value) or value < 0:
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
    """What the redo DECLARED about who produced it.  A declaration, not proof.

    `model_source` carries how the model became known -- `observed` (the
    producer reported what it actually ran), `declared` (the caller named one
    in the environment), or `unrecorded`.  Both are declarations as far as
    this layer is concerned; the distinction matters because only the first
    survives a producer that picks its own default.
    """
    declaration = {"vendor": None, "model": None, "blind": None,
                   "model_source": "unrecorded", "declared": False}
    for event in ledger_events(claimdir) or []:
        if event.get("event") == "producer":
            declaration = {
                "vendor": event.get("vendor"),
                "model": event.get("model"),
                "blind": event.get("blind"),
                "model_source": event.get("model_source") or (
                    "declared" if event.get("model") else "unrecorded"),
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
