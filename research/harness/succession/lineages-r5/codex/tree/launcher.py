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


class Refusal(Exception):
    def __init__(self, code: int, message: str):
        self.code = code
        super().__init__(message)


def _paths(directory: str, recipe: dict) -> list[str]:
    """Validate every recipe name before acting on any of them."""
    names = declared_inputs(recipe, directory)
    names.extend(step["output"] for step in recipe.get("step", []))
    for name in names:
        safe_path(directory, name)
    return names


def _claim(directory: str) -> tuple[str, dict]:
    directory = os.path.abspath(directory)
    recipe = kernel.load_recipe(directory)
    _paths(directory, recipe)
    if not kernel.verify(directory)["ok"]:
        raise Refusal(6, "claim identity has drifted; inspect it before running")
    return directory, recipe


def _generated(recipe: dict) -> list[str]:
    return [step["output"] for step in recipe.get("step", [])
            if step["kind"] == "produce"
            and step.get("class", "generated") == "generated"
            and "from" not in step]


def _state_path(directory: str) -> str:
    return os.path.join(directory, STATE, "state.json")


def _read_state(directory: str) -> dict:
    try:
        with open(_state_path(directory), encoding="utf-8") as stream:
            value = json.load(stream)
        if not isinstance(value, dict):
            raise ValueError("state is not an object")
        return value
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        raise Refusal(6, f"launcher state is damaged: {exc}; strip to recover") from exc


