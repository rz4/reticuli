"""Run claim gates in a bounded, confined environment and record run costs."""

from __future__ import annotations

import importlib.util
import json
import math
import os
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
_SANDBOX_BACKEND = None


def _have(requirement: str) -> bool:
    """Check a declared binary or importable Python module."""
    if not isinstance(requirement, str) or not requirement:
        return False
    name = re.split(r"[<>=!~ ]", requirement, 1)[0]
    if shutil.which(name):
        return True
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError, ModuleNotFoundError):
        return False


def _version_tuple(value: str) -> tuple[int, ...]:
    match = re.search(r"\d+(?:\.\d+)*", str(value))
    return tuple(int(part) for part in match.group().split('.')) if match else ()


def _version_ok(found: str, requirement: str) -> bool:
    """Evaluate a simple declared version constraint."""
    match = re.match(r"^\s*([A-Za-z_][\w.-]*)\s*(<=|>=|==|!=|~=|<|>)\s*(\d+(?:\.\d+)*)\s*$", requirement)
    if not match:
        return True
    op, wanted = match.group(2), _version_tuple(match.group(3))
    actual = _version_tuple(found)
    if not actual:
        return False
    if op == '~=':
        return actual >= wanted and actual[:max(1, len(wanted)-1)] == wanted[:max(1, len(wanted)-1)]
    return {'<': actual < wanted, '<=': actual <= wanted,
            '>': actual > wanted, '>=': actual >= wanted,
            '==': actual == wanted, '!=': actual != wanted}[op]


def _tool_version(name: str) -> str | None:
    if not shutil.which(name):
        return None
    try:
        done = subprocess.run([name, '--version'], capture_output=True, text=True,
                              timeout=5, check=False)
        return (done.stdout or done.stderr).strip().splitlines()[0]
    except (OSError, subprocess.TimeoutExpired, IndexError):
        return None


def preflight(recipe: Mapping | None) -> list[str]:
    """List declared tools unavailable on this host."""
    claim = (recipe or {}).get('claim', {})
    missing = []
    for requirement in claim.get('requires', []):
        if not _have(requirement):
            missing.append(requirement)
            continue
        if any(op in requirement for op in _REQ_OPS):
            name = re.split(r"[<>=!~ ]", requirement, 1)[0]
            version = _tool_version(name)
            if version is not None and not _version_ok(version, requirement):
                missing.append(requirement)
    return missing


def _quote_sb(value: str) -> str:
    return json.dumps(str(value))


def _bwrap_usable() -> bool:
    global _BWRAP_OK
    if _BWRAP_OK is not None:
        return _BWRAP_OK
    if not shutil.which('bwrap'):
        _BWRAP_OK = False
        return False
    try:
        probe = subprocess.run(['bwrap', '--ro-bind', '/', '/', '--dev-bind', '/dev', '/dev',
                                '--proc', '/proc', '--unshare-net', '--', '/bin/sh', '-c', 'true'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=5, check=False)
        _BWRAP_OK = probe.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        _BWRAP_OK = False
    return _BWRAP_OK


def sandbox_backend() -> str:
    """Return the confinement actually available, including an inherited jail."""
    global _SANDBOX_BACKEND
    if os.environ.get(core._JAILED):
        return 'inherited'
    if _SANDBOX_BACKEND is not None:
        return _SANDBOX_BACKEND
    if sys.platform == 'darwin' and shutil.which('sandbox-exec'):
        try:
            result = subprocess.run(['sandbox-exec', '-p', '(version 1)(allow default)',
                                     '/bin/sh', '-c', 'true'],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    timeout=5, check=False)
            if result.returncode == 0:
                _SANDBOX_BACKEND = 'seatbelt'
                return _SANDBOX_BACKEND
        except (OSError, subprocess.TimeoutExpired):
            pass
    _SANDBOX_BACKEND = 'bubblewrap' if _bwrap_usable() else 'none'
    return _SANDBOX_BACKEND


def sandbox() -> dict[str, str]:
    return {'backend': sandbox_backend()}


def _sandbox_argv(command: str, directory: str, backend: str | None = None) -> list[str]:
    backend = backend or sandbox_backend()
    if backend == 'seatbelt':
        room = os.path.realpath(directory)
        profile = ('(version 1)(allow default)(deny network*)'
                   '(deny file-write* (subpath "/"))'
                   f'(allow file-write* (subpath {_quote_sb(room)}))'
                   '(allow file-write* (subpath "/dev"))')
        return ['sandbox-exec', '-p', profile, core._SHELL, '-c', command]
    if backend == 'bubblewrap':
        room = os.path.realpath(directory)
        return ['bwrap', '--ro-bind', '/', '/', '--bind', room, room,
                '--dev-bind', '/dev', '/dev', '--proc', '/proc',
                '--unshare-net', '--', core._SHELL, '-c', command]
    return [core._SHELL, '-c', command]


def _scrub_env(directory: str | os.PathLike[str], backend: str | None = None) -> dict[str, str]:
    """Keep only ordinary host settings and put confined scratch inside the room."""
    backend = backend or sandbox_backend()
    env = {key: os.environ[key] for key in core._KEEP_ENV if key in os.environ}
    env.setdefault('PATH', os.defpath)
    if backend in ('seatbelt', 'bubblewrap'):
        scratch = os.path.join(os.path.realpath(directory), core.STORE, 'scratch')
        os.makedirs(scratch, exist_ok=True)
        env['HOME'] = scratch
        env['TMPDIR'] = scratch
        env[core._JAILED] = '1'
    return env


def gate_timeout(recipe: Mapping | None = None) -> float:
    """A claim's declared ceiling supersedes the host default."""
    declared = (recipe or {}).get('claim', {}).get('gate_timeout')
    if declared is not None:
        if isinstance(declared, bool) or not isinstance(declared, (int, float)) or not math.isfinite(declared) or declared <= 0:
            raise core.ClaimError('gate_timeout must be positive and finite')
        return declared
    override = os.environ.get(core._ENV_TIMEOUT)
    if override:
        try:
            value = float(override)
            if math.isfinite(value) and value > 0:
                return value
        except ValueError:
            pass
    return core.GATE_TIMEOUT


def _kill_tree(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        process.kill()


def _run(argv: list[str], directory: str | os.PathLike[str], env: Mapping[str, str], timeout: float) -> dict:
    start = time.monotonic()
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
                'seconds': time.monotonic() - start}
    except OSError as exc:
        return {'status': 'environment', 'returncode': None, 'stdout': '',
                'stderr': str(exc), 'seconds': time.monotonic() - start}


def run_gate(command: str, directory: str | os.PathLike[str], recipe: Mapping | None = None) -> dict:
    """Run a gate with a scrubbed environment, reported jail and wall-clock bound."""
    missing = preflight(recipe)
    backend = sandbox_backend()
    if missing:
        return {'status': 'environment', 'quarantine': backend,
                'stderr': 'missing requirements: ' + ', '.join(missing)}
    directory = os.path.realpath(directory)
    env = _scrub_env(directory, backend)
    result = _run(_sandbox_argv(command, directory, backend), directory,
                  env, gate_timeout(recipe))
    result['quarantine'] = backend
    return result


def _ledger_path(directory: str | os.PathLike[str]) -> str:
    return os.path.join(directory, core.LEDGER)


def ledger(directory: str | os.PathLike[str], event: Mapping) -> None:
    """Append one cost observation as JSON Lines residue."""
    path = _ledger_path(directory)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'a', encoding='utf-8') as stream:
        stream.write(json.dumps(dict(event), sort_keys=True) + '\n')


