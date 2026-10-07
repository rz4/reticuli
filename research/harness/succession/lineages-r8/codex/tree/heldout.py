"""Evaluate a build with checks kept separate from the claim's own gates."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import kernel


def check(directory, command, files=None, *, timeout=120):
    """Run an external check against a disposable copy of a verified build."""
    if not kernel.verify(directory)['ok']:
        raise kernel.ClaimError('claim identity mismatch')
    with tempfile.TemporaryDirectory(prefix='reticuli-heldout-') as room:
        shutil.copytree(directory, room, dirs_exist_ok=True)
        for name, source in (files or {}).items():
            if not isinstance(name, str) or not name or os.path.isabs(name) or '..' in Path(name).parts:
                raise kernel.ClaimError(f'unsafe heldout path: {name!r}')
            target = Path(room) / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        try:
            result = subprocess.run(command, shell=True, cwd=room, timeout=timeout,
                                    capture_output=True, text=True)
            return {'ok': result.returncode == 0, 'status': 'passed' if result.returncode == 0 else 'failed',
                    'stdout': result.stdout, 'stderr': result.stderr}
        except subprocess.TimeoutExpired:
            return {'ok': False, 'status': 'timeout'}
