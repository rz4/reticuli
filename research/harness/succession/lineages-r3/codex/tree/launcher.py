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
from ._util import safe_path


STATE_DIR = ".launcher"
STATE_FILE = "state.json"


def _say(message: str) -> None:
    print(message, file=sys.stderr)


def _generated(directory: str, parsed: dict) -> list[str]:
    outputs = []
    for step in parsed.get("step", []):
        if (step["kind"] == "produce"
                and step.get("class", "generated") in ("generated", "free")
                and "from" not in step):
            # Validate every declared output before a caller changes anything.
            safe_path(directory, step["output"])
            outputs.append(step["output"])
    return outputs


def _claim(directory: str) -> tuple[dict, list[str]]:
    parsed = kernel.load_recipe(directory)
    return parsed, _generated(directory, parsed)


def _package(directory: str, parsed: dict) -> str:
    inputs = parsed["claim"].get("inputs", [])
    if "package.toml" not in inputs:
        raise kernel.ClaimError("package.toml must be a pinned input")
    path = safe_path(directory, "package.toml")
    try:
        with open(path, "rb") as stream:
            package = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise kernel.ClaimError(f"cannot read package.toml: {exc}") from exc
    entry = package.get("package", {}).get("entrypoint")
    if not isinstance(entry, str):
        raise kernel.ClaimError("package.toml needs [package] entrypoint")
    safe_path(directory, entry)
    return entry


def _digests(directory: str, outputs: list[str]) -> dict[str, str]:
    return {name: kernel._hash_file(safe_path(directory, name)) for name in outputs}


def _state_path(directory: str) -> str:
    return os.path.join(directory, STATE_DIR, STATE_FILE)


def _read_state(directory: str) -> dict | None:
    try:
        with open(_state_path(directory), encoding="utf-8") as stream:
            value = json.load(stream)
        if not isinstance(value, dict) or value.get("status") not in ("fresh", "accepted"):
            raise ValueError("invalid launcher state")
        return value
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        raise kernel.ClaimError(f"cannot read launcher state: {exc}") from exc


