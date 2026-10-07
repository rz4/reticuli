"""Run and strip the generated implementation of a sealed package claim."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

from . import kernel


class NotRunnable(Exception):
    pass


def _path(directory: str, name: str) -> str:
    """Confine a declared path before reading, writing, or removing it."""
    if not isinstance(name, str) or not name or os.path.isabs(name):
        raise NotRunnable(f"unsafe claim path: {name!r}")
    parts = name.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise NotRunnable(f"unsafe claim path: {name!r}")
    root = os.path.realpath(directory)
    cursor = root
    for part in parts:
        cursor = os.path.join(cursor, part)
        if os.path.islink(cursor):
            raise NotRunnable(f"symlink in claim path: {name!r}")
    if os.path.commonpath((root, os.path.realpath(cursor))) != root:
        raise NotRunnable(f"claim path escapes directory: {name!r}")
    return cursor


def _generated(directory: str, recipe: dict) -> list[tuple[str, str]]:
    outputs = []
    for step in recipe.get("step", []):
        if step["kind"] == "produce" and step.get("class", "generated") in ("generated", "free"):
            name = step["output"]
            outputs.append((name, _path(directory, name)))
    return outputs


def _package(directory: str, recipe: dict) -> str:
    claim = recipe["claim"]
    inputs = claim.get("inputs", [])
    if "package.toml" not in inputs:
        manifest = claim.get("inputs_manifest")
        if manifest:
            try:
                lines = Path(_path(directory, manifest)).read_text(encoding="utf-8").splitlines()
                inputs = inputs + [line.strip().split("  ", 1)[-1] for line in lines
                                   if line.strip() and not line.lstrip().startswith("#")]
            except OSError as exc:
                raise NotRunnable(f"cannot read package inputs: {exc}") from exc
    if "package.toml" not in inputs:
        raise NotRunnable("package.toml must be a pinned input")
    try:
        package = tomllib.loads(Path(_path(directory, "package.toml")).read_text(encoding="utf-8"))
        entry = package["package"]["entrypoint"]
        path = _path(directory, entry)
    except (OSError, UnicodeError, tomllib.TOMLDecodeError, KeyError, TypeError) as exc:
        raise NotRunnable(f"invalid package.toml: {exc}") from exc
    return path


def _state_path(directory: str) -> str:
    return os.path.join(directory, ".launcher", "state.json")


def _state(directory: str) -> dict:
    try:
        value = json.loads(Path(_state_path(directory)).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_state(directory: str, status: str) -> None:
    target = _state_path(directory)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=os.path.dirname(target), delete=False,
                                     encoding="utf-8") as stream:
        json.dump({"status": status, "digest": kernel.build_digest(directory)}, stream)
        stream.write("\n")
        temporary = stream.name
    os.replace(temporary, target)


def _phase(directory: str) -> str:
    return kernel.phase(directory)


def _backend() -> str:
    result = kernel.sandbox()
    if isinstance(result, dict):
        return result.get("backend", "none")
    if isinstance(result, (tuple, list)):
        return result[-1]
    return result if isinstance(result, str) else "none"


def _execution(directory: str, entry: str, args: list[str], no_sandbox: bool) -> int:
    backend = "off" if no_sandbox else _backend()
    scratch = os.path.join(directory, ".launcher", "tmp")
    os.makedirs(scratch, exist_ok=True)
    env = {"PATH": os.environ.get("PATH", os.defpath),
           "HOME": scratch, "TMPDIR": scratch,
           "LANG": os.environ.get("LANG", "C"),
           "LC_ALL": os.environ.get("LC_ALL", "C"),
           "TZ": os.environ.get("TZ", "UTC")}
    if backend in ("seatbelt", "bubblewrap", "inherited"):
        env[kernel._JAILED] = "1"
    command = [sys.executable, entry, *args]
    if backend == "seatbelt":
        quoted = json.dumps(directory)
        profile = ("(version 1)\n(deny default)\n(allow file-read*)\n"
                   f"(allow file-write* (subpath {quoted}) (subpath \"/dev\"))\n"
                   "(allow process*)\n(allow sysctl*)\n(allow mach-lookup)\n")
        command = ["sandbox-exec", "-p", profile, *command]
    elif backend == "bubblewrap":
        command = ["bwrap", "--ro-bind", "/", "/", "--dev-bind", "/dev", "/dev",
                   "--proc", "/proc", "--proc", "--bind", directory, directory,
                   "--unshare-net", "--chdir", directory, *command]
    print(f'quarantine = "{backend}"', file=sys.stderr)
    try:
        return subprocess.run(command, cwd=directory, env=env, check=False).returncode
    except OSError as exc:
        print(f"cannot execute entrypoint: {exc}", file=sys.stderr)
        return 3


def _validated(directory: str) -> tuple[dict, list[tuple[str, str]]]:
    directory = os.path.abspath(directory)
    recipe = kernel.load_recipe(directory)
    outputs = _generated(directory, recipe)
    return recipe, outputs


def strip(directory: str) -> int:
    _, outputs = _validated(directory)
    for _, path in outputs:
        if os.path.lexists(path):
            if not os.path.isfile(path):
                raise NotRunnable(f"generated output is not a file: {path}")
            os.unlink(path)
    shutil.rmtree(os.path.join(directory, ".launcher"), ignore_errors=True)
    print("stripped generated outputs", file=sys.stderr)
    return 0


def _regrow(directory: str, outputs: list[tuple[str, str]], producer: str) -> None:
    with tempfile.TemporaryDirectory(prefix="reticuli-launcher-") as room:
        kernel.rebuild(directory, producer, room)
        for name, target in outputs:
            source = _path(room, name)
            if os.path.isfile(source):
                os.makedirs(os.path.dirname(target), exist_ok=True)
                shutil.copyfile(source, target)


def run(directory: str, args: list[str], accept: bool, signed_only: bool,
        no_sandbox: bool) -> int:
    directory = os.path.abspath(directory)
    recipe, outputs = _validated(directory)
    entry = _package(directory, recipe)
    checked = kernel.verify(directory)
    if not checked["ok"]:
        print("claim identity has drifted; inspect or strip", file=sys.stderr)
        return 6
    phase = _phase(directory)
    if signed_only and phase != "signed":
        print("--signed-only requires a signed claim", file=sys.stderr)
        return 5
    state = _state(directory)
    present = all(os.path.isfile(path) for _, path in outputs)
    if state.get("status") == "accepted" and present:
        if state.get("digest") != kernel.build_digest(directory):
            print("accepted build has drifted; strip to recover", file=sys.stderr)
            return 6
    if not present:
        producer = os.environ.get("RETICULI_PRODUCER")
        if not producer:
            print("latent claim: set RETICULI_PRODUCER to regrow it", file=sys.stderr)
            return 7
        _regrow(directory, outputs, producer)
        _save_state(directory, "fresh")
        state = _state(directory)
    if state.get("status") == "fresh" and state.get("digest") != kernel.build_digest(directory):
        print("generated build has drifted; strip to recover", file=sys.stderr)
        return 6
    if not kernel.audit(directory).get("ok"):
        print("build audit failed; strip to recover", file=sys.stderr)
        return 6
    if state.get("status") == "fresh":
        if not accept:
            print("fresh generated bytes require --accept-generated", file=sys.stderr)
            return 4
        _save_state(directory, "accepted")
    if not os.path.isfile(entry):
        print("entrypoint is missing", file=sys.stderr)
        return 3
    print(f"{phase} claim", file=sys.stderr)
    return _execution(directory, entry, args, no_sandbox)


def ls(directories: list[str]) -> int:
    for directory in directories:
        directory = os.path.abspath(directory)
        recipe, outputs = _validated(directory)
        manifest = kernel.read_manifest(directory)
        material = "materialized" if all(os.path.isfile(path) for _, path in outputs) else "latent"
        print(f"{recipe['claim']['name']}  {manifest['root'][:12]}  {_phase(directory)}  {material}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a latent Reticuli package",
        epilog="run flags: --accept-generated, --signed-only, --no-sandbox")
    commands = parser.add_subparsers(dest="verb", required=True)
    run_parser = commands.add_parser("run", help="audit and run a package")
    run_parser.add_argument("claim")
    run_parser.add_argument("--accept-generated", action="store_true")
    run_parser.add_argument("--signed-only", action="store_true")
    run_parser.add_argument("--no-sandbox", action="store_true")
    commands.add_parser("strip", help="remove generated bytes").add_argument("claim")
    commands.add_parser("ls", help="list claims").add_argument("claim", nargs="+")
    arguments, rest = parser.parse_known_args(argv)
    try:
        if arguments.verb == "run":
            if rest and rest[0] == "--":
                rest = rest[1:]
            return run(arguments.claim, rest, arguments.accept_generated,
                       arguments.signed_only, arguments.no_sandbox)
        if rest:
            parser.error("unexpected arguments: " + " ".join(rest))
        if arguments.verb == "strip":
            return strip(os.path.abspath(arguments.claim))
        return ls(arguments.claim)
    except (kernel.ClaimError, NotRunnable, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
