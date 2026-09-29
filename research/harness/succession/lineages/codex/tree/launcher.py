"""Run and retire implementations carried by sealed Reticuli claims."""

from __future__ import annotations

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


STATE_DIR = ".launcher"
STATE_FILE = "state.json"


class NotRunnable(Exception):
    pass


def _confined(root: str, name: str) -> str:
    """Resolve a recipe or package path without following filesystem aliases."""
    if not isinstance(name, str) or not name or os.path.isabs(name):
        raise NotRunnable(f"unsafe claim path: {name!r}")
    pieces = Path(name).parts
    if any(piece == ".." for piece in pieces):
        raise NotRunnable(f"unsafe claim path: {name!r}")
    base = os.path.realpath(root)
    path = base
    for piece in pieces:
        if piece in ("", "."):
            continue
        path = os.path.join(path, piece)
        if os.path.islink(path):
            raise NotRunnable(f"symlink in claim path: {name!r}")
    if path == base or os.path.commonpath((base, os.path.realpath(path))) != base:
        raise NotRunnable(f"unsafe claim path: {name!r}")
    return path


def _recipe(root: str) -> dict:
    try:
        recipe = kernel.load_recipe(root)
        for name in recipe["claim"].get("inputs", []):
            _confined(root, name)
        for step in recipe.get("step", []):
            _confined(root, step["output"])
        return recipe
    except (kernel.ClaimError, KeyError, TypeError, ValueError) as exc:
        raise NotRunnable(str(exc)) from exc


def _generated(recipe: dict) -> list[str]:
    return list(dict.fromkeys(step["output"] for step in recipe.get("step", [])
                              if step.get("kind") == "produce"
                              and step.get("class") == "generated"))


def _package(root: str, recipe: dict) -> str:
    inputs = recipe["claim"].get("inputs", [])
    if "package.toml" not in inputs:
        raise NotRunnable("package.toml must be a pinned input")
    path = _confined(root, "package.toml")
    try:
        with open(path, "rb") as source:
            package = tomllib.load(source)
        entry = package["package"]["entrypoint"]
    except (OSError, ValueError, KeyError, TypeError, tomllib.TOMLDecodeError) as exc:
        raise NotRunnable(f"invalid package.toml: {exc}") from exc
    target = _confined(root, entry)
    if not os.path.isfile(target):
        # A missing generated entrypoint is a legal latent state.
        if entry not in _generated(recipe):
            raise NotRunnable(f"entrypoint missing: {entry}")
    return entry


def _state_path(root: str) -> str:
    return os.path.join(root, STATE_DIR, STATE_FILE)


def _read_state(root: str) -> dict | None:
    try:
        with open(_state_path(root), encoding="utf-8") as source:
            state = json.load(source)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        raise NotRunnable(f"invalid launcher state: {exc}") from exc
    if not isinstance(state, dict) or state.get("status") not in ("fresh", "accepted"):
        raise NotRunnable("invalid launcher state")
    return state


def _write_state(root: str, status: str, digest: str) -> None:
    folder = os.path.join(root, STATE_DIR)
    os.makedirs(folder, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump({"status": status, "digest": digest}, output, sort_keys=True)
            output.write("\n")
        os.replace(temporary, _state_path(root))
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _audited(root: str) -> bool:
    try:
        return bool(kernel.audit(root).get("ok"))
    except (kernel.ClaimError, OSError, ValueError):
        return False


def _run_entrypoint(root: str, entry: str, args: list[str], no_sandbox: bool) -> int:
    scratch = os.path.join(root, STATE_DIR, "runtime")
    os.makedirs(scratch, exist_ok=True)
    command = shlex.join([sys.executable, entry, *args])
    if no_sandbox:
        argv, backend = ["/bin/sh", "-c", command], "off"
    else:
        argv, backend = kernel.sandbox(command, root)
    env = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL", "TZ")
           if key in os.environ}
    env.update({"HOME": scratch, "TMPDIR": scratch})
    if backend in ("seatbelt", "bubblewrap"):
        env[kernel._JAILED] = backend
    elif backend == "inherited" and os.environ.get(kernel._JAILED):
        env[kernel._JAILED] = os.environ[kernel._JAILED]
    print(f'quarantine = "{backend}"', file=sys.stderr)
    try:
        return subprocess.call(argv, cwd=root, env=env)
    except OSError as exc:
        print(f"entrypoint failed: {exc}", file=sys.stderr)
        return 3


