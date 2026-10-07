"""The launcher: runs software that exists only latently in a claim.

`python3 -m reticuli.launcher run|strip|ls ...` (`checks/launcher_check.py`
is this module's acceptance check and its full contract). Stdlib only.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib

from reticuli import kernel

STATE_DIR = ".launcher"
STATE_FILE = "state.json"
_KEEP_ENV = ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "TZ")

HELP = """\
usage: python3 -m reticuli.launcher <command> ...

commands:
  run   <claim> [--accept-generated] [--signed-only] [--no-sandbox] [-- args...]
  strip <claim>
  ls    <claim>...

flags (run):
  --accept-generated   consent to execute and accept freshly regrown bytes
  --signed-only        refuse to execute anything not signed to you
  --no-sandbox          run unconfined; reports quarantine = "off"
"""


def _err(msg: str) -> None:
    sys.stderr.write(msg.rstrip("\n") + "\n")


# -- the path boundary, re-checked here because the kernel's loader exempts
#    generated-class outputs from confinement (crosscheck.load_recipe) --
#    the launcher is the layer that touches those bytes. -------------------

def _safe_join(root: str, name: str) -> str:
    if not name:
        raise kernel.ClaimError("refused: empty path")
    if os.path.isabs(name):
        raise kernel.ClaimError(f"refused: absolute path {name!r}")
    parts = name.split("/")
    for part in parts:
        if part in ("", ".", ".."):
            raise kernel.ClaimError(f"refused: path escapes the claim: {name!r}")
    realroot = os.path.realpath(root)
    cur = realroot
    for part in parts:
        cur = os.path.join(cur, part)
        if os.path.islink(cur):
            raise kernel.ClaimError(f"refused: symlink component in {name!r}")
    if not (cur == realroot or cur.startswith(realroot + os.sep)):
        raise kernel.ClaimError(f"refused: path escapes the claim: {name!r}")
    return cur


def _generated_outputs(recipe: dict) -> list:
    out = []
    for step in recipe.get("step", []):
        if step.get("kind") != "produce":
            continue
        if step.get("class", "generated") in ("generated", "free"):
            out.append(step["output"])
    return out


def _check_confinement(d: str, generated: list) -> None:
    for output in generated:
        _safe_join(d, output)


def _package_entrypoint(d: str, recipe: dict, generated: list) -> str:
    inputs = recipe.get("claim", {}).get("inputs", [])
    if "package.toml" in generated:
        raise kernel.ClaimError(
            "refused: package.toml must be a pinned input, not a generated output"
        )
    if "package.toml" not in inputs:
        raise kernel.ClaimError("refused: claim has no pinned package.toml")
    path = _safe_join(d, "package.toml")
    if not os.path.isfile(path):
        raise kernel.ClaimError("refused: claim has no pinned package.toml")
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise kernel.ClaimError(f"refused: malformed package.toml: {e}") from e
    entry = (data.get("package") or {}).get("entrypoint")
    if not isinstance(entry, str) or not entry:
        raise kernel.ClaimError("refused: package.toml has no [package] entrypoint")
    _safe_join(d, entry)  # refuses an escaping entrypoint
    return entry


# -- launcher state: what the launcher itself generated or accepted -------

def _state_path(d: str) -> str:
    return os.path.join(d, STATE_DIR, STATE_FILE)


def _read_state(d: str):
    path = _state_path(d)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _write_state(d: str, state: dict) -> None:
    path = _state_path(d)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f)


def _regrow(d: str, producer: str, generated: list) -> None:
    room_parent = os.path.join(d, STATE_DIR)
    os.makedirs(room_parent, exist_ok=True)
    room = tempfile.mkdtemp(dir=room_parent, prefix="room-")
    try:
        kernel.rebuild(d, producer, room)
        for output in generated:
            src = _safe_join(room, output)
            if os.path.isfile(src):
                dst = _safe_join(d, output)
                os.makedirs(os.path.dirname(dst) or d, exist_ok=True)
                shutil.copy2(src, dst)
    finally:
        shutil.rmtree(room, ignore_errors=True)


# -- sandboxed, scrubbed execution of the entrypoint -----------------------

def _seatbelt_usable() -> bool:
    exe = "/usr/bin/sandbox-exec"
    if not os.path.isfile(exe):
        return False
    try:
        done = subprocess.run(
            [exe, "-p", "(version 1)(allow default)", "/bin/sh", "-c", "true"],
            capture_output=True, timeout=10, check=False,
        )
        return done.returncode == 0
    except OSError:
        return False


def _bwrap_usable() -> bool:
    if not shutil.which("bwrap"):
        return False
    try:
        done = subprocess.run(
            ["bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "--unshare-net",
             "--die-with-parent", "true"],
            capture_output=True, timeout=10, check=False,
        )
        return done.returncode == 0
    except OSError:
        return False


def _sandbox_backend(no_sandbox: bool) -> str:
    if no_sandbox:
        return "off"
    if os.environ.get(kernel._JAILED):
        return "inherited"
    if sys.platform == "darwin" and _seatbelt_usable():
        return "seatbelt"
    if sys.platform.startswith("linux") and _bwrap_usable():
        return "bubblewrap"
    return "none"


def _quote_sb(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _seatbelt_profile(paths: list) -> str:
    allows = "\n".join(
        f'(allow file-write* (subpath "{_quote_sb(p)}"))' for p in paths
    )
    return (
        "(version 1)\n(allow default)\n(deny network*)\n(deny file-write*)\n"
        f"{allows}\n(allow file-write* (subpath \"/dev\"))\n"
    )


def _wrap_argv(backend: str, d: str, scratch: str, argv: list) -> list:
    if backend == "seatbelt":
        paths = [os.path.realpath(d), os.path.realpath(scratch)]
        return ["/usr/bin/sandbox-exec", "-p", _seatbelt_profile(paths)] + argv
    if backend == "bubblewrap":
        real_d = os.path.realpath(d)
        real_scratch = os.path.realpath(scratch)
        wrapped = ["bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc",
                  "--bind", real_d, real_d, "--bind", real_scratch, real_scratch,
                  "--unshare-net", "--die-with-parent", "--chdir", real_d]
        return wrapped + argv
    return argv


def _scrub_env(extra: dict) -> dict:
    env = {k: os.environ[k] for k in _KEEP_ENV if k in os.environ}
    env.update(extra)
    return env


def _execute(d: str, entry: str, entry_args: list, no_sandbox: bool):
    backend = _sandbox_backend(no_sandbox)
    room_parent = os.path.join(d, STATE_DIR)
    os.makedirs(room_parent, exist_ok=True)
    scratch = tempfile.mkdtemp(dir=room_parent, prefix="scratch-")
    try:
        extra_env = {"HOME": scratch, "TMPDIR": scratch}
        if backend in ("seatbelt", "bubblewrap"):
            extra_env[kernel._JAILED] = backend
        env = _scrub_env(extra_env)
        argv = _wrap_argv(backend, d, scratch, [sys.executable, entry] + list(entry_args))
        proc = subprocess.run(argv, cwd=d, env=env)
        return proc.returncode, backend
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


# -- commands ---------------------------------------------------------------

def _parse_run(args: list):
    claim = None
    accept = signed_only = no_sandbox = False
    entry_args = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--":
            entry_args = args[i + 1:]
            break
        elif a == "--accept-generated":
            accept = True
        elif a == "--signed-only":
            signed_only = True
        elif a == "--no-sandbox":
            no_sandbox = True
        elif claim is None:
            claim = a
        i += 1
    return claim, accept, signed_only, no_sandbox, entry_args


def cmd_run(args: list) -> int:
    claim, accept, signed_only, no_sandbox, entry_args = _parse_run(args)
    if claim is None or not os.path.isdir(claim):
        _err(f"refused: no such claim: {claim!r}")
        return 3

    d = os.path.abspath(claim)
    try:
        recipe = kernel.load_recipe(d)
        generated = _generated_outputs(recipe)
        _check_confinement(d, generated)
        entry = _package_entrypoint(d, recipe, generated)
    except kernel.ClaimError as e:
        _err(str(e))
        return 3

    missing = [o for o in generated if not os.path.isfile(os.path.join(d, o))]
    if missing:
        producer = os.environ.get("RETICULI_PRODUCER")
        if not producer:
            _err("refused: claim is latent and no producer is configured -- "
                "set RETICULI_PRODUCER to regrow it")
            return 7
        try:
            _regrow(d, producer, generated)
        except kernel.ClaimError as e:
            _err(f"refused: rebuild failed: {e}")
            return 1
        state = {"status": "fresh", "digest": kernel.build_digest(d)}
        _write_state(d, state)
    else:
        state = _read_state(d)

    if state is not None:
        if state.get("status") == "fresh":
            if not accept:
                _err("refused: newly generated bytes require consent -- "
                    "pass --accept-generated to execute and accept them")
                return 4
            state = {"status": "accepted", "digest": kernel.build_digest(d)}
            _write_state(d, state)
        elif state.get("status") == "accepted":
            current = kernel.build_digest(d)
            if current != state.get("digest"):
                _err(f"refused: drifted build -- the accepted implementation's "
                    f"bytes no longer match; strip {claim!r} to recover")
                return 6

    if signed_only and kernel.phase(d) != "signed":
        _err("refused: --signed-only requires a claim signed to you; "
            "this claim is not signed")
        return 5

    _err(f"{claim}: phase={kernel.phase(d)}")
    rc, backend = _execute(d, entry, entry_args, no_sandbox)
    _err(f'quarantine = "{backend}"')
    return rc


def cmd_strip(args: list) -> int:
    if not args:
        _err("refused: strip needs a claim")
        return 3
    claim = args[0]
    d = os.path.abspath(claim)
    try:
        recipe = kernel.load_recipe(d)
        generated = _generated_outputs(recipe)
        _check_confinement(d, generated)
    except kernel.ClaimError as e:
        _err(str(e))
        return 3

    for output in generated:
        path = _safe_join(d, output)
        if os.path.islink(path) or os.path.isfile(path):
            os.remove(path)
        elif os.path.isdir(path):
            shutil.rmtree(path)
    shutil.rmtree(os.path.join(d, STATE_DIR), ignore_errors=True)
    return 0


def cmd_ls(args: list) -> int:
    lines = []
    for claim in args:
        d = os.path.abspath(claim)
        try:
            recipe = kernel.load_recipe(d)
            manifest = kernel.read_manifest(d)
            generated = _generated_outputs(recipe)
            present = all(os.path.isfile(os.path.join(d, o)) for o in generated)
            state_word = "materialized" if present else "latent"
            ph = kernel.phase(d)
            lines.append(
                f"{manifest['name']}  {manifest['root'][:8]}  {ph}  {state_word}  {d}"
            )
        except kernel.ClaimError as e:
            lines.append(f"{claim}: {e}")
    sys.stdout.write("\n".join(lines) + ("\n" if lines else ""))
    return 0


def main(argv: list) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        _err(HELP)
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "run":
        return cmd_run(rest)
    if cmd == "strip":
        return cmd_strip(rest)
    if cmd == "ls":
        return cmd_ls(rest)
    _err(f"refused: unknown command: {cmd!r}")
    return 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
