"""Execute claim gates and record their resource use."""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
from typing import Any

from . import core


_REQ_OPS = ('<=', '>=', '==', '!=', '~=', '<', '>')
_BWRAP_OK = None


def _have(command: str) -> bool:
    return shutil.which(command) is not None


def _bwrap_usable() -> bool:
    global _BWRAP_OK
    if _BWRAP_OK is None:
        if not _have('bwrap'):
            _BWRAP_OK = False
        else:
            try:
                probe = subprocess.run(
                    ['bwrap', '--ro-bind', '/', '/', '--proc', '/proc',
                     '--dev-bind', '/dev', '/dev', '--', '/bin/sh', '-c', 'true'],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=3, check=False,
                )
                _BWRAP_OK = probe.returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                _BWRAP_OK = False
    return _BWRAP_OK


def _in_band(value: Any, low: float, high: float) -> bool:
    try:
        return low <= float(value) <= high
    except (TypeError, ValueError):
        return False


def _quote_sb(path: str) -> str:
    """Quote a path as a seatbelt profile string."""
    return json.dumps(os.path.realpath(path))


def sandbox_backend() -> str:
    if os.environ.get(core._JAILED):
        return 'inherited'
    if sys.platform == 'darwin' and _have('sandbox-exec'):
        return 'seatbelt'
    if sys.platform.startswith('linux') and _bwrap_usable():
        return 'bubblewrap'
    return 'none'


def _sandbox_argv(argv: list[str], directory: str, backend: str | None = None) -> list[str]:
    backend = backend or sandbox_backend()
    if backend == 'seatbelt':
        profile = ('(version 1)(deny default)(allow process*)'
                   '(allow file-read*)(allow file-write* (subpath '
                   + _quote_sb(directory) + '))')
        return ['sandbox-exec', '-p', profile, *argv]
    if backend == 'bubblewrap':
        return ['bwrap', '--ro-bind', '/', '/', '--bind', os.path.realpath(directory),
                os.path.realpath(directory), '--proc', '/proc', '--dev-bind',
                '/dev', '/dev', '--', *argv]
    return argv


def sandbox(argv: list[str], directory: str) -> list[str]:
    return _sandbox_argv(argv, directory)


def _scrub_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {key: os.environ[key] for key in core._KEEP_ENV if key in os.environ}
    if extra:
        env.update({str(key): str(value) for key, value in extra.items()})
    return env


def gate_timeout(value: Any = None) -> float:
    if value is None:
        value = os.environ.get(core._ENV_TIMEOUT, core.GATE_TIMEOUT)
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise core.ClaimError('invalid gate timeout') from exc
    if number <= 0:
        raise core.ClaimError('gate timeout must be positive')
    return number


def _kill_tree(process: subprocess.Popen[Any]) -> None:
    try:
        if os.name == 'posix':
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    except ProcessLookupError:
        pass


def _run(argv: list[str], directory: str, timeout: float,
         env: dict[str, str] | None = None) -> dict[str, Any]:
    try:
        process = subprocess.Popen(
            argv, cwd=directory, env=_scrub_env(env),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            start_new_session=(os.name == 'posix'),
        )
        try:
            stdout, stderr = process.communicate(timeout=timeout)
            return {'status': 'ok' if process.returncode == 0 else 'failed',
                    'returncode': process.returncode, 'stdout': stdout,
                    'stderr': stderr}
        except subprocess.TimeoutExpired:
            _kill_tree(process)
            stdout, stderr = process.communicate()
            return {'status': 'timeout', 'returncode': None,
                    'stdout': stdout, 'stderr': stderr}
    except OSError as exc:
        return {'status': 'failed', 'returncode': None,
                'stdout': '', 'stderr': str(exc)}


def run_gate(command: str, directory: str, timeout: Any = None) -> dict[str, Any]:
    """Run a shell gate in its claim directory and report its outcome."""
    backend = sandbox_backend()
    argv = _sandbox_argv([core._SHELL, '-c', command], directory, backend)
    result = _run(argv, directory, gate_timeout(timeout), {core._JAILED: '1'})
    result['quarantine'] = backend
    return result


def _ledger_path(directory: str) -> str:
    return core._safe(directory, core.LEDGER)


def ledger(directory: str, event: dict[str, Any]) -> None:
    """Append one JSON event to the claim's cost ledger."""
    if not isinstance(event, dict):
        raise TypeError('ledger event must be a dictionary')
    path = _ledger_path(directory)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'a', encoding='utf-8') as output:
        output.write(json.dumps(event, sort_keys=True, ensure_ascii=False) + '\n')


def ledger_events(directory: str) -> list[dict[str, Any]]:
    try:
        with open(_ledger_path(directory), encoding='utf-8') as source:
            return [json.loads(line) for line in source if line.strip()]
    except FileNotFoundError:
        return []


def cost(directory: str) -> dict[str, int | float]:
    totals: dict[str, int | float] = {}
    for event in ledger_events(directory):
        for key, value in event.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                totals[key] = totals.get(key, 0) + value
    return totals


def _env_cache_dir(directory: str) -> str:
    return os.environ.get(core._ENV_CACHE, os.path.join(directory, core.STORE, 'env'))


def _version_tuple(value: str) -> tuple[int, ...]:
    match = re.search(r'\d+(?:\.\d+)*', value)
    return tuple(int(piece) for piece in match.group().split('.')) if match else ()


def _version_ok(version: str, requirement: str) -> bool:
    requirement = requirement.strip()
    operator = next((op for op in _REQ_OPS if requirement.startswith(op)), '==')
    target = _version_tuple(requirement[len(operator):] if requirement.startswith(operator)
                            else requirement)
    actual = _version_tuple(version)
    if not target or not actual:
        return False
    if operator == '~=':
        return actual >= target and actual[:max(1, len(target) - 1)] == target[:max(1, len(target) - 1)]
    return {'<=': actual <= target, '>=': actual >= target,
            '==': actual == target, '!=': actual != target,
            '<': actual < target, '>': actual > target}[operator]


def _tool_version(tool: str) -> str | None:
    if not _have(tool):
        return None
    try:
        result = subprocess.run([tool, '--version'], capture_output=True,
                                text=True, timeout=5, check=False)
        return (result.stdout or result.stderr).strip().splitlines()[0]
    except (OSError, subprocess.TimeoutExpired, IndexError):
        return None


def preflight(tools: dict[str, str] | None = None) -> dict[str, bool]:
    return {name: (version is not None and _version_ok(version, requirement))
            for name, requirement in (tools or {}).items()
            for version in [_tool_version(name)]}


def _independence_line(value: Any) -> str:
    return str(value).strip()


def independence(value: Any) -> str:
    return _independence_line(value)


def furnish(command: str, directory: str, timeout: Any = None) -> dict[str, Any]:
    return run_gate(command, directory, timeout if timeout is not None else core.FURNISH_TIMEOUT)
