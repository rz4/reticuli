"""Gate execution: the confined run contract and the cost ledger
(spec/claim-format.md: "Gate execution contract").

`run_gate` runs one gate command under a platform sandbox -- macOS
`sandbox-exec` or Linux `bwrap`, each probed functionally rather than
merely by presence -- with a scrubbed environment and a wall-clock bound.
`ledger` / `ledger_events` / `cost` record and total what a rebuild's
production cost. `gate_timeout` resolves the declared wall-clock ceiling;
a claim's own declaration is the ceiling in both directions, never
undercut by an implementation default. `preflight` checks the claim's
`requires` contract against the host, and `furnish` builds the private,
hash-pinned venv `[claim] environment` describes. Stdlib only.
"""
import json
import operator
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import tempfile

from reticuli._kernel import core

# -- version-requirement parsing, shared by preflight -----------------------
_REQ_OPS = ('<=', '>=', '==', '!=', '~=', '<', '>')
_REQ_RE = re.compile(
    r'^\s*([^\s<>=!~]+)\s*(' + '|'.join(re.escape(o) for o in _REQ_OPS) + r')?\s*(.*?)\s*$'
)
_VER_RE = re.compile(r'\d+(?:\.\d+)*')
_OPS_FN = {
    '<=': operator.le, '>=': operator.ge, '==': operator.eq,
    '!=': operator.ne, '<': operator.lt, '>': operator.gt,
}

# -- functional sandbox probes are cached: a host's sandbox either works
# or does not, for the life of this process. --------------------------------
_BWRAP_OK = None
_SEATBELT_OK = None


def _have(binary: str) -> bool:
    """Whether `binary` resolves on the current PATH."""
    return shutil.which(binary) is not None


def _in_band(fn, *args, **kwargs):
    """Run `fn`; an unexpected exception becomes a `ClaimError` so a
    refusal stays in band rather than surfacing as a raw traceback."""
    try:
        return fn(*args, **kwargs)
    except core.ClaimError:
        raise
    except Exception as e:
        raise core.ClaimError(str(e)) from e


def _version_tuple(s: str) -> tuple:
    """A dotted version string as a tuple of ints; non-numeric leaders
    stop the parse (`"1.2.3rc1"` -> `(1, 2, 3)`)."""
    m = _VER_RE.match(s.strip())
    if not m:
        return (0,)
    return tuple(int(p) for p in m.group(0).split('.'))


def _version_ok(have: tuple, op: str, need: tuple) -> bool:
    """Whether an installed version tuple satisfies `op need`."""
    if not have:
        return False
    n = max(len(have), len(need))
    h = have + (0,) * (n - len(have))
    v = need + (0,) * (n - len(need))
    if op == '~=':
        prefix = need[:-1] if len(need) > 1 else need
        return h[:len(prefix)] == (prefix + (0,) * (len(prefix) - len(need[:-1])))[:len(prefix)] and h >= v
    fn = _OPS_FN.get(op)
    return True if fn is None else fn(h, v)


def _tool_version(name: str):
    """A binary's own reported version, parsed from `name --version`;
    `None` when it cannot be determined."""
    try:
        out = subprocess.run([name, "--version"], capture_output=True,
                              timeout=5, text=True)
    except Exception:
        return None
    m = _VER_RE.search((out.stdout or "") + (out.stderr or ""))
    return _version_tuple(m.group(0)) if m else None


def preflight(recipe: dict) -> list:
    """Missing entries of `[claim] requires` -- binaries or Python
    modules the host lacks, or whose version fails a declared constraint
    (`spec/claim-format.md`: the environment contract)."""
    missing = []
    for req in (recipe or {}).get("claim", {}).get("requires", []) or []:
        m = _REQ_RE.match(req)
        if not m:
            missing.append(req)
            continue
        name, op, ver = m.group(1), m.group(2), m.group(3)
        have = _tool_version(name) if _have(name) else None
        if have is None and not _have(name):
            try:
                import importlib.metadata as _md
                have = _version_tuple(_md.version(name))
            except Exception:
                missing.append(req)
                continue
        if op and ver and not _version_ok(have or (), op, _version_tuple(ver)):
            missing.append(req)
    return missing


def _independence_line(producers) -> str:
    """A human-readable summary of what each producer declared."""
    descs = []
    for p in producers or []:
        if not p:
            descs.append("unknown")
            continue
        descs.append(f"{p.get('vendor', 'unknown')}/{p.get('model', 'unknown')}")
    return " vs ".join(descs) if descs else "no producers declared"


