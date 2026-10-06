"""Run a sealed claim's package, or return its generated files to latency."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

from . import kernel
from ._kernel import run as gate_run
from ._util import declared_inputs, safe_path


STATE = ".launcher/state.json"


class NotRunnable(Exception):
    pass


def _recipe(directory):
    try:
        recipe = kernel.load_recipe(directory)
        # Check every declared path before a command can mutate the claim.
        for name in declared_inputs(recipe, directory):
            safe_path(directory, name)
        for step in recipe.get("step", []):
            safe_path(directory, step["output"])
        return recipe
    except (kernel.ClaimError, KeyError, TypeError, OSError) as error:
        raise NotRunnable(str(error)) from error


def _generated(directory, recipe):
    return [step["output"] for step in recipe.get("step", [])
            if step["kind"] == "produce"
            and step.get("class", "generated") == "generated"
            and "from" not in step]


def _package(directory, recipe):
    if "package.toml" not in declared_inputs(recipe, directory):
        raise NotRunnable("package.toml must be a pinned input")
    path = safe_path(directory, "package.toml")
    try:
        with open(path, "rb") as source:
            package = tomllib.load(source)
        entry = package["package"]["entrypoint"]
        if not isinstance(entry, str):
            raise ValueError("entrypoint must be a path")
        safe_path(directory, entry)
        return entry
    except (OSError, tomllib.TOMLDecodeError, KeyError, ValueError,
            kernel.ClaimError) as error:
        raise NotRunnable(f"invalid package.toml: {error}") from error


def _state_path(directory):
    return safe_path(directory, STATE)


def _read_state(directory):
    try:
        with open(_state_path(directory), encoding="utf-8") as source:
            state = json.load(source)
        return state if isinstance(state, dict) else {}
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as error:
        raise kernel.ClaimError(f"invalid launcher state: {error}") from error


def _write_state(directory, state):
    path = _state_path(directory)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as target:
        json.dump(state, target, sort_keys=True)
        target.write("\n")


def _materialized(directory, outputs):
    return all(os.path.isfile(safe_path(directory, name)) for name in outputs)


def _execute(directory, entry, args, no_sandbox):
    backend = "off" if no_sandbox else gate_run.sandbox_backend()
    if not no_sandbox and backend == "none":
        if sys.platform == "darwin" and shutil.which("sandbox-exec"):
            backend = "seatbelt"
        elif sys.platform.startswith("linux") and shutil.which("bwrap"):
            probe = subprocess.run(
                ["bwrap", "--ro-bind", "/", "/", "--unshare-net", "true"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=5, check=False)
            if probe.returncode == 0:
                backend = "bubblewrap"
    scratch = os.path.join(directory, kernel.STORE, "tmp")
    os.makedirs(scratch, exist_ok=True)
    environment = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LANG": os.environ.get("LANG", "C"),
        "LC_ALL": os.environ.get("LC_ALL", "C"),
        "HOME": scratch,
        "TMPDIR": scratch,
    }
    if backend in ("seatbelt", "bubblewrap", "inherited"):
        environment[kernel._JAILED] = "1"
    command = [sys.executable, entry, *args]
    if backend in ("seatbelt", "bubblewrap"):
        command = gate_run._sandbox_argv(shlex.join(command), directory, backend)
    print(f'quarantine = "{backend}"', file=sys.stderr)
    try:
        return subprocess.run(command, cwd=directory, env=environment,
                              check=False).returncode
    except OSError as error:
        print(f"entrypoint failed to start: {error}", file=sys.stderr)
        return 3


def run(directory, args=(), *, accept_generated=False, signed_only=False,
        no_sandbox=False):
    directory = os.path.abspath(directory)
    try:
        recipe = _recipe(directory)
        entry = _package(directory, recipe)
        checked = kernel.verify(directory)
        if not checked["ok"]:
            print("claim identity drifted; strip and restore the pinned files",
                  file=sys.stderr)
            return 6
        phase = kernel.phase(directory)
        if signed_only and phase != "signed":
            print("signed claim required", file=sys.stderr)
            return 5
        outputs = _generated(directory, recipe)
        state = _read_state(directory)
        if not _materialized(directory, outputs):
            producer = os.environ.get("RETICULI_PRODUCER")
            if not producer:
                print("latent claim needs RETICULI_PRODUCER", file=sys.stderr)
                return 7
            with tempfile.TemporaryDirectory(prefix="reticuli-launch-") as room:
                kernel.rebuild(directory, producer, room)
                for name in outputs:
                    source = safe_path(room, name)
                    destination = safe_path(directory, name)
                    os.makedirs(os.path.dirname(destination), exist_ok=True)
                    shutil.copy2(source, destination)
            state = {"pending": kernel.build_digest(directory)}
            _write_state(directory, state)
        digest = kernel.build_digest(directory)
        if state.get("accepted") and state["accepted"] != digest:
            print("accepted build drifted; strip to recover", file=sys.stderr)
            return 6
        audit = kernel.audit(directory)
        if not audit.get("ok"):
            print("build audit failed; strip to recover", file=sys.stderr)
            return 6
        if state.get("pending"):
            if state["pending"] != digest:
                print("fresh build drifted; strip to recover", file=sys.stderr)
                return 6
            if not accept_generated:
                print("newly generated bytes need --accept-generated", file=sys.stderr)
                return 4
            _write_state(directory, {"accepted": digest})
        print(f"{phase} claim {recipe['claim']['name']} {checked['root'][:12]}",
              file=sys.stderr)
        return _execute(directory, entry, args, no_sandbox)
    except NotRunnable as error:
        print(f"not runnable: {error}", file=sys.stderr)
        return 3
    except (kernel.ClaimError, OSError) as error:
        print(f"claim failed: {error}", file=sys.stderr)
        return 6


def strip(directory):
    directory = os.path.abspath(directory)
    try:
        recipe = _recipe(directory)
        outputs = _generated(directory, recipe)
        for name in outputs:
            path = safe_path(directory, name)
            if os.path.lexists(path):
                os.unlink(path)
        shutil.rmtree(os.path.join(directory, ".launcher"), ignore_errors=True)
        print(f"stripped {recipe['claim']['name']}", file=sys.stderr)
        return 0
    except NotRunnable as error:
        print(f"not runnable: {error}", file=sys.stderr)
        return 3
    except (kernel.ClaimError, OSError) as error:
        print(f"strip failed: {error}", file=sys.stderr)
        return 3


def ls(directories):
    for directory in directories:
        directory = os.path.abspath(directory)
        try:
            recipe = _recipe(directory)
            manifest = kernel.read_manifest(directory)
            phase = kernel.phase(directory)
            status = "materialized" if _materialized(directory, _generated(directory, recipe)) else "latent"
            print(f"{recipe['claim']['name']} {manifest['root'][:12]} {phase} {status} {directory}")
        except (NotRunnable, kernel.ClaimError, OSError) as error:
            print(f"cannot list {directory}: {error}", file=sys.stderr)
            return 3
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Run, strip, or list Reticuli packages",
        epilog="run options: --accept-generated --signed-only --no-sandbox")
    sub = parser.add_subparsers(dest="verb", required=True)
    running = sub.add_parser("run", help="run a package entrypoint")
    running.add_argument("claim")
    running.add_argument("--accept-generated", action="store_true")
    running.add_argument("--signed-only", action="store_true")
    running.add_argument("--no-sandbox", action="store_true")
    stripping = sub.add_parser("strip", help="remove generated bytes")
    stripping.add_argument("claim")
    listing = sub.add_parser("ls", help="list claims and build state")
    listing.add_argument("claims", nargs="+")
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--" in argv:
        split = argv.index("--")
        control, arguments = argv[:split], argv[split + 1:]
    else:
        control, arguments = argv, []
    options = parser.parse_args(control)
    if options.verb == "run":
        return run(options.claim, arguments,
                   accept_generated=options.accept_generated,
                   signed_only=options.signed_only,
                   no_sandbox=options.no_sandbox)
    if options.verb == "strip":
        return strip(options.claim)
    return ls(options.claims)


if __name__ == "__main__":
    sys.exit(main())