def _write_state(directory: str, status: str, digest: str) -> None:
    parent = os.path.join(directory, STATE)
    os.makedirs(parent, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="state-", dir=parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({"status": status, "digest": digest}, stream, sort_keys=True)
            stream.write("\n")
        os.replace(temporary, _state_path(directory))
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _package(directory: str, recipe: dict) -> str:
    if "package.toml" not in declared_inputs(recipe, directory):
        raise Refusal(3, "package.toml must be a pinned input")
    if any(step["output"] == "package.toml" for step in recipe.get("step", [])):
        raise Refusal(3, "package.toml must be a pinned input, not a step output")
    path = safe_path(directory, "package.toml")
    try:
        with open(path, "rb") as stream:
            package = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise Refusal(3, f"cannot read package.toml: {exc}") from exc
    entry = package.get("package", {}).get("entrypoint")
    if not isinstance(entry, str):
        raise Refusal(3, "package.toml needs a package entrypoint")
    return safe_path(directory, entry)


def _regrow(directory: str, recipe: dict, producer: str, outputs: list[str]) -> None:
    with tempfile.TemporaryDirectory(prefix="reticuli-launcher-") as room:
        kernel.rebuild(directory, producer, room)
        for name in outputs:
            source = safe_path(room, name)
            target = safe_path(directory, name)
            if not os.path.isfile(source):
                raise Refusal(6, f"producer omitted {name}")
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(source, target)
    if not kernel.verify(directory)["ok"] or not kernel.audit(directory)["ok"]:
        raise Refusal(6, "regrown build failed audit; strip to recover")
    _write_state(directory, "fresh", kernel.build_digest(directory))


def _environment(directory: str, backend: str) -> dict[str, str]:
    scratch = os.path.join(directory, STATE, "tmp")
    os.makedirs(scratch, exist_ok=True)
    env = {"PATH": os.environ.get("PATH", os.defpath),
           "HOME": scratch, "TMPDIR": scratch,
           "LANG": os.environ.get("LANG", "C"),
           "LC_ALL": os.environ.get("LC_ALL", "C")}
    if backend in ("seatbelt", "bubblewrap"):
        env[kernel._JAILED] = "1"
    elif backend == "inherited":
        env[kernel._JAILED] = os.environ.get(kernel._JAILED, "1")
    return env


def _execute(directory: str, entry: str, args: list[str], no_sandbox: bool) -> int:
    argv = [sys.executable, entry, *args]
    if no_sandbox:
        backend = "off"
        command = argv
    else:
        command, backend = kernel.sandbox(shlex.join(argv), directory)
    print(f'quarantine = "{backend}"', file=sys.stderr)
    try:
        return subprocess.run(command, cwd=directory,
                              env=_environment(directory, backend),
                              check=False).returncode
    except OSError as exc:
        raise Refusal(3, f"cannot launch entrypoint: {exc}") from exc


def run(directory: str, args: list[str], accept_generated: bool = False,
        signed_only: bool = False, no_sandbox: bool = False) -> int:
    directory, recipe = _claim(directory)
    entry = _package(directory, recipe)
    if signed_only and kernel.phase(directory) != "signed":
        raise Refusal(5, "claim is not signed to this verifier")
    outputs = _generated(recipe)
    state = _read_state(directory)
    materialized = all(os.path.isfile(safe_path(directory, name)) for name in outputs)
    if state.get("status") == "accepted":
        if not materialized or state.get("digest") != kernel.build_digest(directory):
            raise Refusal(6, "accepted build has drifted; strip to recover")
    elif state.get("status") == "fresh" and materialized:
        if state.get("digest") != kernel.build_digest(directory):
            raise Refusal(6, "fresh build has drifted; strip to recover")
    if not materialized:
        producer = os.environ.get("RETICULI_PRODUCER")
        if not producer:
            raise Refusal(7, "latent claim needs RETICULI_PRODUCER")
        _regrow(directory, recipe, producer, outputs)
        state = _read_state(directory)
    if not kernel.audit(directory)["ok"]:
        raise Refusal(6, "build audit failed; strip to recover")
    if state.get("status") == "fresh":
        if not accept_generated:
            raise Refusal(4, "newly generated bytes need --accept-generated before execution")
        _write_state(directory, "accepted", kernel.build_digest(directory))
    if not os.path.isfile(entry):
        raise Refusal(3, "package entrypoint is missing")
    print(f"{kernel.phase(directory)} claim: {recipe['claim']['name']}", file=sys.stderr)
    return _execute(directory, entry, args, no_sandbox)


def strip(directory: str) -> int:
    directory, recipe = _claim(directory)
    for name in _generated(recipe):
        path = safe_path(directory, name)
        if os.path.lexists(path):
            os.unlink(path)
    shutil.rmtree(os.path.join(directory, STATE), ignore_errors=True)
    return 0


def ls(directories: list[str]) -> int:
    for directory in directories:
        directory, recipe = _claim(directory)
        outputs = _generated(recipe)
        present = all(os.path.isfile(safe_path(directory, name)) for name in outputs)
        manifest = kernel.read_manifest(directory)
        print(f"{recipe['claim']['name']}  {manifest['root'][:12]}  "
              f"{kernel.phase(directory)}  {'materialized' if present else 'latent'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run executable Reticuli claims",
        epilog="run flags: --accept-generated, --signed-only, --no-sandbox")
    sub = parser.add_subparsers(dest="verb", required=True)
    running = sub.add_parser("run", help="run a package claim")
    running.add_argument("claim")
    running.add_argument("--accept-generated", action="store_true")
    running.add_argument("--signed-only", action="store_true")
    running.add_argument("--no-sandbox", action="store_true")
    sub.add_parser("strip", help="remove generated bytes").add_argument("claim")
    sub.add_parser("ls", help="list claim phases").add_argument("claims", nargs="+")
    words = list(sys.argv[1:] if argv is None else argv)
    passed = []
    if words[:1] == ["run"] and "--" in words:
        boundary = words.index("--")
        passed = words[boundary + 1:]
        words = words[:boundary]
    arguments = parser.parse_args(words)
    try:
        if arguments.verb == "run":
            return run(arguments.claim, passed, arguments.accept_generated,
                       arguments.signed_only, arguments.no_sandbox)
        if arguments.verb == "strip":
            return strip(arguments.claim)
        return ls(arguments.claims)
    except Refusal as exc:
        print(str(exc), file=sys.stderr)
        return exc.code
    except (kernel.ClaimError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
