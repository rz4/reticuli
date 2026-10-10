"""Execute a package carried by a Reticuli claim."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib

from . import kernel
from ._util import declared_inputs, safe_path


STATE = ".launcher"
FRESH = "fresh.json"
ACCEPTED = "accepted.json"


class NotRunnable(Exception):
    pass


def _inside(directory: str, name: str) -> str:
    """Confine every recipe or package path before touching the filesystem."""
    try:
        return safe_path(directory, name)
    except (kernel.ClaimError, ValueError) as exc:
        raise NotRunnable(str(exc)) from exc


def _recipe(directory: str) -> dict:
    try:
        parsed = kernel.load_recipe(directory)
        for step in parsed.get("step", []):
            _inside(directory, step["output"])
        return parsed
    except (kernel.ClaimError, KeyError, TypeError) as exc:
        raise NotRunnable(str(exc)) from exc


def _generated(directory: str, parsed: dict) -> list[str]:
    return [step["output"] for step in parsed.get("step", [])
            if step["kind"] == "produce"
            and step.get("class", "generated") in ("generated", "free")
            and "from" not in step]


def _package(directory: str, parsed: dict) -> str:
    try:
        inputs = declared_inputs(parsed, directory)
    except kernel.ClaimError as exc:
        raise NotRunnable(str(exc)) from exc
    if "package.toml" not in inputs:
        raise NotRunnable("package.toml must be a pinned input")
    path = _inside(directory, "package.toml")
    try:
        with open(path, "rb") as stream:
            package = tomllib.load(stream)
        entry = package["package"]["entrypoint"]
    except (OSError, tomllib.TOMLDecodeError, KeyError, TypeError) as exc:
        raise NotRunnable(f"invalid package.toml: {exc}") from exc
    return _inside(directory, entry)


def _state_path(directory: str, name: str) -> str:
    return os.path.join(directory, STATE, name)


def _read_state(directory: str, name: str) -> dict | None:
    try:
        with open(_state_path(directory, name), encoding="utf-8") as stream:
            data = json.load(stream)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _write_state(directory: str, name: str, digest: str) -> None:
    folder = os.path.join(directory, STATE)
    os.makedirs(folder, exist_ok=True)
    target = _state_path(directory, name)
    with open(target, "w", encoding="utf-8") as stream:
        json.dump({"build_digest": digest}, stream)
        stream.write("\n")


def _backend() -> str:
    if os.environ.get(kernel._JAILED):
        return "inherited"
    if sys.platform == "darwin" and shutil.which("sandbox-exec"):
        return "seatbelt"
    if sys.platform.startswith("linux") and shutil.which("bwrap"):
        try:
            probe = subprocess.run(["bwrap", "--ro-bind", "/", "/",
                                    "--unshare-net", "true"],
                                   stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, timeout=5)
            if probe.returncode == 0:
                return "bubblewrap"
        except (OSError, subprocess.TimeoutExpired):
            pass
    return "none"


def _execute(directory: str, entry: str, args: list[str], no_sandbox: bool) -> int:
    backend = "off" if no_sandbox else _backend()
    scratch = os.path.join(directory, STATE, "scratch")
    os.makedirs(scratch, exist_ok=True)
    env = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL", "TZ")
           if key in os.environ}
    env.setdefault("PATH", os.defpath)
    env["HOME"] = scratch
    env["TMPDIR"] = scratch
    if backend in ("seatbelt", "bubblewrap", "inherited"):
        env[kernel._JAILED] = "1"
    command = [sys.executable, entry, *args]
    if backend == "seatbelt":
        profile = ('(version 1) (deny default) (allow file-read*) '
                   '(allow process*) (allow sysctl-read) (allow mach-lookup) '
                   f'(allow file-write* (subpath {json.dumps(directory)})) '
                   '(allow file-write* (literal "/dev/null"))')
        command = ["sandbox-exec", "-p", profile, *command]
    elif backend == "bubblewrap":
        command = ["bwrap", "--ro-bind", "/", "/", "--dev-bind", "/dev", "/dev",
                   "--proc", "/proc", "--bind", directory, directory,
                   "--chdir", directory, "--unshare-net", "--", *command]
    print(f'quarantine = "{backend}"', file=sys.stderr)
    try:
        return subprocess.run(command, cwd=directory, env=env, check=False).returncode
    except OSError as exc:
        print(f"cannot execute entrypoint: {exc}", file=sys.stderr)
        return 3


def _run(directory: str, accept: bool, signed_only: bool,
         no_sandbox: bool, args: list[str]) -> int:
    parsed = _recipe(directory)
    entry = _package(directory, parsed)
    try:
        verified = kernel.verify(directory)
        if not verified["ok"]:
            raise NotRunnable("claim identity mismatch")
        phase = kernel.phase(directory)
    except kernel.ClaimError as exc:
        raise NotRunnable(str(exc)) from exc
    if signed_only and phase != "signed":
        print("signed claim required", file=sys.stderr)
        return 5

    outputs = _generated(directory, parsed)
    missing = any(not os.path.isfile(_inside(directory, name)) for name in outputs)
    if missing:
        producer = os.environ.get("RETICULI_PRODUCER")
        if not producer:
            print("latent claim: set RETICULI_PRODUCER to regrow it", file=sys.stderr)
            return 7
        with tempfile.TemporaryDirectory(prefix="reticuli-launch-") as room:
            try:
                kernel.rebuild(directory, producer, room)
                for name in outputs:
                    source = _inside(room, name)
                    destination = _inside(directory, name)
                    os.makedirs(os.path.dirname(destination), exist_ok=True)
                    shutil.copyfile(source, destination)
            except (kernel.ClaimError, OSError) as exc:
                print(f"rebuild failed: {exc}", file=sys.stderr)
                return 6
        digest = kernel.build_digest(directory)
        _write_state(directory, FRESH, digest)

    digest = kernel.build_digest(directory)
    accepted = _read_state(directory, ACCEPTED)
    fresh = _read_state(directory, FRESH)
    if accepted and accepted.get("build_digest") != digest:
        print("accepted build drifted; strip to recover", file=sys.stderr)
        return 6
    if fresh and not accepted:
        if fresh.get("build_digest") != digest:
            print("fresh build drifted; strip to recover", file=sys.stderr)
            return 6
        if not accept:
            print("newly generated bytes require --accept-generated", file=sys.stderr)
            return 4

    try:
        audited = kernel.audit(directory)
    except kernel.ClaimError as exc:
        print(f"audit failed; strip to recover: {exc}", file=sys.stderr)
        return 6
    if not audited.get("ok"):
        print("audit failed; strip to recover", file=sys.stderr)
        return 6

    if fresh and not accepted:
        _write_state(directory, ACCEPTED, digest)
        os.unlink(_state_path(directory, FRESH))
    print(f"{phase} claim {parsed['claim']['name']}", file=sys.stderr)
    return _execute(directory, entry, args, no_sandbox)


def _strip(directory: str) -> int:
    parsed = _recipe(directory)
    for name in _generated(directory, parsed):
        path = _inside(directory, name)
        if os.path.lexists(path):
            if not os.path.isfile(path):
                raise NotRunnable(f"generated output is not a file: {name}")
            os.unlink(path)
    shutil.rmtree(os.path.join(directory, STATE), ignore_errors=True)
    return 0


def _ls(directories: list[str]) -> int:
    for directory in directories:
        parsed = _recipe(directory)
        manifest = kernel.read_manifest(directory)
        phase = kernel.phase(directory)
        generated = _generated(directory, parsed)
        presence = "materialized" if all(os.path.isfile(_inside(directory, x))
                                         for x in generated) else "latent"
        print(f"{manifest['name']} {manifest['root'][:12]} {phase} {presence} {directory}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run, strip, or list a claim package",
        epilog="run options: --accept-generated, --signed-only, --no-sandbox")
    sub = parser.add_subparsers(dest="verb", required=True)
    run_parser = sub.add_parser("run", help="execute an entrypoint")
    run_parser.add_argument("claim")
    run_parser.add_argument("--accept-generated", action="store_true")
    run_parser.add_argument("--signed-only", action="store_true")
    run_parser.add_argument("--no-sandbox", action="store_true")
    strip_parser = sub.add_parser("strip", help="remove generated outputs")
    strip_parser.add_argument("claim")
    ls_parser = sub.add_parser("ls", help="list claim status")
    ls_parser.add_argument("claims", nargs="+")
    args, trailing = parser.parse_known_args(argv)
    try:
        if args.verb == "run":
            if trailing and trailing[0] == "--":
                trailing = trailing[1:]
            return _run(os.path.abspath(args.claim), args.accept_generated,
                        args.signed_only, args.no_sandbox, trailing)
        if trailing:
            parser.error("unexpected arguments: " + " ".join(trailing))
        if args.verb == "strip":
            return _strip(os.path.abspath(args.claim))
        return _ls([os.path.abspath(path) for path in args.claims])
    except (NotRunnable, kernel.ClaimError, OSError) as exc:
        print(f"not runnable: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