def independence(*producers) -> dict:
    """Whether declared `producer` blocks show genuinely distinct
    producers -- distinct (vendor, model) pairs -- for a crosscheck."""
    seen = [(p.get("vendor"), p.get("model")) for p in producers if p]
    return {"independent": len(seen) == len(set(seen)),
            "line": _independence_line(producers)}


def _env_cache_dir(d: str) -> str:
    """Where furnished venvs are cached: host residue, never identity."""
    override = os.environ.get(core._ENV_CACHE)
    if override:
        return override
    return os.path.expanduser("~/.cache/reticuli/envs")


def furnish(d: str, recipe: dict):
    """Build the private venv `[claim] environment` names, hash-pinned
    and binary-only (`spec/claim-format.md`). Returns the venv's `bin`
    directory, or `None` when the claim declares no environment."""
    env_file = (recipe or {}).get("claim", {}).get("environment")
    if env_file is None:
        return None
    path = core._safe(d, env_file)
    digest = core._hash_file(path)
    venv_dir = os.path.join(_env_cache_dir(d), digest,
                             sys.platform, platform.python_version())
    bin_dir = os.path.join(venv_dir, "bin")
    if not os.path.isdir(venv_dir):
        os.makedirs(os.path.dirname(venv_dir), exist_ok=True)
        _in_band(subprocess.run, [sys.executable, "-m", "venv", venv_dir],
                 check=True, timeout=core.FURNISH_TIMEOUT)
        _in_band(subprocess.run,
                 [os.path.join(bin_dir, "python3"), "-m", "pip", "install",
                  "--require-hashes", "--only-binary=:all:", "-r", path],
                 check=True, timeout=core.FURNISH_TIMEOUT)
    return bin_dir


# -- the sandbox: functional probes, never presence alone -------------------

def _bwrap_usable() -> bool:
    """Whether `bwrap` actually confines, probed functionally and cached."""
    global _BWRAP_OK
    if _BWRAP_OK is not None:
        return _BWRAP_OK
    if not _have("bwrap"):
        _BWRAP_OK = False
        return _BWRAP_OK
    try:
        proc = subprocess.run(
            ["bwrap", "--ro-bind", "/", "/", "--unshare-all",
             "--die-with-parent", "true"],
            capture_output=True, timeout=5,
        )
        _BWRAP_OK = proc.returncode == 0
    except Exception:
        _BWRAP_OK = False
    return _BWRAP_OK


def _seatbelt_usable() -> bool:
    """Whether `sandbox-exec` actually confines, probed functionally and cached."""
    global _SEATBELT_OK
    if _SEATBELT_OK is not None:
        return _SEATBELT_OK
    if sys.platform != "darwin" or not _have("sandbox-exec"):
        _SEATBELT_OK = False
        return _SEATBELT_OK
    try:
        proc = subprocess.run(
            ["sandbox-exec", "-p", "(version 1)(allow default)", "/usr/bin/true"],
            capture_output=True, timeout=5,
        )
        _SEATBELT_OK = proc.returncode == 0
    except Exception:
        _SEATBELT_OK = False
    return _SEATBELT_OK


def sandbox_backend() -> str:
    """Which confinement applies here: `inherited` when already jailed
    (`RETICULI_JAILED`), else the first functional probe to succeed,
    else `none`, honestly."""
    if os.environ.get(core._JAILED):
        return "inherited"
    if _seatbelt_usable():
        return "seatbelt"
    if _bwrap_usable():
        return "bubblewrap"
    return "none"


def sandbox() -> dict:
    """The functional sandbox probe (v1: `jail`)."""
    backend = sandbox_backend()
    return {"backend": backend, "functional": backend != "none"}


def _quote_sb(s: str) -> str:
    """Quote a string as an S-expression literal for a seatbelt profile."""
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'


def _seatbelt_profile(real_d: str) -> str:
    """A seatbelt profile that allows everything by default -- the gate
    floor (`/dev` sinks, subprocess spawn, host reads, uname, the
    opendirectoryd user lookup) needs no narrower allowlist -- and denies
    only what must stay denied where confinement applies: the network, and
    writes outside the claim's own directory."""
    return "\n".join([
        "(version 1)",
        "(allow default)",
        "(deny network*)",
        "(deny file-write*)",
        f"(allow file-write* (subpath {_quote_sb(real_d)}))",
        f"(allow file-write* (literal {_quote_sb('/dev/null')}))",
    ])


