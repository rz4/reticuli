"""Run, list, and strip the generated implementation of a runnable claim."""

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
from ._kernel import core, recipe as recipe_tools, run as kernel_run


STATE = ".launcher/state.json"


class NotRunnable(Exception):
    pass


def _path(directory: str, name: str) -> str:
    try:
        return core._safe(directory, name)
    except kernel.ClaimError as exc:
        raise NotRunnable(str(exc)) from exc


def _claim(directory: str) -> tuple[dict, list[str]]:
    """Validate every recipe-derived path before an operation can mutate bytes."""
    try:
        parsed = kernel.load_recipe(directory)
        outputs = recipe_tools.generated_outputs(parsed)
        for step in parsed.get("step", []):
            _path(directory, step["output"])
        return parsed, outputs
    except kernel.ClaimError as exc:
        raise NotRunnable(str(exc)) from exc


def _package(directory: str, parsed: dict) -> str:
    inputs = recipe_tools._inputs(parsed, directory)
    if "package.toml" not in inputs:
        raise NotRunnable("package.toml must be a pinned input")
    if any(step["output"] == "package.toml" and
           step.get("class", "generated") == "generated"
           for step in parsed.get("step", [])):
        raise NotRunnable("package.toml must be a pinned input, not generated")
    path = _path(directory, "package.toml")
    try:
        with open(path, "rb") as stream:
            package = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise NotRunnable(f"cannot read package.toml: {exc}") from exc
    entry = package.get("package", {}).get("entrypoint")
    if not isinstance(entry, str):
        raise NotRunnable("package.toml needs a string entrypoint")
    return _path(directory, entry)


def _state(directory: str) -> dict:
    try:
        with open(os.path.join(directory, STATE), encoding="utf-8") as stream:
            data = json.load(stream)
        if isinstance(data, dict):
            return data
    except (OSError, ValueError):
        pass
    return {}


def _save_state(directory: str, data: dict) -> None:
    path = os.path.join(directory, STATE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(data, stream, sort_keys=True)
        stream.write("\n")


def _present(directory: str, outputs: list[str]) -> bool:
    return all(os.path.isfile(_path(directory, name)) for name in outputs)


def _hashes(directory: str, outputs: list[str]) -> dict[str, str]:
    return {name: kernel._hash_file(_path(directory, name)) for name in outputs}


def _execute(directory: str, entry: str, args: list[str], no_sandbox: bool) -> int:
    backend = "off" if no_sandbox else kernel_run.sandbox_backend()
    scratch = os.path.join(directory, ".launcher", "scratch")
    os.makedirs(scratch, exist_ok=True)
    env = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "TZ")
           if key in os.environ}
    env.setdefault("PATH", os.defpath)
    env["HOME"] = scratch
    env["TMPDIR"] = scratch
    if backend in ("seatbelt", "bubblewrap", "inherited"):
        env[kernel._JAILED] = "1"
    print(f'quarantine = "{backend}"', file=sys.stderr)
    argv = [sys.executable, "-B", entry, *args]
    if backend in ("seatbelt", "bubblewrap"):
        command = shlex.join(argv)
        argv = kernel_run._sandbox_argv(command, directory, backend, scratch)
    try:
        return subprocess.run(argv, cwd=directory, env=env, check=False).returncode
    except OSError as exc:
        print(f"entrypoint could not run: {exc}", file=sys.stderr)
        return 3


