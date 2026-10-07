"""Run, list, and strip executable Reticuli claims."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import tomllib

from . import kernel
from ._kernel import core, recipe, run as gate_run


class LauncherError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


def _paths(root: str, parsed: dict) -> list[str]:
    """Validate every declared path before any action can change the claim."""
    names = list(recipe._inputs(parsed, root))
    names.extend(step['output'] for step in parsed.get('step', []))
    for name in names:
        core._safe(root, name)
    return names


def _load(root: str) -> dict:
    try:
        parsed = kernel.load_recipe(root)
        _paths(root, parsed)
        return parsed
    except (kernel.ClaimError, OSError, ValueError) as exc:
        raise LauncherError(3, str(exc)) from exc


def _generated(parsed: dict) -> list[str]:
    return recipe.generated_outputs(parsed)


def _digest(root: str, names: list[str]) -> dict[str, str]:
    return {name: core._hash_file(core._safe(root, name)) for name in names}


def _state_path(root: str) -> str:
    return os.path.join(root, '.launcher', 'state.json')


def _state(root: str) -> dict:
    try:
        with open(_state_path(root), encoding='utf-8') as source:
            state = json.load(source)
        if isinstance(state, dict):
            return state
    except (OSError, ValueError):
        pass
    return {}


def _write_state(root: str, state: dict) -> None:
    path = _state_path(root)
    core._write_json(path, state)


def _package(root: str, parsed: dict) -> str:
    if 'package.toml' not in recipe._inputs(parsed, root):
        raise LauncherError(3, 'package.toml must be a pinned input')
    try:
        path = core._safe(root, 'package.toml')
        with open(path, 'rb') as source:
            package = tomllib.load(source)
        entry = package['package']['entrypoint']
        if not isinstance(entry, str):
            raise ValueError('entrypoint must be a path')
        core._safe(root, entry)
    except (OSError, ValueError, KeyError, TypeError, kernel.ClaimError) as exc:
        raise LauncherError(3, 'invalid package.toml entrypoint: ' + str(exc)) from exc
    return entry


def _checked(root: str) -> dict:
    try:
        checked = kernel.verify(root)
    except kernel.ClaimError as exc:
        raise LauncherError(6, 'claim verification failed; strip to recover: ' + str(exc)) from exc
    if not checked['ok']:
        raise LauncherError(6, 'claim identity drifted; strip to recover')
    return checked


def _audit(root: str) -> None:
    try:
        result = kernel.audit(root)
    except kernel.ClaimError as exc:
        raise LauncherError(6, 'build audit failed; strip to recover: ' + str(exc)) from exc
    if not result['ok']:
        raise LauncherError(6, 'build audit failed; strip to recover: ' + repr(result['gates']))


def _regrow(root: str, parsed: dict, producer: str) -> None:
    with tempfile.TemporaryDirectory(prefix='reticuli-launcher-') as room:
        try:
            kernel.rebuild(root, producer, room)
            for name in _generated(parsed):
                source = core._safe(room, name)
                target = core._safe(root, name)
                if not os.path.isfile(source):
                    raise kernel.ClaimError('producer omitted generated output: ' + name)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                shutil.copyfile(source, target)
        except (kernel.ClaimError, OSError) as exc:
            raise LauncherError(6, 'rebuild failed: ' + str(exc)) from exc
    _write_state(root, {'fresh': _digest(root, _generated(parsed))})


def _execution(root: str, entry: str, arguments: list[str], no_sandbox: bool) -> int:
    backend = 'off' if no_sandbox else gate_run.sandbox_backend()
    if not no_sandbox and backend == 'none' and sys.platform == 'darwin' \
            and shutil.which('sandbox-exec'):
        backend = 'seatbelt'
    scratch = os.path.join(root, '.launcher', 'tmp')
    os.makedirs(scratch, exist_ok=True)
    env = {key: os.environ[key] for key in ('PATH', 'LANG', 'LC_ALL', 'TZ') if key in os.environ}
    env.setdefault('PATH', os.defpath)
    env['HOME'] = scratch
    env['TMPDIR'] = scratch
    if backend in ('seatbelt', 'bubblewrap', 'inherited'):
        env[core._JAILED] = '1'
    command = [sys.executable, core._safe(root, entry), *arguments]
    if backend in ('seatbelt', 'bubblewrap'):
        argv = gate_run._sandbox_argv(shlex.join(command), root, backend)
    else:
        argv = command
    print(f'quarantine = "{backend}"', file=sys.stderr)
    try:
        return subprocess.run(argv, cwd=root, env=env, check=False).returncode
    except OSError as exc:
        raise LauncherError(3, 'cannot execute entrypoint: ' + str(exc)) from exc


def command_run(root: str, accept: bool, signed_only: bool,
                no_sandbox: bool, arguments: list[str]) -> int:
    root = os.path.realpath(root)
    parsed = _load(root)
    entry = _package(root, parsed)
    checked = _checked(root)
    phase = kernel.phase(root)
    if signed_only and phase != 'signed':
        raise LauncherError(5, 'claim is not signed to you')
    print(f'{phase} {checked["name"]} {checked["root"][:12]}', file=sys.stderr)
    names = _generated(parsed)
    state = _state(root)
    present = all(os.path.isfile(core._safe(root, name)) for name in names)
    if not present:
        producer = os.environ.get('RETICULI_PRODUCER')
        if not producer:
            raise LauncherError(7, 'latent build: set RETICULI_PRODUCER to regrow it')
        _regrow(root, parsed, producer)
        state = _state(root)
    digests = _digest(root, names)
    if 'accepted' in state and state['accepted'] != digests:
        raise LauncherError(6, 'accepted build bytes drifted; strip to recover')
    if 'fresh' in state and state['fresh'] != digests:
        raise LauncherError(6, 'fresh build bytes drifted; strip to recover')
    _audit(root)
    if 'fresh' in state:
        if not accept:
            raise LauncherError(4, 'new generated bytes require --accept-generated')
        _write_state(root, {'accepted': digests})
    return _execution(root, entry, arguments, no_sandbox)


def command_strip(root: str) -> int:
    root = os.path.realpath(root)
    parsed = _load(root)
    for name in _generated(parsed):
        path = core._safe(root, name)
        if os.path.exists(path):
            os.unlink(path)
    shutil.rmtree(os.path.join(root, '.launcher'), ignore_errors=True)
    print('stripped generated outputs', file=sys.stderr)
    return 0


def command_ls(roots: list[str]) -> int:
    for claim in roots:
        root = os.path.realpath(claim)
        parsed = _load(root)
        checked = _checked(root)
        phase = kernel.phase(root)
        material = ('materialized' if all(os.path.isfile(core._safe(root, name))
                                         for name in _generated(parsed)) else 'latent')
        print(f'{checked["name"]} {checked["root"][:12]} {phase} {material} {claim}')
    return 0


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    forwarded = []
    if raw[:1] == ['run'] and '--' in raw:
        boundary = raw.index('--')
        forwarded = raw[boundary + 1:]
        raw = raw[:boundary]
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog='run options: --accept-generated, --signed-only, --no-sandbox; '
               'put entrypoint arguments after --')
    sub = parser.add_subparsers(dest='verb', required=True)
    execute = sub.add_parser('run', help='run a claim entrypoint')
    execute.add_argument('claim')
    execute.add_argument('--accept-generated', action='store_true')
    execute.add_argument('--signed-only', action='store_true')
    execute.add_argument('--no-sandbox', action='store_true')
    strip = sub.add_parser('strip', help='delete generated outputs')
    strip.add_argument('claim')
    listing = sub.add_parser('ls', help='list claim identities and build state')
    listing.add_argument('claims', nargs='+')
    args = parser.parse_args(raw)
    try:
        if args.verb == 'run':
            return command_run(args.claim, args.accept_generated, args.signed_only,
                               args.no_sandbox, forwarded)
        if args.verb == 'strip':
            return command_strip(args.claim)
        return command_ls(args.claims)
    except LauncherError as exc:
        print(str(exc), file=sys.stderr)
        return exc.code


if __name__ == '__main__':
    raise SystemExit(main())