def run(root: str, accept_generated: bool = False, signed_only: bool = False,
        no_sandbox: bool = False, args: list[str] | None = None) -> int:
    root = os.path.abspath(root)
    try:
        recipe = _recipe(root)
        entry = _package(root, recipe)
        verified = kernel.verify(root)
        if not verified.get("ok"):
            print("claim identity changed; nothing executed", file=sys.stderr)
            return 6
        generated = _generated(recipe)
        state = _read_state(root)
        current = kernel.build_digest(root)
        if state and state.get("digest") != current:
            print("build drifted; run strip to recover", file=sys.stderr)
            return 6
        if signed_only and kernel.phase(root) != "signed":
            print("signed claim required", file=sys.stderr)
            return 5

        missing = [name for name in generated if not os.path.isfile(_confined(root, name))]
        if missing:
            producer = os.environ.get("RETICULI_PRODUCER")
            if not producer:
                print("latent claim: RETICULI_PRODUCER is required", file=sys.stderr)
                return 7
            with tempfile.TemporaryDirectory(prefix="reticuli-launch-") as rebuilt:
                kernel.rebuild(root, producer, rebuilt)
                if kernel.read_manifest(rebuilt)["root"] != verified["root"]:
                    print("rebuilt claim has a different root", file=sys.stderr)
                    return 6
                for name in generated:
                    source = _confined(rebuilt, name)
                    target = _confined(root, name)
                    if not os.path.isfile(source):
                        print(f"producer omitted {name}", file=sys.stderr)
                        return 6
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    shutil.copyfile(source, target)
            current = kernel.build_digest(root)
            _write_state(root, "fresh", current)
            state = {"status": "fresh", "digest": current}

        if not _audited(root):
            print("build audit failed; run strip to recover", file=sys.stderr)
            return 6
        if state and state["status"] == "fresh":
            if not accept_generated:
                print("new generated bytes need --accept-generated", file=sys.stderr)
                return 4
            _write_state(root, "accepted", current)
        print(f"{kernel.phase(root)} claim {recipe['claim']['name']}", file=sys.stderr)
        return _run_entrypoint(root, entry, args or [], no_sandbox)
    except NotRunnable as exc:
        print(f"not runnable: {exc}", file=sys.stderr)
        return 3
    except (kernel.ClaimError, OSError, ValueError) as exc:
        print(f"claim failed: {exc}", file=sys.stderr)
        return 6


def strip(root: str) -> int:
    root = os.path.abspath(root)
    try:
        recipe = _recipe(root)
        for name in _generated(recipe):
            path = _confined(root, name)
            if os.path.lexists(path):
                if not os.path.isfile(path):
                    raise NotRunnable(f"generated output is not a file: {name}")
                os.unlink(path)
        shutil.rmtree(os.path.join(root, STATE_DIR), ignore_errors=True)
        return 0
    except (NotRunnable, kernel.ClaimError, OSError, ValueError) as exc:
        print(f"cannot strip: {exc}", file=sys.stderr)
        return 3


def ls(roots: list[str]) -> int:
    try:
        for root in roots:
            root = os.path.abspath(root)
            recipe = _recipe(root)
            manifest = kernel.read_manifest(root)
            available = all(os.path.isfile(_confined(root, name))
                            for name in _generated(recipe))
            print(f"{recipe['claim']['name']} {manifest['root'][:12]} "
                  f"{kernel.phase(root)} {'materialized' if available else 'latent'}")
        return 0
    except (NotRunnable, kernel.ClaimError, OSError, ValueError) as exc:
        print(f"cannot list: {exc}", file=sys.stderr)
        return 3


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    help_text = ("usage: python3 -m reticuli.launcher <run|strip|ls> ...\n"
                 "run <claim> [--accept-generated] [--signed-only] "
                 "[--no-sandbox] [-- args...]\n"
                 "strip <claim>\nls <claim>...")
    if not argv or argv[0] in ("-h", "--help"):
        print(help_text)
        return 0 if argv else 2
    verb = argv.pop(0)
    if verb == "run" and argv:
        root = argv.pop(0)
        flags = set()
        while argv and argv[0] != "--":
            flag = argv.pop(0)
            if flag not in ("--accept-generated", "--signed-only", "--no-sandbox"):
                print(f"unknown flag: {flag}", file=sys.stderr)
                return 2
            flags.add(flag)
        if argv and argv[0] == "--":
            argv.pop(0)
        return run(root, "--accept-generated" in flags,
                   "--signed-only" in flags, "--no-sandbox" in flags, argv)
    if verb == "strip" and len(argv) == 1:
        return strip(argv[0])
    if verb == "ls" and argv:
        return ls(argv)
    print(help_text, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
