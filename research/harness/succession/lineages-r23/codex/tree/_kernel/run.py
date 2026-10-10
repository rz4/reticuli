"""Run claim gates with a bounded, scrubbed environment and record costs."""

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

from . import core

_REQ_OPS = ('<=', '>=', '==', '!=', '~=', '<', '>')
_BWRAP_OK = None


def _have(name):
    return shutil.which(name) is not None


def _quote_sb(value):
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"') + '"'


def _in_band(path, directory):
    path = os.path.realpath(path)
    directory = os.path.realpath(directory)
    return path == directory or os.path.commonpath((path, directory)) == directory


def _bwrap_usable():
    global _BWRAP_OK
    if _BWRAP_OK is None:
        if not _have('bwrap'):
            _BWRAP_OK = False
        else:
            try:
                result = subprocess.run(
                    ['bwrap', '--ro-bind', '/', '/', '--dev-bind', '/dev', '/dev',
                     '--proc', '/proc', '--', 'true'],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=5, check=False)
                _BWRAP_OK = result.returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                _BWRAP_OK = False
    return _BWRAP_OK


def sandbox_backend():
    if os.environ.get(core._JAILED):
        return 'inherited'
    if sys.platform == 'darwin' and _have('sandbox-exec'):
        return 'seatbelt'
    if sys.platform.startswith('linux') and _bwrap_usable():
        return 'bubblewrap'
    return 'none'


def sandbox():
    return {'backend': sandbox_backend()}


def _sandbox_argv(command, directory, backend=None):
    backend = backend or sandbox_backend()
    shell = '/bin/sh'
    if backend == 'seatbelt':
        # Keep host reads, process creation, device sinks and user lookup
        # available to ordinary gates. Restrict writes and network access.
        profile = ('(version 1)\n'
                   '(allow default)\n'
                   '(deny network*)\n'
                   '(deny file-write*)\n'
                   f'(allow file-write* (subpath {_quote_sb(os.path.realpath(directory))}))\n'
                   '(allow file-write* (literal "/dev/null"))\n'
                   '(allow file-write* (literal "/dev/tty"))\n')
        return ['sandbox-exec', '-p', profile, shell, '-c', command]
    if backend == 'bubblewrap':
        directory = os.path.realpath(directory)
        return ['bwrap', '--ro-bind', '/', '/', '--dev-bind', '/dev', '/dev',
                '--proc', '/proc', '--bind', directory, directory,
                '--chdir', directory, '--unshare-net', '--', shell, '-c', command]
    return [shell, '-c', command]


def _scrub_env(directory=None, extra=None, backend=None):
    env = {key: os.environ[key] for key in core._KEEP_ENV if key in os.environ}
    env.setdefault('PATH', os.defpath)
    env.setdefault('LANG', 'C')
    if extra:
        env.update({str(key): str(value) for key, value in extra.items()})
    if backend in ('seatbelt', 'bubblewrap'):
        scratch = os.path.join(os.fspath(directory), core.STORE, 'tmp')
        os.makedirs(scratch, exist_ok=True)
        env['HOME'] = scratch
        env['TMPDIR'] = scratch
        env[core._JAILED] = '1'
    return env


def gate_timeout(recipe=None):
    if isinstance(recipe, dict):
        claim = recipe.get('claim', {})
        if 'gate_timeout' in claim:
            value = claim['gate_timeout']
            if type(value) not in (int, float) or value <= 0:
                raise core.ClaimError('claim gate_timeout must be positive')
            return value
    value = os.environ.get(core._ENV_TIMEOUT)
    if value is not None:
        try:
            value = float(value)
            if value > 0:
                return value
        except ValueError:
            pass
    return core.GATE_TIMEOUT


def _kill_tree(process):
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except OSError:
        process.kill()


def _run(argv, directory, env, timeout):
    start = time.monotonic()
    try:
        process = subprocess.Popen(argv, cwd=directory, env=env,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=True)
        try:
            stdout, stderr = process.communicate(timeout=timeout)
            status = 'ok' if process.returncode == 0 else 'failed'
        except subprocess.TimeoutExpired:
            _kill_tree(process)
            stdout, stderr = process.communicate()
            status = 'timeout'
        return {'status': status, 'returncode': process.returncode,
                'stdout': stdout.decode('utf-8', 'replace'),
                'stderr': stderr.decode('utf-8', 'replace'),
                'seconds': time.monotonic() - start}
    except OSError as exc:
        return {'status': 'environment', 'returncode': None, 'stdout': '',
                'stderr': str(exc), 'seconds': time.monotonic() - start}