def _write_state(directory: str, status: str, digests: dict[str, str]) -> None:
    folder = os.path.join(directory, STATE_DIR)
    os.makedirs(folder, exist_ok=True)
    target = _state_path(directory)
    fd, temporary = tempfile.mkstemp(prefix=".state-", dir=folder, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({"status": status, "digests": digests}, stream, sort_keys=True)
            stream.write("\n")
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _checked(directory: str) -> bool:
    return kernel.verify(directory).get("ok") is True


def _audit(directory: str) -> bool:
    return kernel.audit(directory).get("ok") is True


def _quote_sb(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _execute(directory: str, entry: str, args: list[str], no_sandbox: bool) -> int:
    backend = "off" if no_sandbox else kernel.sandbox()[1]
    scratch = os.path.join(directory, kernel.STORE, "scratch")
    os.makedirs(scratch, exist_ok=True)
    environment = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL", "TZ")
                   if key in os.environ}
    environment.setdefault("PATH", os.defpath)
    environment.setdefault("LANG", "C.UTF-8")
    environment["HOME"] = scratch
    environment["TMPDIR"] = scratch
    if backend in ("seatbelt", "bubblewrap", "inherited"):
        environment[kernel._JAILED] = "1"
    command = [sys.executable, entry, *args]
    if backend == "seatbelt":
        profile = ("(version 1) (deny default) (allow process*) (allow file-read*) "
                   f"(allow file-write* (subpath {_quote_sb(directory)}))")
        command = ["sandbox-exec", "-p", profile, *command]
    elif backend == "bubblewrap":
        command = ["bwrap", "--ro-bind", "/", "/", "--dev-bind", "/dev", "/dev",
                   "--proc", "/proc", "--tmpfs", "/tmp", "--bind", directory,
                   directory, "--unshare-net", "--", *command]
    _say(f"sealed claim; quarantine = \"{backend}\"")
    try:
        return subprocess.run(command, cwd=directory, env=environment,
                              check=False).returncode
    except OSError as exc:
        _say(f"cannot execute entrypoint: {exc}")
        return 3


def invoke(directory: str, args: list[str], *, accept_generated: bool = False,
           signed_only: bool = False, no_sandbox: bool = False) -> int:
    directory = os.path.realpath(os.path.abspath(directory))
    try:
        parsed, outputs = _claim(directory)
        entry = _package(directory, parsed)
        if not _checked(directory):
            _say("claim identity mismatch; strip and restore the pinned claim")
            return 6
        if signed_only and kernel.phase(directory) != "signed":
            _say("signed claim required")
            return 5
        state = _read_state(directory)
        materialized = all(os.path.isfile(safe_path(directory, name)) for name in outputs)
        if state and state["status"] == "accepted":
            if not materialized or state.get("digests") != _digests(directory, outputs):
                _say("accepted build drifted; strip and regrow it")
                return 6
        if not materialized:
            producer = os.environ.get("RETICULI_PRODUCER")
            if not producer:
                _say("latent claim needs RETICULI_PRODUCER")
                return 7
            with tempfile.TemporaryDirectory(prefix="reticuli-launch-") as room:
                kernel.rebuild(directory, producer, room)
                if kernel.read_manifest(room)["root"] != kernel.read_manifest(directory)["root"]:
                    _say("regrown build has a different root; strip to recover")
                    return 6
                for name in outputs:
                    source = safe_path(room, name)
                    target = safe_path(directory, name)
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    shutil.copyfile(source, target)
            _write_state(directory, "fresh", _digests(directory, outputs))
            state = _read_state(directory)
        if state and state["status"] == "fresh":
            if state.get("digests") != _digests(directory, outputs):
                _say("fresh build drifted; strip and regrow it")
                return 6
            if not accept_generated:
                _say("newly generated bytes require --accept-generated")
                return 4
        if not _audit(directory):
            _say("build audit failed; strip and regrow it")
            return 6
        if state and state["status"] == "fresh":
            _write_state(directory, "accepted", _digests(directory, outputs))
        return _execute(directory, entry, args, no_sandbox)
    except (kernel.ClaimError, OSError, ValueError, KeyError) as exc:
        _say(str(exc))
        return 3


def strip(directory: str) -> int:
    directory = os.path.realpath(os.path.abspath(directory))
    try:
        _, outputs = _claim(directory)
        paths = [safe_path(directory, name) for name in outputs]
        for path in paths:
            if os.path.lexists(path):
                os.unlink(path)
        shutil.rmtree(os.path.join(directory, STATE_DIR), ignore_errors=True)
        _say("claim stripped to latency")
        return 0
    except (kernel.ClaimError, OSError, ValueError, KeyError) as exc:
        _say(str(exc))
        return 3


def ls(directories: list[str]) -> int:
    result = 0
    for given in directories:
        directory = os.path.realpath(os.path.abspath(given))
        try:
            parsed, outputs = _claim(directory)
            manifest = kernel.read_manifest(directory)
            phase = kernel.phase(directory)
            status = "materialized" if all(os.path.isfile(safe_path(directory, n)) for n in outputs) else "latent"
            print(f"{parsed['claim']['name']}  {manifest['root'][:12]}  {phase}  {status}  {given}")
        except (kernel.ClaimError, OSError, ValueError, KeyError) as exc:
            _say(f"{given}: {exc}")
            result = 3
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run and manage executable claims")
    sub = parser.add_subparsers(dest="verb", required=True)
    run_parser = sub.add_parser("run", help="run a claim")
    run_parser.add_argument("claim")
    run_parser.add_argument("--accept-generated", action="store_true")
    run_parser.add_argument("--signed-only", action="store_true")
    run_parser.add_argument("--no-sandbox", action="store_true")
    sub.add_parser("strip", help="remove generated bytes").add_argument("claim")
    sub.add_parser("ls", help="list claims").add_argument("claims", nargs="+")
    parser.epilog = "run flags: --accept-generated, --signed-only, --no-sandbox; use -- before entrypoint arguments"
    args, rest = parser.parse_known_args(argv)
    if args.verb == "run":
        if rest and rest[0] == "--":
            rest = rest[1:]
        return invoke(args.claim, rest, accept_generated=args.accept_generated,
                      signed_only=args.signed_only, no_sandbox=args.no_sandbox)
    if rest:
        parser.error("unexpected arguments: " + " ".join(rest))
    if args.verb == "strip":
        return strip(args.claim)
    return ls(args.claims)


if __name__ == "__main__":
    sys.exit(main())
