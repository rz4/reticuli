"""Execute claim gates and record measured work."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import venv
from pathlib import Path

from . import core, recipe as recipe_module


_REQ_OPS = ('<=', '>=', '==', '!=', '~=', '<', '>')
_BWRAP_OK = None
_SEATBELT_OK = None


def _have(name: str) -> bool:
    return shutil.which(name) is not None


def _quote_sb(value: str) -> str:
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def _bwrap_usable() -> bool:
    global _BWRAP_OK
    if _BWRAP_OK is None:
        if not _have('bwrap'):
            _BWRAP_OK = False
        else:
            try:
                result = subprocess.run(
                    ['bwrap', '--ro-bind', '/', '/', '--dev-bind', '/dev', '/dev',
                     '--proc', '/proc', '--', '/bin/sh', '-c', 'true'],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
                _BWRAP_OK = result.returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                _BWRAP_OK = False
    return _BWRAP_OK


def _seatbelt_usable() -> bool:
    global _SEATBELT_OK
    if _SEATBELT_OK is None:
        if not _have('sandbox-exec'):
            _SEATBELT_OK = False
        else:
            try:
                result = subprocess.run(
                    ['sandbox-exec', '-p', '(version 1)(allow default)',
                     '/bin/sh', '-c', 'true'],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
                _SEATBELT_OK = result.returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                _SEATBELT_OK = False
    return _SEATBELT_OK


def sandbox_backend() -> str:
    if os.environ.get(core._JAILED):
        return 'inherited'
    if sys.platform == 'darwin' and _seatbelt_usable():
        return 'seatbelt'
    if sys.platform.startswith('linux') and _bwrap_usable():
        return 'bubblewrap'
    return 'none'


def sandbox() -> dict:
    return {'backend': sandbox_backend()}


def _sandbox_argv(command: str, directory: str, backend: str) -> list[str]:
    shell = [core._SHELL, '-c', command]
    if backend == 'seatbelt':
        base = os.path.realpath(directory)
        profile = ('(version 1) (allow default) '
                   '(deny network*) '
                   '(deny file-write* (subpath "/")) '
                   f'(allow file-write* (subpath {_quote_sb(base)})) '
                   '(allow file-write* (subpath "/dev"))')
        return ['sandbox-exec', '-p', profile, *shell]
    if backend == 'bubblewrap':
        base = os.path.realpath(directory)
        return ['bwrap', '--ro-bind', '/', '/', '--dev-bind', '/dev', '/dev',
                '--proc', '/proc', '--bind', base, base, '--chdir', base,
                '--unshare-net', '--', *shell]
    return shell


def _scrub_env(directory: str, backend: str) -> dict[str, str]:
    env = {name: os.environ[name] for name in core._KEEP_ENV if name in os.environ}
    if backend in ('seatbelt', 'bubblewrap'):
        scratch = os.path.join(directory, core.STORE, 'tmp')
        os.makedirs(scratch, exist_ok=True)
        env['HOME'] = scratch
        env['TMPDIR'] = scratch
        env[core._JAILED] = '1'
    return env


def _kill_tree(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except OSError:
        process.kill()
    process.communicate()


def _run(argv: list[str], directory: str, env: dict[str, str], timeout: float) -> dict:
    started = time.monotonic()
    try:
        process = subprocess.Popen(argv, cwd=directory, env=env,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=True)
        try:
            stdout, stderr = process.communicate(timeout=timeout)
            status = 'ok' if process.returncode == 0 else 'failed'
        except subprocess.TimeoutExpired:
            _kill_tree(process)
            stdout, stderr = b'', b''
            status = 'timeout'
        return {'status': status, 'returncode': process.returncode,
                'stdout': stdout.decode('utf-8', 'replace'),
                'stderr': stderr.decode('utf-8', 'replace'),
                'seconds': time.monotonic() - started}
    except OSError as exc:
        return {'status': 'failed', 'returncode': None, 'stdout': '',
                'stderr': str(exc), 'seconds': time.monotonic() - started}


def gate_timeout(claim: dict | None = None) -> float:
    declaration = (claim or {}).get('claim', {}).get('gate_timeout')
    if declaration is not None:
        if isinstance(declaration, bool) or not isinstance(declaration, (int, float)) or declaration <= 0:
            raise core.ClaimError('gate_timeout must be a positive number')
        return float(declaration) if isinstance(declaration, float) else declaration
    candidate = os.environ.get(core._ENV_TIMEOUT)
    if candidate:
        try:
            return float(candidate)
        except ValueError as exc:
            raise core.ClaimError('invalid gate timeout') from exc
    return core.GATE_TIMEOUT


def run_gate(command: str, directory: str, claim: dict | None = None) -> dict:
    backend = sandbox_backend()
    result = _run(_sandbox_argv(command, directory, backend), directory,
                  _scrub_env(directory, backend), gate_timeout(claim))
    result['quarantine'] = backend
    return result


def _ledger_path(directory: str) -> str:
    return os.path.join(directory, core.LEDGER)


def ledger(directory: str, event: dict) -> None:
    path = _ledger_path(directory)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'a', encoding='utf-8') as output:
        output.write(json.dumps(event, sort_keys=True, allow_nan=False) + '\n')


def ledger_events(directory: str) -> list[dict]:
    try:
        with open(_ledger_path(directory), encoding='utf-8') as source:
            return [json.loads(line) for line in source if line.strip()]
    except FileNotFoundError:
        return []


def cost(directory: str) -> dict | None:
    totals: dict[str, float | int] = {}
    for event in ledger_events(directory):
        for key in core.COST_KEYS:
            value = event.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
                totals[key] = totals.get(key, 0) + value
    return totals or None


def _version_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r'\d+', value))


def _version_ok(actual: str, requirement: str) -> bool:
    for op in _REQ_OPS:
        if requirement.startswith(op):
            target = _version_tuple(requirement[len(op):])
            found = _version_tuple(actual)
            return {'<=': found <= target, '>=': found >= target,
                    '==': found == target, '!=': found != target,
                    '<': found < target, '>': found > target,
                    '~=': found >= target and found[:1] == target[:1]}[op]
    return True


def _tool_version(name: str) -> str | None:
    if not _have(name):
        return None
    try:
        result = subprocess.run([name, '--version'], capture_output=True,
                                text=True, timeout=5)
        return (result.stdout or result.stderr).strip().splitlines()[0]
    except (OSError, subprocess.TimeoutExpired, IndexError):
        return None


def preflight(claim: dict) -> list[str]:
    missing = []
    for requirement in claim.get('claim', {}).get('requires', []):
        name = re.split(r'[<>=!~]', requirement, 1)[0]
        if not _have(name) and importlib.util.find_spec(name) is None:
            missing.append(requirement)
    return missing


def _env_cache_dir() -> str:
    return os.environ.get(core._ENV_CACHE, os.path.join(tempfile.gettempdir(), 'reticuli-envs'))


def furnish(directory: str, claim: dict | None = None) -> str | None:
    claim = claim or recipe_module.load_recipe(directory)
    name = claim.get('claim', {}).get('environment')
    if not name:
        return None
    digest = core._hash_file(core._safe(directory, name))
    destination = os.path.join(_env_cache_dir(), digest + '-' + sys.implementation.cache_tag)
    if not os.path.isfile(os.path.join(destination, 'pyvenv.cfg')):
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        venv.EnvBuilder(with_pip=True).create(destination)
        pip = os.path.join(destination, 'bin', 'pip')
        subprocess.run([pip, 'install', '--require-hashes', '--only-binary=:all:',
                        '-r', core._safe(directory, name)], check=True,
                       timeout=core.FURNISH_TIMEOUT)
    return destination


def _in_band(first: dict | None, second: dict | None, tolerance: float = core.TOLERANCE) -> dict:
    first, second = first or {}, second or {}
    for unit in core.COST_LADDER:
        if unit in first and unit in second:
            a, b = first[unit], second[unit]
            return {'unit': unit, 'ok': b <= a * tolerance if a else b == 0,
                    'original': a, 'rebuild': b}
    return {'unit': None, 'ok': None}


def _independence_line(original: dict, rebuilt: dict) -> str:
    a = original.get('vendor')
    b = rebuilt.get('vendor')
    return 'unestablished' if not a or not b or a == b else 'declared'


def independence(original: dict, rebuilt: dict) -> dict:
    return {'status': _independence_line(original, rebuilt),
            'original': original, 'rebuild': rebuilt}