def run_gate(command, directory, recipe=None, env=None):
    backend = sandbox_backend()
    result = _run(_sandbox_argv(command, directory, backend), directory,
                  _scrub_env(directory, env, backend), gate_timeout(recipe))
    result['quarantine'] = backend
    return result


def _ledger_path(directory):
    return core._safe(directory, core.LEDGER)


def ledger(directory, event):
    path = _ledger_path(directory)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'a', encoding='utf-8') as stream:
        stream.write(json.dumps(event, sort_keys=True) + '\n')


def ledger_events(directory):
    path = _ledger_path(directory)
    if not os.path.isfile(path):
        return []
    try:
        with open(path, encoding='utf-8') as stream:
            return [json.loads(line) for line in stream if line.strip()]
    except (OSError, ValueError) as exc:
        raise core.ClaimError(f'invalid ledger {path}: {exc}') from exc


def cost(directory):
    totals = {}
    for event in ledger_events(directory):
        if event.get('kind') != 'producer':
            continue
        for key in core.COST_KEYS:
            value = event.get(key)
            if type(value) in (int, float) and value >= 0:
                totals[key] = totals.get(key, 0) + value
    return totals or None


def _version_tuple(value):
    return tuple(int(part) for part in re.findall(r'\d+', str(value)))


def _version_ok(actual, op, wanted):
    actual, wanted = _version_tuple(actual), _version_tuple(wanted)
    if op == '>=':
        return actual >= wanted
    if op == '<=':
        return actual <= wanted
    if op == '>':
        return actual > wanted
    if op == '<':
        return actual < wanted
    if op == '==':
        return actual == wanted
    if op == '!=':
        return actual != wanted
    if op == '~=':
        return actual >= wanted and actual[:max(1, len(wanted)-1)] == wanted[:max(1, len(wanted)-1)]
    return False


def _tool_version(name):
    try:
        done = subprocess.run([name, '--version'], capture_output=True, text=True,
                              timeout=5, check=False)
        return (done.stdout or done.stderr).strip()
    except (OSError, subprocess.TimeoutExpired):
        return ''


def preflight(recipe):
    missing = []
    for requirement in recipe.get('claim', {}).get('requires', []):
        match = re.fullmatch(r'([^<>=!~\s]+)\s*(<=|>=|==|!=|~=|<|>)?\s*(.*)', requirement)
        if not match:
            missing.append(requirement)
            continue
        name, op, wanted = match.groups()
        present = _have(name) or importlib.util.find_spec(name) is not None
        if present and op:
            present = _version_ok(_tool_version(name), op, wanted)
        if not present:
            missing.append(requirement)
    return missing


def _env_cache_dir():
    return os.environ.get(core._ENV_CACHE) or os.path.join(
        os.path.expanduser('~'), '.cache', 'reticuli', 'env')


def furnish(directory, recipe=None):
    if recipe is None:
        from . import recipe as recipe_module
        recipe = recipe_module.load_recipe(directory)
    name = recipe.get('claim', {}).get('environment')
    if not name:
        return None
    source = core._safe(directory, name)
    digest = core._hash_file(source)
    cache_key = hashlib.sha256((digest + sys.executable + platform.platform()).encode()).hexdigest()
    target = os.path.join(_env_cache_dir(), cache_key)
    python = os.path.join(target, 'bin', 'python')
    if os.path.isfile(python):
        return target
    os.makedirs(os.path.dirname(target), exist_ok=True)
    staging = tempfile.mkdtemp(prefix='reticuli-env-', dir=os.path.dirname(target))
    try:
        venv.EnvBuilder(with_pip=True).create(staging)
        pip = os.path.join(staging, 'bin', 'pip')
        done = subprocess.run([pip, 'install', '--require-hashes',
                               '--only-binary=:all:', '-r', source],
                              capture_output=True, text=True,
                              timeout=core.FURNISH_TIMEOUT, check=False)
        if done.returncode:
            raise core.ClaimError(f'cannot furnish environment: {done.stderr[-500:]}')
        os.replace(staging, target)
        return target
    finally:
        if os.path.exists(staging):
            shutil.rmtree(staging, ignore_errors=True)


def _independence_line(producer):
    if not isinstance(producer, dict):
        return 'independence unestablished'
    vendor = producer.get('vendor')
    model = producer.get('model')
    return f'{vendor or "unknown vendor"}/{model or "unknown model"}'


def independence(original=None, rebuild=None):
    first = original or {}
    second = rebuild or {}
    if isinstance(first, dict) and isinstance(second, dict):
        if first.get('vendor') and second.get('vendor') and first['vendor'] != second['vendor']:
            return {'established': True, 'reason': 'different vendors'}
    return {'established': False, 'reason': 'independence unestablished'}
