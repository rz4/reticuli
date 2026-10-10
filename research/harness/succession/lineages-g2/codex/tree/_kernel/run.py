"""Execute claim gates and account for production cost.

The gate runner gives a command a small environment, a wall clock limit, and
the best working confinement available on the host.
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
from collections.abc import Mapping

from . import core


_REQ_OPS = ('<=', '>=', '==', '!=', '~=', '<', '>')
_BWRAP_OK = None


def _have(name: str) -> bool:
    return shutil.which(name) is not None


def _quote_sb(path: str) -> str:
    """Quote a path as one Seatbelt profile string."""
    return json.dumps(os.path.realpath(path))


def _bwrap_usable() -> bool:
    global _BWRAP_OK
    if _BWRAP_OK is not None:
        return _BWRAP_OK
    if not _have('bwrap'):
        _BWRAP_OK = False
        return False
    try:
        result = subprocess.run(
            ['bwrap', '--ro-bind', '/', '/', '--proc', '/proc', '--dev', '/dev',
             '--', '/bin/sh', '-c', 'true'], stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=5)
        _BWRAP_OK = result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        _BWRAP_OK = False
    return _BWRAP_OK


def sandbox_backend() -> str:
    if os.environ.get(core._JAILED):
        return 'inherited'
    if sys.platform == 'darwin' and _have('sandbox-exec'):
        try:
            probe = subprocess.run(
                ['sandbox-exec', '-p', '(version 1)(allow default)',
                 '/bin/sh', '-c', 'true'], stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=5)
            if probe.returncode == 0:
                return 'seatbelt'
        except (OSError, subprocess.TimeoutExpired):
            pass
    if sys.platform.startswith('linux') and _bwrap_usable():
        return 'bubblewrap'
    return 'none'


def sandbox() -> dict[str, str]:
    return {'backend': sandbox_backend()}


def _sandbox_argv(command: str, directory: str, backend: str | None = None) -> list[str]:
    backend = backend or sandbox_backend()
    shell = [core._SHELL, '-c', command]
    if backend == 'seatbelt':
        profile = ('(version 1)\n(allow default)\n'
                   '(deny network*)\n(deny file-write*)\n'
                   f'(allow file-write* (subpath {_quote_sb(directory)}))\n'
                   '(allow file-write* (literal "/dev/null"))\n'
                   '(allow file-write* (literal "/dev/tty"))\n')
        return ['sandbox-exec', '-p', profile, *shell]
    if backend == 'bubblewrap':
        return ['bwrap', '--ro-bind', '/', '/', '--dev-bind', '/dev', '/dev',
                '--proc', '/proc', '--bind', directory, directory,
                '--chdir', directory, '--unshare-net', '--', *shell]
    return shell


def _scrub_env(directory: str, backend: str | None = None,
               extra: Mapping[str, str] | None = None) -> dict[str, str]:
    backend = backend or sandbox_backend()
    env = {key: os.environ[key] for key in core._KEEP_ENV if key in os.environ}
    env.setdefault('PATH', os.defpath)
    if backend in ('seatbelt', 'bubblewrap'):
        scratch = os.path.join(directory, core.STORE, 'tmp')
        os.makedirs(scratch, exist_ok=True)
        env['HOME'] = scratch
        env['TMPDIR'] = scratch
        env[core._JAILED] = '1'
    if extra:
        env.update({str(key): str(value) for key, value in extra.items()})
    return env


def _kill_tree(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except OSError:
        process.kill()


def _run(argv: list[str], directory: str, env: Mapping[str, str],
         timeout: float) -> dict:
    started = time.monotonic()
    try:
        process = subprocess.Popen(argv, cwd=directory, env=dict(env),
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
                'seconds': time.monotonic() - started}
    except OSError as exc:
        return {'status': 'environment', 'returncode': None, 'stdout': '',
                'stderr': str(exc), 'seconds': time.monotonic() - started}


def gate_timeout(recipe: Mapping | None = None) -> float:
    claim = recipe.get('claim', {}) if isinstance(recipe, Mapping) else {}
    if isinstance(claim, Mapping) and 'gate_timeout' in claim:
        return float(claim['gate_timeout'])
    configured = os.environ.get(core._ENV_TIMEOUT)
    if configured:
        try:
            value = float(configured)
            if math.isfinite(value) and value > 0:
                return value
        except ValueError:
            pass
    return core.GATE_TIMEOUT


def run_gate(command: str, directory: os.PathLike[str] | str,
             recipe: Mapping | None = None, *,
             extra_env: Mapping[str, str] | None = None) -> dict:
    directory = os.path.realpath(os.fspath(directory))
    backend = sandbox_backend()
    env = _scrub_env(directory, backend, extra_env)
    result = _run(_sandbox_argv(command, directory, backend), directory, env,
                  gate_timeout(recipe))
    result['quarantine'] = backend
    return result


def _ledger_path(directory: os.PathLike[str] | str) -> str:
    return core._safe(directory, core.LEDGER)


def ledger(directory: os.PathLike[str] | str, event: Mapping) -> None:
    path = _ledger_path(directory)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'a', encoding='utf-8') as stream:
        stream.write(json.dumps(dict(event), sort_keys=True) + '\n')


def ledger_events(directory: os.PathLike[str] | str) -> list[dict]:
    path = _ledger_path(directory)
    if not os.path.exists(path):
        return []
    result = []
    with open(path, encoding='utf-8') as stream:
        for line in stream:
            if line.strip():
                result.append(json.loads(line))
    return result


def cost(directory: os.PathLike[str] | str) -> dict[str, float] | None:
    totals: dict[str, float] = {}
    for event in ledger_events(directory):
        if event.get('kind') not in ('producer', 'produce'):
            continue
        for key in core.COST_KEYS:
            value = event.get(key)
            if type(value) in (int, float) and math.isfinite(value) and value >= 0:
                totals[key] = totals.get(key, 0) + value
    return totals or None


def _version_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r'\d+', value))


def _version_ok(actual: str, operator: str, requested: str) -> bool:
    left, right = _version_tuple(actual), _version_tuple(requested)
    if operator == '==': return left == right
    if operator == '!=': return left != right
    if operator == '>=': return left >= right
    if operator == '<=': return left <= right
    if operator == '>': return left > right
    if operator == '<': return left < right
    if operator == '~=': return left >= right and left[:max(1, len(right)-1)] == right[:max(1, len(right)-1)]
    return False


def _tool_version(name: str) -> str | None:
    try:
        done = subprocess.run([name, '--version'], capture_output=True,
                              text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return (done.stdout or done.stderr).strip().splitlines()[0] if (done.stdout or done.stderr).strip() else None


def preflight(recipe: Mapping) -> list[str]:
    """List requirements absent from the judging host."""
    claim = recipe.get('claim', {}) if isinstance(recipe, Mapping) else {}
    missing = []
    for requirement in claim.get('requires', []):
        name = re.split(r'\s*(?:>=|<=|==|!=|~=|>|<)\s*', requirement, maxsplit=1)[0]
        if not _have(name):
            try:
                found = importlib.util.find_spec(name) is not None
            except (ImportError, ValueError):
                found = False
            if not found:
                missing.append(requirement)
    return missing


def _env_cache_dir() -> str:
    return os.path.realpath(os.environ.get(core._ENV_CACHE,
                            os.path.join(os.path.expanduser('~'), '.cache', 'reticuli', 'env')))


def furnish(directory: os.PathLike[str] | str, recipe: Mapping) -> str | None:
    """Install a declared hash-pinned Python environment and return its bin."""
    name = recipe.get('claim', {}).get('environment')
    if not name:
        return None
    requirements = core._safe(directory, name)
    digest = core._hash_file(requirements)
    key = hashlib.sha256((digest + sys.executable + platform.platform()).encode()).hexdigest()
    target = os.path.join(_env_cache_dir(), key)
    ready = os.path.join(target, '.ready')
    bindir = os.path.join(target, 'Scripts' if os.name == 'nt' else 'bin')
    if os.path.exists(ready):
        return bindir
    os.makedirs(os.path.dirname(target), exist_ok=True)
    venv.EnvBuilder(with_pip=True).create(target)
    pip = os.path.join(bindir, 'pip')
    try:
        subprocess.run([pip, 'install', '--require-hashes', '--only-binary=:all:',
                        '-r', requirements], check=True, timeout=core.FURNISH_TIMEOUT,
                       capture_output=True)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise core.ClaimError(f'cannot furnish environment: {exc}') from exc
    with open(ready, 'w', encoding='utf-8') as stream:
        stream.write(digest + '\n')
    return bindir


def _in_band(first: float, second: float, tolerance: float = core.TOLERANCE) -> bool:
    return first <= second * tolerance and second <= first * tolerance


def _independence_line(original: Mapping | None, rebuilt: Mapping | None) -> str:
    a = (original or {}).get('vendor')
    b = (rebuilt or {}).get('vendor')
    if not a or not b:
        return 'independence unestablished'
    return 'same vendor' if a == b else 'different vendors'


def independence(original: Mapping | None, rebuilt: Mapping | None) -> dict:
    return {'status': _independence_line(original, rebuilt),
            'original': dict(original or {}), 'rebuilt': dict(rebuilt or {})}
