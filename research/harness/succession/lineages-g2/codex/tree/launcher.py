"""Run, list, and strip executable Reticuli claims.

Launcher bookkeeping is residue.  The claim's recipe and pinned bytes remain
the authority for identity; accepted build digests only guard local consent.
"""

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
from ._kernel import core, recipe as recipes


STATE = ".launcher/state.json"


class NotRunnable(Exception):
    pass


def _directory(value: str) -> str:
    return os.path.realpath(os.path.abspath(value))


def _path(directory: str, name: str) -> str:
    try:
        return core._safe(directory, name)
    except kernel.ClaimError as exc:
        raise NotRunnable(str(exc)) from exc


def _recipe(directory: str) -> dict:
    try:
        parsed = kernel.load_recipe(directory)
        # Force validation of all declared paths, including those obtained from
        # an inputs manifest, before either verb mutates a claim.
        for name in recipes._inputs(parsed, directory):
            _path(directory, name)
        for step in parsed.get("step", []):
            _path(directory, step["output"])
        return parsed
    except kernel.ClaimError as exc:
        raise NotRunnable(str(exc)) from exc


def _generated(parsed: dict) -> list[str]:
    return [step["output"] for step in parsed.get("step", [])
            if step.get("class", "generated" if step["kind"] == "produce" else "pinned")
            in ("generated", "free") and "from" not in step]


def _package(directory: str, parsed: dict) -> str:
    inputs = recipes._inputs(parsed, directory)
    if "package.toml" not in inputs:
        raise NotRunnable("package.toml must be a pinned input")
    package_path = _path(directory, "package.toml")
    try:
        core._hash_file(package_path)
        with open(package_path, "rb") as stream:
            package = tomllib.load(stream)
        entry = package["package"]["entrypoint"]
        if not isinstance(entry, str):
            raise ValueError("entrypoint must be a string")
    except (OSError, ValueError, KeyError, TypeError, tomllib.TOMLDecodeError,
            kernel.ClaimError) as exc:
        raise NotRunnable("invalid pinned package.toml: " + str(exc)) from exc
    return _path(directory, entry)


def _state_path(directory: str) -> str:
    return _path(directory, STATE)


def _state(directory: str) -> dict | None:
    path = _state_path(directory)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as stream:
            value = json.load(stream)
        if (isinstance(value, dict) and value.get("status") in ("fresh", "accepted")
                and isinstance(value.get("digest"), str)):
            return value
    except (OSError, ValueError):
        pass
    raise NotRunnable("invalid launcher state")


def _save_state(directory: str, status: str) -> None:
    path = _state_path(directory)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    value = {"status": status, "digest": kernel.build_digest(directory)}
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True)
        stream.write("\n")


def _phase(directory: str) -> str:
    return kernel.phase(directory)


def _scrubbed_env(directory: str, backend: str) -> dict[str, str]:
    env = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL", "TZ")
           if key in os.environ}
    env.setdefault("PATH", os.defpath)
    scratch = _path(directory, ".launcher/tmp")
    os.makedirs(scratch, exist_ok=True)
    env["HOME"] = scratch
    env["TMPDIR"] = scratch
    if backend in ("seatbelt", "bubblewrap", "inherited"):
        env[kernel._JAILED] = "1"
    return env


def _execute(directory: str, entry: str, args: list[str], no_sandbox: bool) -> int:
    command = [sys.executable, entry, *args]
    if no_sandbox:
        argv, backend = command, "off"
    else:
        argv, backend = kernel.sandbox(shlex.join(command), directory)
    env = _scrubbed_env(directory, backend)
    print(f'quarantine = "{backend}"', file=sys.stderr)
    try:
        return subprocess.run(argv, cwd=directory, env=env, check=False).returncode
    except OSError as exc:
        print(f"launcher: cannot execute entrypoint: {exc}", file=sys.stderr)
        return 3


