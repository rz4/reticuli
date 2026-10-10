"""Run, list, and strip executable Reticuli claims."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import tomllib

from . import kernel
from ._kernel import recipe as recipe_module


class NotRunnable(Exception):
    pass


def _path(directory, name):
    """Confine a declared path before using it for any filesystem action."""
    if (not isinstance(name, str) or not name or os.path.isabs(name)
            or any(part in ("", ".", "..") for part in name.replace("\\", "/").split("/"))):
        raise NotRunnable(f"path escapes claim: {name!r}")
    base = os.path.realpath(directory)
    candidate = os.path.join(base, name)
    if os.path.commonpath((base, os.path.realpath(candidate))) != base:
        raise NotRunnable(f"path escapes claim: {name!r}")
    current = base
    for part in name.replace("\\", "/").split("/"):
        current = os.path.join(current, part)
        if os.path.islink(current):
            raise NotRunnable(f"symlink in claim path: {name!r}")
    return candidate


def _recipe(directory):
    recipe = kernel.load_recipe(directory)
    for step in recipe.get("step", []):
        _path(directory, step["output"])
    return recipe


def _generated(directory, recipe):
    return {step["output"]: _path(directory, step["output"])
            for step in recipe.get("step", [])
            if step.get("class", "generated" if step["kind"] == "produce" else "pinned") == "generated"
            and "from" not in step}


def _package(directory, recipe):
    inputs = recipe_module._inputs(recipe, directory)
    if "package.toml" not in inputs:
        raise NotRunnable("package.toml must be a pinned input")
    package_path = _path(directory, "package.toml")
    try:
        with open(package_path, "rb") as stream:
            package = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise NotRunnable(f"invalid package.toml: {exc}") from exc
    entry = package.get("package", {}).get("entrypoint")
    path = _path(directory, entry)
    if not os.path.isfile(path):
        # A generated entrypoint may be absent until a producer regrows it.
        if entry not in _generated(directory, recipe):
            raise NotRunnable(f"entrypoint is absent: {entry}")
    return entry


def _state_path(directory):
    return os.path.join(directory, ".launcher", "state.json")


def _read_state(directory):
    try:
        with open(_state_path(directory), encoding="utf-8") as stream:
            state = json.load(stream)
        if state.get("status") in ("fresh", "accepted") and isinstance(state.get("digests"), dict):
            return state
    except (OSError, ValueError, AttributeError):
        pass
    return None


def _write_state(directory, status, digests):
    parent = os.path.join(directory, ".launcher")
    os.makedirs(parent, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="state-", dir=parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({"status": status, "digests": digests}, stream, sort_keys=True)
            stream.write("\n")
        os.replace(temporary, _state_path(directory))
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _digests(paths):
    return {name: kernel._hash_file(path) for name, path in paths.items()
            if os.path.isfile(path)}


def _materialized(paths):
    return all(os.path.isfile(path) for path in paths.values())


def _strip(directory):
    recipe = _recipe(directory)
    paths = _generated(directory, recipe)
    for path in paths.values():
        if os.path.lexists(path):
            if not os.path.isfile(path) or os.path.islink(path):
                raise NotRunnable(f"generated output is not a regular file: {path}")
    for path in paths.values():
        if os.path.isfile(path):
            os.unlink(path)
    state_dir = os.path.join(directory, ".launcher")
    if os.path.isdir(state_dir) and not os.path.islink(state_dir):
        shutil.rmtree(state_dir)
    print(f"stripped {directory}", file=sys.stderr)
    return 0


def _regrow(directory, recipe, paths, producer):
    with tempfile.TemporaryDirectory(prefix="reticuli-launcher-") as target:
        kernel.rebuild(directory, producer, target)
        for name, path in paths.items():
            source = _path(target, name)
            if not os.path.isfile(source):
                raise NotRunnable(f"producer omitted generated output {name}")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            shutil.copyfile(source, path)
    _write_state(directory, "fresh", _digests(paths))


def _environment(directory, backend):
    scratch = os.path.join(directory, ".launcher", "tmp")
    os.makedirs(scratch, exist_ok=True)
    env = {"PATH": os.environ.get("PATH", os.defpath), "LANG": "C",
           "LC_ALL": "C", "HOME": scratch, "TMPDIR": scratch}
    if backend in ("seatbelt", "bubblewrap", "inherited"):
        env[kernel._JAILED] = "1"
    return env


def _execute(directory, entry, args, no_sandbox):
    command = "exec " + " ".join(shlex.quote(arg) for arg in
                                  (sys.executable, entry, *args))
    if no_sandbox:
        argv, backend = ["/bin/sh", "-c", command], "off"
    else:
        argv, backend = kernel.sandbox(command, directory)
    print(f'quarantine = "{backend}"', file=sys.stderr)
    return subprocess.run(argv, cwd=directory,
                          env=_environment(directory, backend), check=False).returncode


def _run(directory, *, accept=False, signed_only=False, no_sandbox=False, args=()):
    recipe = _recipe(directory)
    entry = _package(directory, recipe)
    paths = _generated(directory, recipe)
    checked = kernel.verify(directory)
    if not checked["ok"]:
        print("claim identity drifted; strip and rebuild", file=sys.stderr)
        return 6
    state = _read_state(directory)
    if state and state["status"] == "accepted" and state["digests"] != _digests(paths):
        print("accepted build drifted; strip to recover", file=sys.stderr)
        return 6
    if signed_only and kernel.phase(directory) != "signed":
        print("signed claim required", file=sys.stderr)
        return 5
    if not _materialized(paths):
        producer = os.environ.get("RETICULI_PRODUCER")
        if not producer:
            print("latent claim needs RETICULI_PRODUCER", file=sys.stderr)
            return 7
        _regrow(directory, recipe, paths, producer)
        state = _read_state(directory)
    if state and state["status"] == "fresh":
        if state["digests"] != _digests(paths):
            print("fresh build drifted; strip to recover", file=sys.stderr)
            return 6
        if not accept:
            print("newly generated bytes need --accept-generated", file=sys.stderr)
            return 4
    audit = kernel.audit(directory)
    if not audit.get("ok"):
        print(f"build audit failed; strip to recover: {audit.get('verdict', '')}", file=sys.stderr)
        return 6
    if state and state["status"] == "fresh":
        _write_state(directory, "accepted", _digests(paths))
    print(f"{kernel.phase(directory)} claim {recipe['claim']['name']}", file=sys.stderr)
    return _execute(directory, entry, args, no_sandbox)


def _ls(directories):
    for directory in directories:
        recipe = _recipe(directory)
        manifest = kernel.read_manifest(directory)
        paths = _generated(directory, recipe)
        status = "materialized" if _materialized(paths) else "latent"
        print(f"{manifest['name']} {manifest['root'][:12]} {kernel.phase(directory)} {status}")
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    help_text = ("usage: python3 -m reticuli.launcher {run,strip,ls} ...\n"
                 "run <claim> [--accept-generated] [--signed-only] [--no-sandbox] [-- args...]\n"
                 "strip <claim>\nls <claim>...\n")
    if not argv or argv[0] in ("-h", "--help"):
        print(help_text, end="")
        return 0 if argv else 2
    verb = argv.pop(0)
    if verb not in ("run", "strip", "ls"):
        print(help_text, file=sys.stderr)
        return 2
    try:
        if verb == "ls":
            if not argv:
                raise NotRunnable("ls requires a claim")
            return _ls([os.path.abspath(item) for item in argv])
        if not argv:
            raise NotRunnable(f"{verb} requires a claim")
        directory = os.path.abspath(argv.pop(0))
        if verb == "strip":
            if argv:
                raise NotRunnable("strip takes one claim")
            return _strip(directory)
        if "--" in argv:
            boundary = argv.index("--")
            flags, args = argv[:boundary], argv[boundary + 1:]
        else:
            flags, args = argv, []
        if any(flag not in ("--accept-generated", "--signed-only", "--no-sandbox") for flag in flags):
            raise NotRunnable("unknown run option")
        return _run(directory, accept="--accept-generated" in flags,
                    signed_only="--signed-only" in flags,
                    no_sandbox="--no-sandbox" in flags, args=args)
    except (NotRunnable, kernel.ClaimError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
