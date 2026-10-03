"""Cache earned verdicts for one claim build on one judging host.

The cache is residue under ``.reticuli``. It cannot change claim identity.
Only successful verdicts are eligible for reuse.
"""

from __future__ import annotations

import json
import os
import platform
import sys

from . import kernel
from ._util import write_json


_CACHE = "verdict-cache.json"


def fingerprint(directory):
    """Describe the exact claim, build, and host that earned a verdict."""
    checked = kernel.verify(directory)
    if not checked["ok"]:
        raise kernel.ClaimError("claim identity mismatch")
    return {
        "root": checked["root"],
        "build": kernel.build_digest(directory),
        "platform": platform.platform(),
        "python": f"{sys.implementation.name} {platform.python_version()}",
    }


def _path(directory):
    return os.path.join(directory, kernel.STORE, _CACHE)


def lookup(directory):
    """Return a matching passing verdict, or ``None`` on a cache miss."""
    key = fingerprint(directory)
    try:
        with open(_path(directory), encoding="utf-8") as stream:
            cached = json.load(stream)
    except (OSError, UnicodeError, ValueError):
        return None
    if (isinstance(cached, dict) and cached.get("fingerprint") == key
            and isinstance(cached.get("verdict"), dict)
            and cached["verdict"].get("ok") is True):
        return cached["verdict"]
    return None


def remember(directory, verdict):
    """Store a passing verdict; remove an old cache entry after a failure."""
    path = _path(directory)
    if not isinstance(verdict, dict) or verdict.get("ok") is not True:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
        return False
    write_json(path, {"fingerprint": fingerprint(directory), "verdict": verdict})
    return True
