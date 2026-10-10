"""Run, list, and strip executable Reticuli claims."""

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

from . import kernel
from ._util import declared_inputs, safe_path


STATE = ".launcher"


def _error(message, code=3):
    print(f"launcher: {message}", file=sys.stderr)
    return code


def _generated(parsed):
    return [step["output"] for step in parsed.get("step", [])
            if step["kind"] == "produce"
            and step.get("class", "generated") in ("generated", "free")
            and "from" not in step]


def _load(directory):
    directory = os.path.abspath(directory)
    parsed = kernel.load_recipe(directory)
    # Validate every path before a verb can touch a file. load_recipe performs
    # this check for recipe paths; safe_path keeps the launcher's own paths
    # under the same claim root.
    for name in _generated(parsed):
        safe_path(directory, name)
    checked = kernel.verify(directory)
    if not checked["ok"]:
        raise kernel.ClaimError("claim identity does not match its seal")
    return directory, parsed, checked


def _package(directory, parsed):
    if "package.toml" not in declared_inputs(parsed, directory):
        raise kernel.ClaimError("package.toml must be a pinned input")
    if any(step.get("output") == "package.toml" and
           step.get("class", "generated" if step["kind"] == "produce" else "pinned")
           in ("generated", "free") for step in parsed.get("step", [])):
        raise kernel.ClaimError("package.toml must be a pinned input")
    package_path = safe_path(directory, "package.toml")
    try:
        with open(package_path, "rb") as stream:
            package = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise kernel.ClaimError(f"cannot read package.toml: {exc}") from exc
    entry = package.get("package", {}).get("entrypoint")
    if not isinstance(entry, str):
        raise kernel.ClaimError("package.toml needs a package entrypoint")
    safe_path(directory, entry)
    return entry


def _state_path(directory):
    return os.path.join(directory, STATE, "build.json")


def _read_state(directory):
    try:
        with open(_state_path(directory), encoding="utf-8") as stream:
            state = json.load(stream)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        raise kernel.ClaimError(f"cannot read launcher state: {exc}") from exc
    if not isinstance(state, dict) or state.get("status") not in ("fresh", "accepted") or not isinstance(state.get("digest"), str):
        raise kernel.ClaimError("invalid launcher state")
    return state


def _write_state(directory, status):
    folder = os.path.join(directory, STATE)
    os.makedirs(folder, exist_ok=True)
    destination = _state_path(directory)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=folder, delete=False) as stream:
        temporary = stream.name
        json.dump({"status": status, "digest": kernel.build_digest(directory)}, stream)
        stream.write("\n")
    os.replace(temporary, destination)


def _materialized(directory, names):
    return all(os.path.isfile(safe_path(directory, name)) for name in names)


def _execute(directory, entry, arguments, phase, no_sandbox):
    command = [sys.executable, safe_path(directory, entry), *arguments]
    if no_sandbox:
        argv, backend = command, "off"
    else:
        shell_command = " ".join(shlex.quote(arg) for arg in command)
        argv, backend = kernel.sandbox(shell_command, directory)
    scratch = os.path.join(directory, kernel.STORE, "launcher-tmp")
    os.makedirs(scratch, exist_ok=True)
    env = {"PATH": os.environ.get("PATH", os.defpath),
           "LANG": os.environ.get("LANG", "C.UTF-8"),
           "HOME": scratch, "TMPDIR": scratch}
    for key in ("LC_ALL", "TZ"):
        if key in os.environ:
            env[key] = os.environ[key]
    if backend in ("seatbelt", "bubblewrap", "inherited"):
        env["RETICULI_JAILED"] = "1"
    print(f"launcher: {phase}; quarantine = {json.dumps(backend)}", file=sys.stderr)
    try:
        return subprocess.run(argv, cwd=directory, env=env, check=False).returncode
    except OSError as exc:
        return _error(f"cannot execute entrypoint: {exc}", 3)


def run(directory, arguments=(), *, accept_generated=False, signed_only=False,
        no_sandbox=False):
    try:
        directory, parsed, _ = _load(directory)
        entry = _package(directory, parsed)
        phase = kernel.phase(directory)
        if signed_only and phase != "signed":
            return _error("signed claim required", 5)
        names = _generated(parsed)
        state = _read_state(directory)
        present = _materialized(directory, names)
        if state and state["status"] == "accepted" and present:
            if kernel.build_digest(directory) != state["digest"]:
                return _error("accepted build drifted; strip the claim to recover", 6)
        if not present:
            producer = os.environ.get("RETICULI_PRODUCER")
            if not producer:
                return _error("latent claim needs RETICULI_PRODUCER", 7)
            with tempfile.TemporaryDirectory(prefix="reticuli-launch-") as room:
                kernel.rebuild(directory, producer, room)
                for name in names:
                    source = safe_path(room, name)
                    target = safe_path(directory, name)
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    shutil.copyfile(source, target)
            _write_state(directory, "fresh")
            state = _read_state(directory)
        if state and state["status"] == "fresh" and not accept_generated:
            return _error("fresh generated bytes need --accept-generated", 4)
        if not kernel.audit(directory)["ok"]:
            return _error("build audit failed; strip the claim to recover", 6)
        if state and state["status"] == "fresh":
            _write_state(directory, "accepted")
        return _execute(directory, entry, arguments, phase, no_sandbox)
    except (kernel.ClaimError, OSError, ValueError) as exc:
        return _error(str(exc), 3)


def strip(directory):
    try:
        directory, parsed, _ = _load(directory)
        names = _generated(parsed)
        paths = [safe_path(directory, name) for name in names]
        for path in paths:
            if os.path.lexists(path):
                os.unlink(path)
        shutil.rmtree(os.path.join(directory, STATE), ignore_errors=True)
        return 0
    except (kernel.ClaimError, OSError, ValueError) as exc:
        return _error(str(exc), 3)


def ls(directories):
    try:
        for directory in directories:
            directory, parsed, checked = _load(directory)
            status = "materialized" if _materialized(directory, _generated(parsed)) else "latent"
            print(f"{parsed['claim']['name']} {checked['root'][:12]} {kernel.phase(directory)} {status}")
        return 0
    except (kernel.ClaimError, OSError, ValueError) as exc:
        return _error(str(exc), 3)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Run or strip executable claims",
        epilog="run options: --accept-generated, --signed-only, --no-sandbox")
    verbs = parser.add_subparsers(dest="verb", required=True)
    runner = verbs.add_parser("run", help="run a claim")
    runner.add_argument("claim")
    runner.add_argument("--accept-generated", action="store_true")
    runner.add_argument("--signed-only", action="store_true")
    runner.add_argument("--no-sandbox", action="store_true")
    verbs.add_parser("strip", help="remove generated bytes").add_argument("claim")
    verbs.add_parser("ls", help="list claim status").add_argument("claims", nargs="+")
    args, rest = parser.parse_known_args(argv)
    if args.verb == "run":
        if rest and rest[0] == "--":
            rest = rest[1:]
        return run(args.claim, rest, accept_generated=args.accept_generated,
                   signed_only=args.signed_only, no_sandbox=args.no_sandbox)
    if rest:
        parser.error("unrecognized arguments: " + " ".join(rest))
    return strip(args.claim) if args.verb == "strip" else ls(args.claims)


if __name__ == "__main__":
    sys.exit(main())
