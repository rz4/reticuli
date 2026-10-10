"""Execute a packaged claim, regrowing its generated files when necessary."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib

from . import kernel


STATE = ".launcher"


class NotRunnable(Exception):
    pass


def _path(directory: str, name: str) -> str:
    """Confine a recipe or package path before touching the filesystem."""
    if not isinstance(name, str) or not name or os.path.isabs(name):
        raise NotRunnable(f"unsafe claim path: {name!r}")
    parts = name.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise NotRunnable(f"unsafe claim path: {name!r}")
    path = directory
    for part in parts:
        path = os.path.join(path, part)
        if os.path.islink(path):
            raise NotRunnable(f"symlink claim path: {name!r}")
    if os.path.commonpath((directory, os.path.abspath(path))) != directory:
        raise NotRunnable(f"claim path escapes directory: {name!r}")
    return path


def _recipe(directory: str) -> dict:
    parsed = kernel.load_recipe(directory)
    for name in parsed["claim"].get("inputs", []):
        _path(directory, name)
    for step in parsed.get("step", []):
        _path(directory, step["output"])
    return parsed


def _generated(parsed: dict) -> list[str]:
    return [step["output"] for step in parsed.get("step", [])
            if step["kind"] == "produce"
            and step.get("class", "generated") == "generated"
            and "from" not in step]


def _package(directory: str, parsed: dict) -> str:
    inputs = parsed["claim"].get("inputs", [])
    if "package.toml" not in inputs:
        raise NotRunnable("package.toml must be a pinned input")
    if any(step["output"] == "package.toml" and
           step.get("class", "generated") == "generated"
           for step in parsed.get("step", [])):
        raise NotRunnable("package.toml must be a pinned input")
    path = _path(directory, "package.toml")
    try:
        with open(path, "rb") as stream:
            package = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise NotRunnable(f"cannot read package.toml: {exc}") from exc
    entry = package.get("package", {}).get("entrypoint")
    return _path(directory, entry)


def _state_path(directory: str, name: str) -> str:
    return os.path.join(directory, STATE, name + ".json")


def _read_state(directory: str, name: str) -> str | None:
    try:
        with open(_state_path(directory, name), encoding="utf-8") as stream:
            value = json.load(stream)
        return value if isinstance(value, str) else None
    except (OSError, ValueError):
        return None


def _write_state(directory: str, name: str, digest: str) -> None:
    folder = os.path.join(directory, STATE)
    os.makedirs(folder, exist_ok=True)
    target = _state_path(directory, name)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=folder,
                                     delete=False) as stream:
        temporary = stream.name
        json.dump(digest, stream)
    os.replace(temporary, target)


def _sandbox() -> str:
    if os.environ.get(kernel._JAILED):
        return "inherited"
    if sys.platform == "darwin" and shutil.which("sandbox-exec"):
        return "seatbelt"
    if shutil.which("bwrap"):
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
    backend = "off" if no_sandbox else _sandbox()
    scratch = os.path.join(directory, STATE, "tmp")
    os.makedirs(scratch, exist_ok=True)
    env = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL", "TZ")
           if key in os.environ}
    env.setdefault("PATH", os.defpath)
    env.setdefault("LANG", "C")
    env.update(HOME=scratch, TMPDIR=scratch)
    if backend in ("seatbelt", "bubblewrap", "inherited"):
        env[kernel._JAILED] = "1"
    command = [sys.executable, entry, *args]
    if backend == "seatbelt":
        command = ["sandbox-exec", "-p",
                   "(version 1)(allow default)(deny network*)", *command]
    elif backend == "bubblewrap":
        command = ["bwrap", "--ro-bind", "/", "/",
                   "--bind", directory, directory,
                   "--dev-bind", "/dev", "/dev", "--proc", "/proc",
                   "--unshare-net", "--die-with-parent", "--chdir", directory,
                   "--", *command]
    print(f'quarantine = "{backend}"', file=sys.stderr)
    try:
        return subprocess.run(command, cwd=directory, env=env, check=False).returncode
    except OSError as exc:
        print(f"launcher: cannot execute entrypoint: {exc}", file=sys.stderr)
        return 3


def run(directory: str, args: list[str], *, accept_generated: bool = False,
        signed_only: bool = False, no_sandbox: bool = False) -> int:
    directory = os.path.abspath(directory)
    try:
        parsed = _recipe(directory)
        entry = _package(directory, parsed)
        verified = kernel.verify(directory)
        if not verified["ok"]:
            print("launcher: claim identity drift; strip and restore the claim",
                  file=sys.stderr)
            return 6
        phase = kernel.phase(directory)
        if signed_only and phase != "signed":
            print("launcher: signed claim required", file=sys.stderr)
            return 5
        generated = _generated(parsed)
        present = all(os.path.isfile(_path(directory, name)) for name in generated)
        accepted = _read_state(directory, "accepted")
        fresh = _read_state(directory, "fresh")
        if accepted is not None and present and kernel.build_digest(directory) != accepted:
            print("launcher: accepted build drifted; strip to recover", file=sys.stderr)
            return 6
        if not present:
            producer = os.environ.get("RETICULI_PRODUCER")
            if not producer:
                print("launcher: latent claim needs RETICULI_PRODUCER", file=sys.stderr)
                return 7
            with tempfile.TemporaryDirectory(prefix="reticuli-launch-") as room:
                result = kernel.rebuild(directory, producer, room)
                if not result["ok"]:
                    print("launcher: rebuild failed", file=sys.stderr)
                    return 6
                for name in generated:
                    source = _path(room, name)
                    target = _path(directory, name)
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    shutil.copyfile(source, target)
            fresh = kernel.build_digest(directory)
            _write_state(directory, "fresh", fresh)
        audit = kernel.audit(directory)
        if not audit["ok"]:
            print("launcher: build audit failed; strip to recover", file=sys.stderr)
            return 6
        digest = kernel.build_digest(directory)
        if fresh is not None and accepted != digest:
            if not accept_generated:
                print("launcher: fresh generated bytes need --accept-generated",
                      file=sys.stderr)
                return 4
            _write_state(directory, "accepted", digest)
        if not os.path.isfile(entry):
            print("launcher: package entrypoint is missing", file=sys.stderr)
            return 3
        print(f"launcher: {phase} {parsed['claim']['name']}", file=sys.stderr)
        return _execute(directory, entry, args, no_sandbox)
    except NotRunnable as exc:
        print(f"launcher: {exc}", file=sys.stderr)
        return 3
    except kernel.ClaimError as exc:
        print(f"launcher: {exc}", file=sys.stderr)
        return 3


def strip(directory: str) -> int:
    directory = os.path.abspath(directory)
    try:
        parsed = _recipe(directory)
        for name in _generated(parsed):
            path = _path(directory, name)
            if os.path.exists(path):
                os.unlink(path)
        shutil.rmtree(os.path.join(directory, STATE), ignore_errors=True)
        return 0
    except (NotRunnable, kernel.ClaimError, OSError) as exc:
        print(f"launcher: {exc}", file=sys.stderr)
        return 3


def ls(directories: list[str]) -> int:
    status = 0
    for directory in directories:
        directory = os.path.abspath(directory)
        try:
            parsed = _recipe(directory)
            manifest = kernel.read_manifest(directory)
            generated = _generated(parsed)
            availability = ("materialized" if all(os.path.isfile(_path(directory, n))
                                                   for n in generated) else "latent")
            print(f"{manifest['name']} {manifest['root'][:12]} "
                  f"{kernel.phase(directory)} {availability}")
        except (NotRunnable, kernel.ClaimError) as exc:
            print(f"launcher: {exc}", file=sys.stderr)
            status = 3
    return status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog="run options: --accept-generated --signed-only --no-sandbox")
    sub = parser.add_subparsers(dest="verb", required=True)
    run_parser = sub.add_parser("run", help="run a packaged claim")
    run_parser.add_argument("claim")
    run_parser.add_argument("--accept-generated", action="store_true")
    run_parser.add_argument("--signed-only", action="store_true")
    run_parser.add_argument("--no-sandbox", action="store_true")
    sub.add_parser("strip", help="remove generated bytes").add_argument("claim")
    sub.add_parser("ls", help="list claim state").add_argument("claims", nargs="+")
    argv = sys.argv[1:] if argv is None else argv
    entry_args = []
    if argv and argv[0] == "run" and "--" in argv:
        at = argv.index("--")
        entry_args = argv[at + 1:]
        argv = argv[:at]
    options = parser.parse_args(argv)
    if options.verb == "run":
        return run(options.claim, entry_args,
                   accept_generated=options.accept_generated,
                   signed_only=options.signed_only,
                   no_sandbox=options.no_sandbox)
    if options.verb == "strip":
        return strip(options.claim)
    return ls(options.claims)


if __name__ == "__main__":
    raise SystemExit(main())
