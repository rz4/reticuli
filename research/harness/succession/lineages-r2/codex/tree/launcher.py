"""Run and retire the generated implementation of a sealed package claim."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tomllib

from . import kernel
from ._kernel import recipe as recipes, run as execution
from ._util import safe_path


class NotRunnable(Exception):
    pass


def _recipe(directory):
    try:
        parsed = kernel.load_recipe(directory)
        # Check every output before any state change, including absent files.
        for step in parsed.get("step", []):
            safe_path(directory, step["output"])
        return parsed
    except (kernel.ClaimError, KeyError, TypeError) as exc:
        raise NotRunnable(str(exc)) from exc


def _generated(parsed):
    return [step for step in parsed.get("step", [])
            if step.get("kind") == "produce"
            and step.get("class", "generated") in ("generated", "free")]


def _package(directory, parsed):
    try:
        inputs = recipes._inputs(parsed, directory)
        if "package.toml" not in inputs:
            raise NotRunnable("package.toml must be a pinned input")
        path = safe_path(directory, "package.toml")
        with open(path, "rb") as stream:
            package = tomllib.load(stream)
        entry = package["package"]["entrypoint"]
        if not isinstance(entry, str):
            raise NotRunnable("package entrypoint must be a path")
        safe_path(directory, entry)
        return entry
    except (kernel.ClaimError, OSError, tomllib.TOMLDecodeError,
            KeyError, TypeError, ValueError) as exc:
        raise NotRunnable("invalid package.toml: " + str(exc)) from exc


def _digests(directory, steps):
    return {step["output"]: kernel._hash_file(safe_path(directory, step["output"]))
            for step in steps}


def _state_path(directory):
    return safe_path(directory, ".launcher/state.json")


def _read_state(directory):
    path = _state_path(directory)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as stream:
            value = json.load(stream)
        if isinstance(value, dict):
            return value
    except (OSError, ValueError):
        pass
    raise NotRunnable("invalid launcher state")


def _write_state(directory, value):
    path = _state_path(directory)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True)
        stream.write("\n")
    os.replace(temporary, path)


def _scrub(directory, *, sandbox=None):
    scratch = safe_path(directory, ".launcher/tmp")
    os.makedirs(scratch, exist_ok=True)
    env = {"PATH": os.environ.get("PATH", os.defpath),
           "LANG": "C", "LC_ALL": "C", "HOME": scratch, "TMPDIR": scratch}
    if sandbox in ("seatbelt", "bubblewrap", "inherited"):
        env["RETICULI_JAILED"] = sandbox
    return env


def _produce(directory, steps, command):
    for step in steps:
        output = step["output"]
        path = safe_path(directory, output)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        env = _scrub(directory)
        env["RETICULI_OUTPUT"] = output
        env["RETICULI_REQUEST"] = step.get("guidance", step.get("request", ""))
        done = subprocess.run(command, shell=True, cwd=directory, env=env,
                              capture_output=True, text=True, timeout=3600)
        if done.returncode or not os.path.isfile(path):
            raise NotRunnable("producer failed for " + output + ": " + done.stderr[-300:])


def _audit(directory):
    try:
        checked = kernel.verify(directory)
        if not checked["ok"]:
            return False
        return bool(kernel.audit(directory)["ok"])
    except kernel.ClaimError:
        return False


def _execute(directory, entry, args, no_sandbox):
    backend = "off" if no_sandbox else execution.sandbox_backend()
    env = _scrub(directory, sandbox=backend)
    command = [sys.executable, safe_path(directory, entry), *args]
    if backend in ("seatbelt", "bubblewrap"):
        # The kernel owns the platform profiles. Quote each argument into its
        # shell command, as _sandbox_argv runs through /bin/sh.
        import shlex
        argv = execution._sandbox_argv(shlex.join(command), directory, backend)
    else:
        argv = command
    print(f'quarantine = "{backend}"', file=sys.stderr)
    return subprocess.call(argv, cwd=directory, env=env)


def run_claim(directory, args, *, accept_generated=False, signed_only=False,
              no_sandbox=False):
    directory = os.path.realpath(directory)
    parsed = _recipe(directory)
    entry = _package(directory, parsed)
    try:
        phase = kernel.phase(directory)
    except kernel.ClaimError as exc:
        print("drifted claim: " + str(exc) + "; use strip to recover", file=sys.stderr)
        return 6
    if signed_only and phase != "signed":
        print("signed-only requires a signed claim", file=sys.stderr)
        return 5
    print(phase + " claim", file=sys.stderr)
    steps = _generated(parsed)
    state = _read_state(directory)
    missing = [step for step in steps if not os.path.isfile(safe_path(directory, step["output"]))]
    if state.get("accepted") is not None:
        if missing or _digests(directory, steps) != state["accepted"]:
            print("accepted build drifted; use strip to recover", file=sys.stderr)
            return 6
    elif state.get("fresh") is not None and not missing:
        if _digests(directory, steps) != state["fresh"]:
            print("fresh build drifted; use strip to recover", file=sys.stderr)
            return 6
    if missing:
        producer = os.environ.get("RETICULI_PRODUCER")
        if not producer:
            print("latent claim: set RETICULI_PRODUCER to regrow it", file=sys.stderr)
            return 7
        try:
            _produce(directory, missing, producer)
            state = {"fresh": _digests(directory, steps)}
            _write_state(directory, state)
        except (OSError, subprocess.TimeoutExpired, kernel.ClaimError, NotRunnable) as exc:
            print("cannot regrow build: " + str(exc), file=sys.stderr)
            return 6
    if not _audit(directory):
        print("build audit failed; use strip to recover", file=sys.stderr)
        return 6
    if state.get("fresh") is not None:
        if not accept_generated:
            print("newly generated bytes require --accept-generated", file=sys.stderr)
            return 4
        state = {"accepted": _digests(directory, steps)}
        _write_state(directory, state)
    if not os.path.isfile(safe_path(directory, entry)):
        print("entrypoint is absent: " + entry, file=sys.stderr)
        return 3
    return _execute(directory, entry, args, no_sandbox)


def strip_claim(directory):
    directory = os.path.realpath(directory)
    parsed = _recipe(directory)
    paths = [safe_path(directory, step["output"]) for step in _generated(parsed)]
    state = _state_path(directory)
    for path in paths:
        if os.path.lexists(path):
            if not os.path.isfile(path) or os.path.islink(path):
                raise NotRunnable("generated path is not a regular file: " + path)
            os.unlink(path)
    if os.path.exists(state):
        os.unlink(state)
    return 0


def list_claims(directories):
    for directory in directories:
        directory = os.path.realpath(directory)
        parsed = _recipe(directory)
        manifest = kernel.read_manifest(directory)
        phase = kernel.phase(directory)
        materialized = all(os.path.isfile(safe_path(directory, s["output"]))
                           for s in _generated(parsed))
        print(f'{parsed["claim"]["name"]} {manifest["root"][:8]} {phase} '
              f'{"materialized" if materialized else "latent"} {directory}')
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Run sealed package claims",
        epilog="run options: --accept-generated, --signed-only, --no-sandbox")
    subs = parser.add_subparsers(dest="verb", required=True)
    runner = subs.add_parser("run")
    runner.add_argument("claim")
    runner.add_argument("--accept-generated", action="store_true")
    runner.add_argument("--signed-only", action="store_true")
    runner.add_argument("--no-sandbox", action="store_true")
    stripper = subs.add_parser("strip")
    stripper.add_argument("claim")
    listing = subs.add_parser("ls")
    listing.add_argument("claims", nargs="+")
    argv = list(sys.argv[1:] if argv is None else argv)
    extra = []
    if "--" in argv:
        index = argv.index("--")
        extra = argv[index + 1:]
        argv = argv[:index]
    options = parser.parse_args(argv)
    try:
        if options.verb == "run":
            return run_claim(options.claim, extra,
                             accept_generated=options.accept_generated,
                             signed_only=options.signed_only,
                             no_sandbox=options.no_sandbox)
        if options.verb == "strip":
            return strip_claim(options.claim)
        return list_claims(options.claims)
    except (NotRunnable, kernel.ClaimError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
