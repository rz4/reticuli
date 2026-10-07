"""Run claim gates in a bounded, scrubbed environment and record their cost."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import venv
from pathlib import Path

from . import core


_REQ_OPS = ('<=', '>=', '==', '!=', '~=', '<', '>')
_BWRAP_OK = None


def _have(name):
    return shutil.which(name) is not None


def _version_tuple(value):
    return tuple(int(part) for part in re.findall(r'\d+', str(value)))


def _tool_version(name):
    try:
        result = subprocess.run([name, '--version'], capture_output=True,
                                text=True, timeout=5, check=False)
        return (result.stdout or result.stderr).strip().splitlines()[0]
    except (OSError, IndexError, subprocess.TimeoutExpired):
        return ''


def _version_ok(actual, requirement):
    """Evaluate a simple version constraint against a version string."""
    if not requirement:
        return True
    for op in _REQ_OPS:
        if requirement.startswith(op):
            wanted = _version_tuple(requirement[len(op):])
            got = _version_tuple(actual)
            if op == '~=':
                return got >= wanted and got[:1] == wanted[:1]
            return {'<=': got <= wanted, '>=': got >= wanted,
                    '==': got == wanted, '!=': got != wanted,
                    '<': got < wanted, '>': got > wanted}[op]
    return _version_tuple(actual) == _version_tuple(requirement)


def preflight(recipe):
    """List requirements unavailable on this host."""
    missing = []
    for requirement in recipe.get('claim', {}).get('requires', []):
        name = re.split(r'\s*(?:<=|>=|==|!=|~=|<|>)\s*', requirement, 1)[0]
        if not _have(name) and importlib.util.find_spec(name) is None:
            missing.append(requirement)
    return missing


def gate_timeout(recipe=None):
    declared = (recipe or {}).get('claim', {}).get('gate_timeout')
    ceiling = float(declared) if declared is not None else core.GATE_TIMEOUT
    host = os.environ.get(core._ENV_TIMEOUT)
    if host:
        ceiling = min(ceiling, float(host))
    if ceiling <= 0:
        raise core.ClaimError('gate timeout must be positive')
    return ceiling


def _quote_sb(value):
    return json.dumps(os.path.realpath(os.fspath(value)))


def _seatbelt_profile(directory):
    room = _quote_sb(directory)
    return ('(version 1)\n'
            '(deny default)\n'
            '(allow file-read*)\n'
            '(allow process*)\n'
            '(allow sysctl-read)\n'
            '(allow mach-lookup)\n'
            '(allow ipc-posix*)\n'
            f'(allow file-write* (subpath {room}) (literal "/dev/null") '
            '(literal "/dev/tty"))\n')


def _bwrap_usable():
    global _BWRAP_OK
    if _BWRAP_OK is None:
        if not _have('bwrap'):
            _BWRAP_OK = False
        else:
            try:
                probe = subprocess.run(['bwrap', '--ro-bind', '/', '/',
                                        '--unshare-net', '--', '/bin/true'],
                                       capture_output=True, timeout=5)
                _BWRAP_OK = probe.returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                _BWRAP_OK = False
    return _BWRAP_OK


def sandbox_backend():
    if os.environ.get(core._JAILED):
        return 'inherited'
    if sys.platform == 'darwin' and _have('sandbox-exec'):
        try:
            with tempfile.TemporaryDirectory() as room:
                probe = subprocess.run(['sandbox-exec', '-p',
                                        _seatbelt_profile(room), '/bin/true'],
                                       capture_output=True, timeout=5)
                if probe.returncode == 0:
                    return 'seatbelt'
        except (OSError, subprocess.TimeoutExpired):
            pass
    if sys.platform.startswith('linux') and _bwrap_usable():
        return 'bubblewrap'
    return 'none'


def sandbox():
    return {'backend': sandbox_backend()}


def _sandbox_argv(command, directory, backend=None):
    backend = backend or sandbox_backend()
    shell = [core._SHELL, '-c', command]
    if backend == 'seatbelt':
        return ['sandbox-exec', '-p', _seatbelt_profile(directory), *shell]
    if backend == 'bubblewrap':
        room = os.path.realpath(directory)
        return ['bwrap', '--ro-bind', '/', '/', '--bind', room, room,
                '--dev-bind', '/dev', '/dev', '--proc', '/proc',
                '--unshare-net', '--chdir', room, '--', *shell]
    return shell


def _scrub_env(directory, backend='none', extra=None):
    env = {key: os.environ[key] for key in core._KEEP_ENV if key in os.environ}
    env.setdefault('PATH', os.defpath)
    if backend in ('seatbelt', 'bubblewrap'):
        scratch = os.path.join(os.path.realpath(directory), core.STORE, 'tmp')
        os.makedirs(scratch, exist_ok=True)
        env['HOME'] = scratch
        env['TMPDIR'] = scratch
        env[core._JAILED] = '1'
    if extra:
        env.update(extra)
    return env


def _kill_tree(process):
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _run(argv, directory, env, timeout):
    started = time.monotonic()
    process = subprocess.Popen(argv, cwd=directory, env=env,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
        status = 'ok' if process.returncode == 0 else 'failed'
    except subprocess.TimeoutExpired:
        _kill_tree(process)
        stdout, stderr = process.communicate()
        status = 'timeout'
    return {'status': status, 'returncode': process.returncode,
            'stdout': stdout, 'stderr': stderr,
            'seconds': time.monotonic() - started}


def run_gate(command, directory, recipe=None):
    """Execute a shell gate with confinement when the host supports it."""
    missing = preflight(recipe or {})
    if missing:
        return {'status': 'environment', 'quarantine': sandbox_backend(),
                'missing': missing}
    backend = sandbox_backend()
    env = _scrub_env(directory, backend)
    try:
        result = _run(_sandbox_argv(command, directory, backend), directory,
                      env, gate_timeout(recipe))
    except OSError as exc:
        return {'status': 'environment', 'quarantine': backend,
                'error': str(exc)}
    result['quarantine'] = backend
    return result


def _ledger_path(directory):
    return core._safe(directory, core.LEDGER)


def ledger(directory, event):
    path = _ledger_path(directory)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'a', encoding='utf-8') as target:
        target.write(json.dumps(event, sort_keys=True) + '\n')


def ledger_events(directory):
    try:
        with open(_ledger_path(directory), encoding='utf-8') as source:
            return [json.loads(line) for line in source if line.strip()]
    except FileNotFoundError:
        return []


def cost(directory):
    totals = {}
    for event in ledger_events(directory):
        for key in core.COST_KEYS:
            value = event.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                totals[key] = totals.get(key, 0) + value
    return totals or None


def _in_band(a, b, tolerance=core.TOLERANCE):
    if a is None or b is None:
        return None
    if a == b == 0:
        return True
    if a <= 0 or b <= 0:
        return False
    return 1 / tolerance <= b / a <= tolerance


def _independence_line(original, rebuilt):
    if not original or not rebuilt:
        return 'unestablished'
    if original.get('vendor') == rebuilt.get('vendor'):
        return 'same vendor'
    return 'different vendor'


def independence(original=None, rebuilt=None):
    return _independence_line(original, rebuilt)


def _env_cache_dir():
    return os.environ.get(core._ENV_CACHE, os.path.join(Path.home(), '.cache', 'reticuli', 'env'))


def furnish(directory, recipe):
    """Build or reuse a private, hash-pinned Python environment."""
    name = recipe.get('claim', {}).get('environment')
    if not name:
        return None
    requirements = core._safe(directory, name)
    digest = core._hash_file(requirements)
    key = hashlib.sha256((digest + sys.executable + platform.platform()).encode()).hexdigest()
    target = os.path.join(_env_cache_dir(), key)
    python = os.path.join(target, 'bin', 'python')
    if os.path.isfile(python):
        return target
    os.makedirs(os.path.dirname(target), exist_ok=True)
    venv.EnvBuilder(with_pip=True).create(target)
    command = [python, '-m', 'pip', 'install', '--require-hashes',
               '--only-binary=:all:', '-r', requirements]
    try:
        completed = subprocess.run(command, capture_output=True, text=True,
                                   timeout=core.FURNISH_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as exc:
        shutil.rmtree(target, ignore_errors=True)
        raise core.ClaimError(f'cannot furnish environment: {exc}') from exc
    if completed.returncode:
        shutil.rmtree(target, ignore_errors=True)
        raise core.ClaimError(f'cannot furnish environment: {completed.stderr[-500:]}')
    return target
