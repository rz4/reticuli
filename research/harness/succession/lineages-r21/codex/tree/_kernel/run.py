"""Execute claim gates and account for measured work."""

from __future__ import annotations

import json
import os
import re
import shlex
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


def _have(command):
    return shutil.which(command) is not None


def _quote_sb(value):
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"') + '"'


def _bwrap_usable():
    global _BWRAP_OK
    if _BWRAP_OK is None:
        if not _have('bwrap'):
            _BWRAP_OK = False
        else:
            try:
                result = subprocess.run(
                    ['bwrap', '--ro-bind', '/', '/', '--dev-bind', '/dev', '/dev',
                     '--proc', '/proc', '--unshare-net', '--', 'true'],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
                _BWRAP_OK = result.returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                _BWRAP_OK = False
    return _BWRAP_OK


def _seatbelt_profile(directory):
    room = os.path.realpath(directory)
    return ('(version 1)(allow default)(deny network*)'
            '(deny file-write*)'
            f'(allow file-write* (subpath {_quote_sb(room)}))'
            '(allow file-write-data (literal "/dev/null"))')


def sandbox_backend():
    if os.environ.get(core._JAILED):
        return 'inherited'
    if sys.platform == 'darwin' and _have('sandbox-exec'):
        try:
            with tempfile.TemporaryDirectory() as directory:
                command = ['sandbox-exec', '-p', _seatbelt_profile(directory),
                           '/bin/sh', '-c', 'printf ok > probe']
                result = subprocess.run(command, cwd=directory,
                                        stdout=subprocess.DEVNULL,
                                        stderr=subprocess.DEVNULL, timeout=5)
                if result.returncode == 0 and os.path.isfile(os.path.join(directory, 'probe')):
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
    shell = ['/bin/sh', '-c', command]
    if backend == 'seatbelt':
        return ['sandbox-exec', '-p', _seatbelt_profile(directory), *shell]
    if backend == 'bubblewrap':
        room = os.path.realpath(directory)
        return ['bwrap', '--ro-bind', '/', '/', '--dev-bind', '/dev', '/dev',
                '--proc', '/proc', '--unshare-net', '--bind', room, room,
                '--chdir', room, '--', *shell]
    return shell


def _scrub_env(directory=None, backend=None, extra=None):
    env = {key: os.environ[key] for key in core._KEEP_ENV if key in os.environ}
    env.setdefault('PATH', os.defpath)
    env.setdefault('LANG', 'C.UTF-8')
    if backend in ('seatbelt', 'bubblewrap'):
        scratch = os.path.join(os.path.realpath(directory), core.STORE, 'tmp')
        os.makedirs(scratch, exist_ok=True)
        env['HOME'] = scratch
        env['TMPDIR'] = scratch
        env[core._JAILED] = '1'
    if extra:
        env.update(extra)
    return env


def gate_timeout(recipe=None):
    claim = recipe.get('claim', {}) if isinstance(recipe, dict) else {}
    value = claim.get('gate_timeout', os.environ.get(core._ENV_TIMEOUT, core.GATE_TIMEOUT))
    try:
        number = float(value)
        if number <= 0:
            raise ValueError('must be positive')
        return number
    except (TypeError, ValueError) as exc:
        raise core.ClaimError(f'invalid gate timeout: {value!r}') from exc


def _kill_tree(process):
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        process.kill()
    process.wait()


def _run(argv, directory, timeout, env=None):
    process = subprocess.Popen(argv, cwd=directory, env=env,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
        return {'returncode': process.returncode, 'stdout': stdout, 'stderr': stderr}
    except subprocess.TimeoutExpired:
        _kill_tree(process)
        stdout, stderr = process.communicate()
        return {'returncode': None, 'stdout': stdout, 'stderr': stderr,
                'timeout': True}


def run_gate(command, directory, recipe=None):
    """Run one shell gate within its declared wall-clock limit."""
    backend = sandbox_backend()
    env = _scrub_env(directory, backend)
    start = time.monotonic()
    try:
        result = _run(_sandbox_argv(command, directory, backend), directory,
                      gate_timeout(recipe), env)
    except OSError as exc:
        return {'status': 'environment', 'quarantine': backend,
                'error': str(exc), 'seconds': time.monotonic() - start}
    status = 'timeout' if result.get('timeout') else ('ok' if result['returncode'] == 0 else 'failed')
    return {'status': status, 'quarantine': backend,
            'returncode': result['returncode'], 'stdout': result['stdout'],
            'stderr': result['stderr'], 'seconds': time.monotonic() - start}


def _ledger_path(directory):
    return os.path.join(directory, core.LEDGER)


def ledger(directory, event):
    path = _ledger_path(directory)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'a', encoding='utf-8') as stream:
        stream.write(json.dumps(event, sort_keys=True) + '\n')
    return event


def ledger_events(directory):
    try:
        with open(_ledger_path(directory), encoding='utf-8') as stream:
            return [json.loads(line) for line in stream if line.strip()]
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as exc:
        raise core.ClaimError(f'cannot read ledger: {exc}') from exc


def cost(directory):
    totals = {}
    for event in ledger_events(directory):
        for key in core.COST_KEYS:
            value = event.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                totals[key] = totals.get(key, 0) + value
    return totals or None


def _version_tuple(value):
    return tuple(int(part) for part in re.findall(r'\d+', str(value)))


def _version_ok(actual, requirement):
    match = re.match(r'\s*(<=|>=|==|!=|~=|<|>)\s*(.*)', str(requirement))
    if not match:
        return True
    op, wanted = match.groups()
    left, right = _version_tuple(actual), _version_tuple(wanted)
    return {'<': left < right, '<=': left <= right, '==': left == right,
            '!=': left != right, '>=': left >= right, '>': left > right,
            '~=': left >= right and left[:1] == right[:1]}[op]


def _tool_version(name):
    try:
        result = subprocess.run([name, '--version'], capture_output=True,
                                text=True, timeout=5)
        return (result.stdout or result.stderr).strip()
    except (OSError, subprocess.TimeoutExpired):
        return None


def preflight(recipe):
    import importlib.util
    missing = []
    for item in recipe.get('claim', {}).get('requires', []):
        if not isinstance(item, str):
            missing.append(str(item))
            continue
        name = re.split(r'[<>=!~]', item, 1)[0].strip()
        if not _have(name):
            try:
                found = importlib.util.find_spec(name) is not None
            except (ImportError, ValueError, ModuleNotFoundError):
                found = False
            if not found:
                missing.append(item)
    return missing


def _env_cache_dir():
    return os.environ.get(core._ENV_CACHE, os.path.join(Path.home(), '.cache', 'reticuli'))


def furnish(directory, recipe=None):
    """Create a private Python environment for a hash-pinned requirements file."""
    from . import recipe as recipe_module
    from . import identity
    recipe = recipe or recipe_module.load_recipe(directory)
    filename = recipe.get('claim', {}).get('environment')
    if not filename:
        return None
    path = core._safe(directory, filename)
    key = core._hash_file(path) + '-' + str(sys.version_info[:2]).replace(' ', '')
    target = os.path.join(_env_cache_dir(), key)
    python = os.path.join(target, 'bin', 'python')
    if not os.path.isfile(python):
        os.makedirs(os.path.dirname(target), exist_ok=True)
        venv.EnvBuilder(with_pip=True).create(target)
        done = subprocess.run([python, '-m', 'pip', 'install', '--require-hashes',
                               '--only-binary=:all:', '-r', path],
                              capture_output=True, text=True,
                              timeout=core.FURNISH_TIMEOUT)
        if done.returncode:
            raise core.ClaimError(f'cannot furnish environment: {done.stderr[-500:]}')
    return target


def _in_band(a, b, tolerance=core.TOLERANCE):
    if a is None or b is None:
        return None
    if a == 0 or b == 0:
        return a == b
    return max(a / b, b / a) <= tolerance


def _independence_line(producer):
    if not isinstance(producer, dict):
        return 'independence unestablished'
    return f"{producer.get('vendor', 'unknown')}/{producer.get('model', 'unknown')}"


def independence(*producers):
    if len(producers) < 2:
        return 'independence unestablished'
    return ('independent' if _independence_line(producers[0]) !=
            _independence_line(producers[1]) else 'independence unestablished')
