"""The launcher: run software that exists only latently in a claim
(`checks/launcher_check.py`, which is this module's definition).

A runnable claim is an ordinary claim whose pinned inputs include
`package.toml` (`[package] entrypoint = "..."`). `run` makes the claim
executable -- checking a standing build, landing a fresh rebuild and asking
for consent, or refusing a drifted one -- and `strip` deletes the generated
bytes back to latency. The claim, never the code, is the identity.

Stdlib only.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib

from reticuli import kernel, _util

LAUNCHER_DIR = ".launcher"
STATE_FILE = "state.json"
SCRATCH_DIR = "scratch"
PRODUCER_VAR = "RETICULI_PRODUCER"

HELP = """\
usage: python3 -m reticuli.launcher <verb> ...

verbs:
  run   <claim> [--accept-generated] [--signed-only] [--no-sandbox] [-- args...]
  strip <claim>
  ls    <claim>...
"""


def eprint(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# -- Recipe-derived helpers (no kernel private touched; `doc` is the
# already-parsed, already-validated recipe `kernel.load_recipe` returned) --


def _generated_outputs(doc: dict) -> list:
    out = []
    for step in doc.get("step", []):
        if step.get("kind") != "produce":
            continue
        cls = step.get("class", "generated")
        if cls in ("generated", "free"):
            out.append(step["output"])
    return out


def _package_entrypoint(d: str, doc: dict) -> str:
    """Validate the package contract and return the entrypoint's safe,
    resolved path inside `d` -- or raise `kernel.ClaimError` naming why the
    claim is not runnable.
    """
    name = "package.toml"
    claim = doc.get("claim", {})
    declared_inputs = claim.get("inputs", [])

    is_generated = any(
        step.get("kind") == "produce" and step.get("output") == name
        for step in doc.get("step", [])
    )
    if is_generated:
        raise kernel.ClaimError(
            "package.toml is a generated output; it must be a pinned input")
    if name not in declared_inputs:
        raise kernel.ClaimError(
            "no package.toml pinned as an input -- claim is not runnable")

    path = _util.safe_path(d, name)
    if not os.path.isfile(path):
        raise kernel.ClaimError(f"pinned package.toml is missing: {path!r}")

    try:
        with open(path, "rb") as f:
            pkg_doc = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise kernel.ClaimError(f"malformed package.toml: {e}") from e

    entry = (pkg_doc.get("package") or {}).get("entrypoint")
    if not isinstance(entry, str) or not entry:
        raise kernel.ClaimError(
            "package.toml [package] entrypoint is required and must be a string")
    return _util.safe_path(d, entry)


def _hash_file(path: str) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# -- Launcher state: `<claim>/.launcher/state.json` -- freshness and
# acceptance, removed wholesale by `strip`. -------------------------------


def _state_path(d: str) -> str:
    return os.path.join(d, LAUNCHER_DIR, STATE_FILE)


def _load_state(d: str):
    path = _state_path(d)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _save_state(d: str, state: dict) -> None:
    path = _state_path(d)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f)
    os.replace(tmp, path)


# -- Execution hygiene: scrubbed env, claim-local HOME/TMPDIR, and the
# functional sandbox probe (seatbelt / bubblewrap / inherited / none / off).
# A self-contained probe and wrapper -- the launcher never reaches into a
# kernel private for its own confinement. ---------------------------------


def _sandbox_backend(no_sandbox: bool) -> str:
    if no_sandbox:
        return "off"
    if os.environ.get(kernel._JAILED):
        return "inherited"
    if sys.platform == "darwin" and shutil.which("sandbox-exec"):
        return "seatbelt"
    if shutil.which("bwrap"):
        try:
            probe = subprocess.run(
                ["bwrap", "--ro-bind", "/", "/", "--unshare-net", "true"],
                capture_output=True, timeout=5, check=False)
            if probe.returncode == 0:
                return "bubblewrap"
        except (OSError, subprocess.SubprocessError):
            pass
    return "none"


def _quote_sb(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _seatbelt_argv(d: str, scratch: str, inner: list) -> list:
    paths = [os.path.realpath(d), os.path.realpath(scratch)]
    subpaths = "\n".join(f'  (subpath "{_quote_sb(p)}")' for p in paths)
    profile = (
        "(version 1)\n(deny default)\n(allow process-fork)\n"
        "(allow process-exec*)\n(allow signal (target same-sandbox))\n"
        "(allow file-read*)\n(allow file-write*\n"
        f"{subpaths}\n"
        '  (literal "/dev/null")\n  (literal "/dev/tty")\n'
        '  (literal "/dev/stdout")\n  (literal "/dev/stderr"))\n'
        "(allow file-ioctl)\n(allow sysctl-read)\n(allow mach-lookup)\n"
    )
    return ["/usr/bin/sandbox-exec", "-p", profile] + inner


def _bwrap_argv(d: str, scratch: str, inner: list) -> list:
    real = os.path.realpath(d)
    real_scratch = os.path.realpath(scratch)
    argv = [
        "bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc",
        "--tmpfs", "/tmp", "--bind", real, real, "--unshare-net",
        "--die-with-parent", "--chdir", real,
    ]
    if real_scratch != real and not real_scratch.startswith(real + os.sep):
        argv += ["--bind", real_scratch, real_scratch]
    return argv + inner


def _run_entrypoint(d: str, entry_abs: str, args: list, no_sandbox: bool):
    """Run the entrypoint, confined and scrubbed; returns (quarantine, rc)."""
    backend = _sandbox_backend(no_sandbox)

    scratch = os.path.join(d, LAUNCHER_DIR, SCRATCH_DIR)
    os.makedirs(scratch, exist_ok=True)

    env = {}
    for key in ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "TZ"):
        if key in os.environ:
            env[key] = os.environ[key]
    env.setdefault("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")
    env["HOME"] = scratch
    env["TMPDIR"] = scratch
    if backend in ("seatbelt", "bubblewrap", "inherited"):
        env[kernel._JAILED] = backend

    inner = [sys.executable, entry_abs] + list(args)
    if backend == "seatbelt":
        argv = _seatbelt_argv(d, scratch, inner)
    elif backend == "bubblewrap":
        argv = _bwrap_argv(d, scratch, inner)
    else:
        argv = inner

    proc = subprocess.run(argv, cwd=d, env=env)
    return backend, proc.returncode


# -- run --------------------------------------------------------------------


def _parse_run_args(args: list):
    accept_generated = False
    signed_only = False
    no_sandbox = False
    claim_arg = None
    entry_args = []
    i = 0
    n = len(args)
    while i < n:
        a = args[i]
        if a == "--":
            entry_args = list(args[i + 1:])
            break
        if a == "--accept-generated":
            accept_generated = True
        elif a == "--signed-only":
            signed_only = True
        elif a == "--no-sandbox":
            no_sandbox = True
        elif claim_arg is None:
            claim_arg = a
        else:
            raise ValueError(f"unrecognized argument: {a!r}")
        i += 1
    return accept_generated, signed_only, no_sandbox, claim_arg, entry_args


def cmd_run(args: list) -> int:
    try:
        accept_generated, signed_only, no_sandbox, claim_arg, entry_args = \
            _parse_run_args(args)
    except ValueError as e:
        eprint(str(e))
        return 2
    if claim_arg is None:
        eprint("run requires a claim path")
        return 2

    d = os.path.abspath(claim_arg)

    try:
        doc = kernel.load_recipe(d)
    except kernel.ClaimError as e:
        eprint(f"not runnable: {e}")
        return 3

    try:
        entry_abs = _package_entrypoint(d, doc)
    except kernel.ClaimError as e:
        eprint(f"not runnable: {e}")
        return 3

    generated = _generated_outputs(doc)
    try:
        safe_generated = {p: _util.safe_path(d, p) for p in generated}
    except kernel.ClaimError as e:
        eprint(f"not runnable: {e}")
        return 3

    try:
        ph = kernel.phase(d)
    except kernel.ClaimError as e:
        eprint(f"claim does not verify: {e}")
        return 1

    if signed_only and ph != "signed":
        eprint(f"claim is not signed to you (phase: {ph}); "
               "--signed-only refuses execution")
        return 5

    eprint(f"reticuli.launcher: running {doc['claim']['name']} (phase: {ph})")

    present = all(os.path.isfile(safe_generated[p]) for p in generated)
    state = _load_state(d)

    if not present:
        producer = os.environ.get(PRODUCER_VAR)
        if not producer:
            eprint("claim is latent (no generated bytes present) and no "
                   f"producer is configured; set {PRODUCER_VAR} to rebuild it")
            return 7

        tmp = tempfile.mkdtemp(prefix="reticuli-launcher-")
        try:
            kernel.rebuild(d, producer, tmp)
        except kernel.ClaimError as e:
            shutil.rmtree(tmp, ignore_errors=True)
            eprint(f"rebuild failed: {e}")
            return 1

        digests = {}
        for p in generated:
            src = _util.safe_path(tmp, p)
            dst = safe_generated[p]
            os.makedirs(os.path.dirname(dst) or d, exist_ok=True)
            shutil.copy2(src, dst)
            digests[p] = _hash_file(dst)
        shutil.rmtree(tmp, ignore_errors=True)

        if accept_generated:
            _save_state(d, {"status": "accepted", "digests": digests})
        else:
            _save_state(d, {"status": "fresh", "digests": digests})
            eprint("freshly generated bytes materialized but not accepted; "
                   "pass --accept-generated to execute and accept them")
            return 4
    elif state is not None and state.get("status") == "fresh":
        if accept_generated:
            current = {p: _hash_file(safe_generated[p]) for p in generated}
            _save_state(d, {"status": "accepted", "digests": current})
        else:
            eprint("freshly generated bytes are not yet accepted; "
                   "pass --accept-generated to execute and accept them")
            return 4
    elif state is not None and state.get("status") == "accepted":
        current = {p: _hash_file(safe_generated[p]) for p in generated}
        if current != state.get("digests"):
            eprint("accepted implementation has drifted from the bytes "
                   "accepted earlier; run `strip` to recover, then rebuild "
                   "and accept again")
            return 6
    # else: no launcher state at all -- an implementation the launcher never
    # generated or accepted runs on audit alone.

    backend, rc = _run_entrypoint(d, entry_abs, entry_args, no_sandbox)
    eprint(f'quarantine = "{backend}"')
    return rc


# -- strip -------------------------------------------------------------------


def cmd_strip(args: list) -> int:
    if not args:
        eprint("strip requires a claim path")
        return 2
    d = os.path.abspath(args[0])

    try:
        doc = kernel.load_recipe(d)
    except kernel.ClaimError as e:
        eprint(f"cannot strip: {e}")
        return 3

    generated = _generated_outputs(doc)
    try:
        safe_paths = [_util.safe_path(d, p) for p in generated]
    except kernel.ClaimError as e:
        eprint(f"cannot strip: {e}")
        return 3

    for p in safe_paths:
        if os.path.islink(p) or os.path.isfile(p):
            os.remove(p)
        elif os.path.isdir(p):
            shutil.rmtree(p)

    shutil.rmtree(os.path.join(d, LAUNCHER_DIR), ignore_errors=True)
    return 0


# -- ls -----------------------------------------------------------------


def cmd_ls(args: list) -> int:
    if not args:
        eprint("ls requires at least one claim path")
        return 2

    lines = []
    rc = 0
    for claim_arg in args:
        d = os.path.abspath(claim_arg)
        try:
            doc = kernel.load_recipe(d)
            manifest = kernel.read_manifest(d)
            ph = kernel.phase(d)
        except kernel.ClaimError as e:
            lines.append(f"{claim_arg}: refused -- {e}")
            rc = 1
            continue
        generated = _generated_outputs(doc)
        present = all(os.path.isfile(os.path.join(d, p)) for p in generated)
        status = "materialized" if present else "latent"
        lines.append(
            f"{manifest['name']}  {manifest['root'][:8]}  "
            f"phase={ph}  {status}")

    print("\n".join(lines))
    return rc


# -- entry point --------------------------------------------------------


def main(argv: list) -> int:
    if not argv:
        eprint(HELP)
        return 2
    if argv[0] in ("-h", "--help"):
        print(HELP)
        return 0

    verb, rest = argv[0], argv[1:]
    if verb == "run":
        return cmd_run(rest)
    if verb == "strip":
        return cmd_strip(rest)
    if verb == "ls":
        return cmd_ls(rest)

    eprint(f"unknown verb: {verb!r}\n\n{HELP}")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