def ledger_events(directory: str | os.PathLike[str]) -> list[dict]:
    path = _ledger_path(directory)
    try:
        with open(path, 'r', encoding='utf-8') as stream:
            return [json.loads(line) for line in stream if line.strip()]
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as exc:
        raise core.ClaimError(f'cannot read ledger {path}: {exc}') from exc


def cost(directory: str | os.PathLike[str]) -> dict[str, float] | None:
    """Total only measured units, keeping unmeasured units absent."""
    totals: dict[str, float] = {}
    for event in ledger_events(directory):
        for unit in core.COST_KEYS:
            value = event.get(unit)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                totals[unit] = totals.get(unit, 0) + value
    return totals or None


def _in_band(first: float, second: float, tolerance: float) -> bool:
    return first >= 0 and second >= 0 and max(first, second) <= tolerance * max(min(first, second), 1e-12)


def _independence_line(first: Mapping | None, second: Mapping | None) -> str:
    first, second = first or {}, second or {}
    if first.get('vendor') and second.get('vendor') and first['vendor'] != second['vendor']:
        return 'different vendors declared'
    return 'independence unestablished'


def independence(first: Mapping | None, second: Mapping | None) -> dict:
    return {'line': _independence_line(first, second)}


def _env_cache_dir() -> str:
    return os.environ.get(core._ENV_CACHE) or os.path.join(os.path.expanduser('~'), '.cache', 'reticuli', 'env')


def furnish(directory: str | os.PathLike[str], recipe: Mapping | None = None) -> str | None:
    """Install a hash-pinned Python environment and return its bin directory."""
    claim = (recipe or {}).get('claim', {})
    environment = claim.get('environment')
    if not environment:
        return None
    path = core._safe(directory, environment)
    digest = core._hash_file(path)
    target = os.path.join(_env_cache_dir(), digest, f'py{sys.version_info.major}.{sys.version_info.minor}-{sys.platform}')
    marker = os.path.join(target, '.ready')
    if not os.path.isfile(marker):
        os.makedirs(os.path.dirname(target), exist_ok=True)
        venv.EnvBuilder(with_pip=True).create(target)
        pip = os.path.join(target, 'bin', 'pip')
        done = subprocess.run([pip, 'install', '--require-hashes', '--only-binary=:all:',
                               '-r', path], capture_output=True, text=True,
                              timeout=core.FURNISH_TIMEOUT, check=False)
        if done.returncode:
            raise core.ClaimError('cannot furnish environment: ' + done.stderr[-1000:])
        with open(marker, 'w', encoding='utf-8') as stream:
            stream.write('ready\n')
    return os.path.join(target, 'bin')
