"""Gate execution, host requirements, and the local cost ledger.

A sandbox is advertised only after a functional probe.  Gate results always
record which confinement was actually used.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
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


def _have(name: str) -> bool:
    return shutil.which(name) is not None


def _version_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", value))


def _tool_version(name: str) -> str | None:
    try:
        done = subprocess.run([name, "--version"], capture_output=True,
                              text=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return (done.stdout or done.stderr).strip().splitlines()[0] if (done.stdout or done.stderr).strip() else None


def _version_ok(actual: str, operator: str, required: str) -> bool:
    left, right = _version_tuple(actual), _version_tuple(required)
    if not left or not right:
        return False
    if operator == '~=':
        return left >= right and left[:max(1, len(right) - 1)] == right[:max(1, len(right) - 1)]
    return {'<': left < right, '<=': left <= right, '==': left == right,
            '!=': left != right, '>=': left >= right, '>': left > right}.get(operator, False)


def preflight(recipe: dict) -> list[str]:
    """Return requirements that this host does not satisfy."""
    missing = []
    for requirement in recipe.get('claim', {}).get('requires', []):
        if not isinstance(requirement, str):
            missing.append(str(requirement))
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.+-]+)\s*(<=|>=|==|!=|~=|<|>)\s*([\w.+-]+)", requirement)
        name = match.group(1) if match else requirement
        available = _have(name)
        if not available:
            try:
                available = importlib.util.find_spec(name) is not None
            except (ImportError, ValueError, AttributeError):
                available = False
        if not available or (match and not _version_ok(_tool_version(name) or '', match.group(2), match.group(3))):
            missing.append(requirement)
    return missing


def _quote_sb(path: str) -> str:
    return json.dumps(os.path.realpath(path))


def _bwrap_usable() -> bool:
    global _BWRAP_OK
    if _BWRAP_OK is not None:
        return _BWRAP_OK
    if not _have('bwrap'):
        _BWRAP_OK = False
        return False
    try:
        done = subprocess.run(['bwrap', '--ro-bind', '/', '/', '--dev-bind', '/dev', '/dev',
                               '--proc', '/proc', '--', '/bin/sh', '-c', 'true'],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              timeout=5)
        _BWRAP_OK = done.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        _BWRAP_OK = False
    return _BWRAP_OK


def sandbox_backend() -> str:
    if os.environ.get(core._JAILED):
        return 'inherited'
    if sys.platform.startswith('linux') and _bwrap_usable():
        return 'bubblewrap'
    # sandbox-exec is often installed but unusable in an already confined
    # process.  The capability test includes a write in the intended room.
    if sys.platform == 'darwin' and _have('sandbox-exec'):
        with tempfile.TemporaryDirectory() as directory:
            profile = _seatbelt_profile(directory)
            try:
                done = subprocess.run(['sandbox-exec', '-p', profile, '/bin/sh', '-c',
                                       'printf ok > PROBE'], cwd=directory,
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                      timeout=5)
                if done.returncode == 0 and os.path.exists(os.path.join(directory, 'PROBE')):
                    return 'seatbelt'
            except (OSError, subprocess.TimeoutExpired):
                pass
    return 'none'


def sandbox() -> dict:
    return {'backend': sandbox_backend()}


def _seatbelt_profile(directory: str) -> str:
    return ('(version 1) (deny default) (allow file-read*) (allow process*) '
            '(allow sysctl-read) (allow mach-lookup) '
            f'(allow file-write* (subpath {_quote_sb(directory)})) '
            '(allow file-write* (literal "/dev/null"))')


def _sandbox_argv(command: str, directory: str, backend: str) -> list[str]:
    shell = [core._SHELL, '-c', command]
    if backend == 'bubblewrap':
        return ['bwrap', '--ro-bind', '/', '/', '--dev-bind', '/dev', '/dev',
                '--proc', '/proc', '--bind', os.path.realpath(directory), os.path.realpath(directory),
                '--chdir', os.path.realpath(directory), '--unshare-net', '--', *shell]
    if backend == 'seatbelt':
        return ['sandbox-exec', '-p', _seatbelt_profile(directory), *shell]
    return shell


def _scrub_env(directory: str, recipe: dict | None = None, backend: str = 'none') -> dict[str, str]:
    env = {key: os.environ[key] for key in core._KEEP_ENV if key in os.environ}
    env.setdefault('PATH', os.defpath)
    if backend in ('seatbelt', 'bubblewrap'):
        scratch = os.path.join(directory, core.STORE, 'scratch')
        os.makedirs(scratch, exist_ok=True)
        env['HOME'] = scratch
        env['TMPDIR'] = scratch
        env[core._JAILED] = '1'
    if recipe:
        claim = recipe.get('claim', {})
        variables = claim.get('variables', {})
        if isinstance(variables, dict):
            env.update({str(key): str(value) for key, value in variables.items()})
    return env


def gate_timeout(recipe: dict | None = None) -> float:
    declared = (recipe or {}).get('claim', {}).get('gate_timeout')
    if declared is not None:
        if isinstance(declared, bool) or not isinstance(declared, (int, float)) or not math.isfinite(declared) or declared <= 0:
            raise core.ClaimError('gate_timeout must be a positive number')
        return declared
    host = os.environ.get(core._ENV_TIMEOUT)
    if host:
        try:
            value = float(host)
            if math.isfinite(value) and value > 0:
                return value
        except ValueError:
            pass
    return core.GATE_TIMEOUT


def _kill_tree(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (OSError, AttributeError):
        process.kill()


def _run(argv: list[str], directory: str, env: dict[str, str], timeout: float) -> dict:
    started = time.monotonic()
    try:
        process = subprocess.Popen(argv, cwd=directory, env=env,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, start_new_session=True)
    except OSError as exc:
        return {'status': 'environment', 'detail': str(exc), 'seconds': time.monotonic() - started}
    try:
        stdout, stderr = process.communicate(timeout=timeout)
        status = 'ok' if process.returncode == 0 else 'failed'
    except subprocess.TimeoutExpired:
        _kill_tree(process)
        stdout, stderr = process.communicate()
        status = 'timeout'
    return {'status': status, 'returncode': process.returncode,
            'stdout': stdout, 'stderr': stderr, 'seconds': time.monotonic() - started}


def run_gate(command: str, directory: str, recipe: dict | None = None) -> dict:
    missing = preflight(recipe or {})
    if missing:
        return {'status': 'environment', 'quarantine': sandbox_backend(),
                'detail': 'missing requirements: ' + ', '.join(missing)}
    backend = sandbox_backend()
    env = _scrub_env(directory, recipe, backend)
    result = _run(_sandbox_argv(command, directory, backend), directory, env,
                  gate_timeout(recipe))
    result['quarantine'] = backend
    return result


def _ledger_path(directory: str) -> str:
    return core._safe(directory, core.LEDGER)


def ledger(directory: str, event: dict) -> None:
    path = _ledger_path(directory)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'a', encoding='utf-8') as stream:
        stream.write(json.dumps(event, sort_keys=True) + '\n')


def ledger_events(directory: str) -> list[dict]:
    path = _ledger_path(directory)
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def cost(directory: str) -> dict[str, float] | None:
    totals = {}
    for event in ledger_events(directory):
        if event.get('kind') != 'producer':
            continue
        for key in core.COST_KEYS:
            value = event.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                totals[key] = totals.get(key, 0) + value
    return totals or None


def _in_band(original: float, rebuilt: float, tolerance: float = core.TOLERANCE) -> bool:
    if original < 0 or rebuilt < 0 or tolerance <= 0:
        return False
    return rebuilt <= original * tolerance


def _independence_line(original: dict | None, rebuilt: dict | None) -> str:
    first = (original or {}).get('vendor')
    second = (rebuilt or {}).get('vendor')
    if first and second and first != second:
        return 'different vendors'
    return 'independence unestablished'


def independence(original: dict | None = None, rebuilt: dict | None = None) -> dict:
    return {'status': _independence_line(original, rebuilt)}


def _env_cache_dir() -> str:
    return os.environ.get(core._ENV_CACHE, os.path.join(os.path.expanduser('~'), '.cache', 'reticuli', 'env'))


def furnish(directory: str, recipe: dict) -> str | None:
    """Install a hash-pinned requirements file into a private cached venv."""
    name = recipe.get('claim', {}).get('environment')
    if not name:
        return None
    source = core._safe(directory, name)
    digest = core._hash_file(source)
    key = hashlib.sha256(f'{digest}:{sys.executable}:{platform.platform()}'.encode()).hexdigest()
    target = os.path.join(_env_cache_dir(), key)
    python = os.path.join(target, 'bin', 'python')
    if os.path.exists(python):
        return target
    os.makedirs(os.path.dirname(target), exist_ok=True)
    venv.EnvBuilder(with_pip=True).create(target)
    result = subprocess.run([python, '-m', 'pip', 'install', '--require-hashes',
                             '--only-binary=:all:', '-r', source],
                            capture_output=True, text=True, timeout=core.FURNISH_TIMEOUT)
    if result.returncode:
        shutil.rmtree(target, ignore_errors=True)
        raise core.ClaimError('cannot furnish environment: ' + result.stderr[-500:])
    return target