def run_claim(directory: str, *, accept_generated: bool = False,
              signed_only: bool = False, no_sandbox: bool = False,
              args: list[str] | None = None) -> int:
    directory = os.path.abspath(directory)
    try:
        parsed, outputs = _claim(directory)
        entry = _package(directory, parsed)
        verified = kernel.verify(directory)
        if not verified["ok"]:
            print("claim identity drifted; strip and reseal if intended", file=sys.stderr)
            return 6
        phase = kernel.phase(directory)
        if signed_only and phase != "signed":
            print("signed claim required", file=sys.stderr)
            return 5
        state = _state(directory)
        if not _present(directory, outputs):
            producer = os.environ.get("RETICULI_PRODUCER")
            if not producer:
                print("latent claim: set RETICULI_PRODUCER to regrow it", file=sys.stderr)
                return 7
            with tempfile.TemporaryDirectory(prefix="reticuli-launch-") as room:
                try:
                    kernel.rebuild(directory, producer, room)
                    for name in outputs:
                        source = _path(room, name)
                        target = _path(directory, name)
                        os.makedirs(os.path.dirname(target), exist_ok=True)
                        shutil.copyfile(source, target)
                except (kernel.ClaimError, OSError) as exc:
                    print(f"rebuild failed: {exc}", file=sys.stderr)
                    return 6
            state = {"status": "fresh", "hashes": _hashes(directory, outputs)}
            _save_state(directory, state)
        else:
            accepted = state.get("status") == "accepted"
            if accepted and state.get("hashes") != _hashes(directory, outputs):
                print("accepted build drifted; strip to recover", file=sys.stderr)
                return 6
        audited = kernel.audit(directory)
        if not audited.get("ok"):
            print("build audit failed; strip to recover", file=sys.stderr)
            return 6
        if state.get("status") == "fresh":
            if not accept_generated:
                print("newly generated bytes require --accept-generated", file=sys.stderr)
                return 4
            _save_state(directory, {"status": "accepted", "hashes": _hashes(directory, outputs)})
        print(f"{phase} claim: {parsed['claim']['name']}", file=sys.stderr)
        return _execute(directory, entry, args or [], no_sandbox)
    except (NotRunnable, kernel.ClaimError, OSError) as exc:
        print(f"not runnable: {exc}", file=sys.stderr)
        return 3


def strip_claim(directory: str) -> int:
    directory = os.path.abspath(directory)
    try:
        _, outputs = _claim(directory)
        for name in outputs:
            path = _path(directory, name)
            if os.path.isfile(path):
                os.unlink(path)
        shutil.rmtree(os.path.join(directory, ".launcher"), ignore_errors=True)
        return 0
    except (NotRunnable, OSError) as exc:
        print(f"not runnable: {exc}", file=sys.stderr)
        return 3


def list_claims(directories: list[str]) -> int:
    result = 0
    for directory in directories:
        directory = os.path.abspath(directory)
        try:
            parsed, outputs = _claim(directory)
            manifest = kernel.read_manifest(directory)
            phase = kernel.phase(directory)
            present = "materialized" if _present(directory, outputs) else "latent"
            print(f"{parsed['claim']['name']} {manifest['root'][:12]} {phase} {present}")
        except (NotRunnable, kernel.ClaimError, OSError) as exc:
            print(f"cannot list {directory}: {exc}", file=sys.stderr)
            result = 3
    return result


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    forwarded = []
    if argv[:1] == ["run"] and "--" in argv:
        marker = argv.index("--")
        forwarded = argv[marker + 1:]
        argv = argv[:marker]
    parser = argparse.ArgumentParser(
        description="Run content-addressed packages",
        epilog="run flags: --accept-generated --signed-only --no-sandbox")
    sub = parser.add_subparsers(dest="verb", required=True)
    run_parser = sub.add_parser("run", help="execute a package")
    run_parser.add_argument("claim")
    run_parser.add_argument("--accept-generated", action="store_true")
    run_parser.add_argument("--signed-only", action="store_true")
    run_parser.add_argument("--no-sandbox", action="store_true")
    strip_parser = sub.add_parser("strip", help="remove generated bytes")
    strip_parser.add_argument("claim")
    list_parser = sub.add_parser("ls", help="list claims")
    list_parser.add_argument("claims", nargs="+")
    ns = parser.parse_args(argv)
    if ns.verb == "run":
        return run_claim(ns.claim, accept_generated=ns.accept_generated,
                         signed_only=ns.signed_only, no_sandbox=ns.no_sandbox,
                         args=forwarded)
    if ns.verb == "strip":
        return strip_claim(ns.claim)
    return list_claims(ns.claims)


if __name__ == "__main__":
    sys.exit(main())