def run_claim(directory: str, args: list[str], *, accept: bool = False,
              signed_only: bool = False, no_sandbox: bool = False) -> int:
    directory = _directory(directory)
    try:
        parsed = _recipe(directory)
        entry = _package(directory, parsed)
        phase = _phase(directory)
        if signed_only and phase != "signed":
            print("launcher: signed claim required", file=sys.stderr)
            return 5
        if not kernel.verify(directory)["ok"]:
            print("launcher: claim identity mismatch", file=sys.stderr)
            return 6
        outputs = _generated(parsed)
        missing = [name for name in outputs if not os.path.isfile(_path(directory, name))]
        state = _state(directory)
        if not missing and state and state["status"] == "accepted":
            if state["digest"] != kernel.build_digest(directory):
                print("launcher: accepted build drifted; strip to recover", file=sys.stderr)
                return 6
        if missing:
            producer = os.environ.get("RETICULI_PRODUCER")
            if not producer:
                print("launcher: latent claim needs RETICULI_PRODUCER", file=sys.stderr)
                return 7
            with tempfile.TemporaryDirectory(prefix="reticuli-launch-") as room:
                result = kernel.rebuild(directory, producer, room)
                if result["root"] != kernel.read_manifest(directory)["root"]:
                    print("launcher: rebuilt root differs", file=sys.stderr)
                    return 6
                for name in outputs:
                    source = _path(room, name)
                    target = _path(directory, name)
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    shutil.copy2(source, target)
            _save_state(directory, "fresh")
            state = _state(directory)
        if state and state["status"] == "fresh" and not accept:
            print("launcher: newly generated bytes; pass --accept-generated to execute",
                  file=sys.stderr)
            return 4
        audited = kernel.audit(directory)
        if not audited["ok"]:
            print("launcher: build audit failed; strip to recover", file=sys.stderr)
            return 6
        if not os.path.isfile(entry):
            raise NotRunnable("package entrypoint is absent")
        if state and state["status"] == "fresh" and accept:
            _save_state(directory, "accepted")
        print(f"launcher: {phase}", file=sys.stderr)
        return _execute(directory, entry, args, no_sandbox)
    except NotRunnable as exc:
        print(f"launcher: {exc}", file=sys.stderr)
        return 3
    except kernel.ClaimError as exc:
        print(f"launcher: {exc}", file=sys.stderr)
        return 6


def strip_claim(directory: str) -> int:
    directory = _directory(directory)
    try:
        parsed = _recipe(directory)
        for name in _generated(parsed):
            path = _path(directory, name)
            if os.path.lexists(path):
                os.unlink(path)
        shutil.rmtree(os.path.join(directory, ".launcher"), ignore_errors=True)
        return 0
    except (NotRunnable, OSError) as exc:
        print(f"launcher: {exc}", file=sys.stderr)
        return 3


def list_claims(directories: list[str]) -> int:
    status = 0
    for value in directories:
        directory = _directory(value)
        try:
            parsed = _recipe(directory)
            manifest = kernel.read_manifest(directory)
            phase = _phase(directory)
            presence = "latent" if any(not os.path.isfile(_path(directory, name))
                                       for name in _generated(parsed)) else "materialized"
            print(f"{manifest['name']} {manifest['root'][:12]} {phase} {presence} {value}")
        except (NotRunnable, kernel.ClaimError) as exc:
            print(f"launcher: {value}: {exc}", file=sys.stderr)
            status = 3
    return status


HELP = """usage: python3 -m reticuli.launcher VERB CLAIM [options]

verbs:
  run CLAIM [--accept-generated] [--signed-only] [--no-sandbox] [-- args...]
  strip CLAIM
  ls CLAIM...
"""


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(HELP)
        return 0
    verb = argv.pop(0)
    if verb == "run" and argv:
        directory = argv.pop(0)
        options = {"--accept-generated": False, "--signed-only": False,
                   "--no-sandbox": False}
        while argv and argv[0] != "--":
            flag = argv.pop(0)
            if flag not in options:
                print(f"launcher: unknown option {flag}", file=sys.stderr)
                return 3
            options[flag] = True
        if argv and argv[0] == "--":
            argv.pop(0)
        return run_claim(directory, argv, accept=options["--accept-generated"],
                         signed_only=options["--signed-only"],
                         no_sandbox=options["--no-sandbox"])
    if verb == "strip" and len(argv) == 1:
        return strip_claim(argv[0])
    if verb == "ls" and argv:
        return list_claims(argv)
    print(HELP, file=sys.stderr)
    return 3


if __name__ == "__main__":
    sys.exit(main())