def _sandbox_argv(cmd: str, real_d: str, scratch, backend: str) -> list:
    """The argv that actually runs `cmd` under `backend`'s confinement."""
    if backend == "seatbelt":
        return ["sandbox-exec", "-p", _seatbelt_profile(real_d),
                core._SHELL, "-c", cmd]
    if backend == "bubblewrap":
        argv = ["bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc",
                "--unshare-net", "--die-with-parent", "--bind", real_d, real_d]
        if scratch and not (scratch == real_d or scratch.startswith(real_d + os.sep)):
            argv += ["--bind", scratch, scratch]
        argv += ["--chdir", real_d, core._SHELL, "-c", cmd]
        return argv
    return [core._SHELL, "-c", cmd]


def _scrub_env(backend: str) -> dict:
    """A minimal host allowlist (`spec/claim-format.md`): inherited
    secrets never reach a gate."""
    env = {k: os.environ[k] for k in core._KEEP_ENV if k in os.environ}
    if backend in ("seatbelt", "bubblewrap"):
        env[core._JAILED] = "1"
    return env


def _kill_tree(pid: int) -> None:
    """Kill a timed-out gate's whole process group, not just its leader."""
    try:
        pgid = os.getpgid(pid)
    except ProcessLookupError:
        return
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        pass


def _run(argv: list, cwd: str, env: dict, timeout: float) -> str:
    """Run `argv`, bounded by `timeout`; `ok` / `failed` / `timeout`."""
    try:
        proc = subprocess.Popen(argv, cwd=cwd, env=env,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 start_new_session=True)
    except OSError:
        return "failed"
    try:
        proc.communicate(timeout=timeout)
        return "ok" if proc.returncode == 0 else "failed"
    except subprocess.TimeoutExpired:
        _kill_tree(proc.pid)
        try:
            proc.communicate(timeout=5)
        except Exception:
            pass
        return "timeout"


def gate_timeout(recipe) -> float:
    """The effective wall-clock bound (`spec/claim-format.md`): a declared
    `gate_timeout` IS the ceiling, raising past the implementation default
    if it says so -- never undercut by one. A host ceiling
    (`RETICULI_GATE_TIMEOUT`), where set, still applies on top."""
    declared = (recipe or {}).get("claim", {}).get("gate_timeout")
    value = float(declared) if declared is not None else core.GATE_TIMEOUT
    cap = os.environ.get(core._ENV_TIMEOUT)
    if cap:
        try:
            value = min(value, float(cap))
        except ValueError:
            pass
    return value


def run_gate(cmd: str, d: str, recipe=None) -> dict:
    """Run one gate command the one way every verb runs it
    (`spec/claim-format.md`): scrubbed environment, sandboxed, bounded,
    with a scratch `TMPDIR`/`HOME` inside the claim's store wherever real
    confinement applies. Returns `{"status", "quarantine"}`."""
    backend = sandbox_backend()
    timeout = gate_timeout(recipe)
    real_d = os.path.realpath(d)
    env = _scrub_env(backend)
    scratch = None
    if backend in ("seatbelt", "bubblewrap"):
        store_dir = os.path.join(d, core.STORE)
        os.makedirs(store_dir, exist_ok=True)
        scratch = tempfile.mkdtemp(prefix="scratch-", dir=store_dir)
        env["TMPDIR"] = scratch
        env["HOME"] = scratch
    argv = _sandbox_argv(cmd, real_d, scratch, backend)
    status = _run(argv, d, env, timeout)
    return {"status": status, "quarantine": backend}


def _ledger_path(d: str) -> str:
    return os.path.join(d, core.LEDGER)


def ledger(d: str, entry: dict) -> dict:
    """Append one cost entry to `d`'s ledger, stamping `when` if absent."""
    path = _ledger_path(d)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    rec = dict(entry)
    rec.setdefault("when", core._now())
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, sort_keys=True))
        f.write("\n")
    return rec


def ledger_events(d: str) -> list:
    """Every ledger entry recorded for `d`, in append order."""
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
    """Ledger totals per unit (`spec/kernel-api.md`); `None` if nothing
    was measured. Totals carry only the keys the ledger actually names."""
    totals = {}
    for e in ledger_events(d):
        for k in core.COST_KEYS:
            v = e.get(k)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                totals[k] = totals.get(k, 0) + v
    return totals or None
