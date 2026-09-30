"""Host-specific cache of passing claim verdicts.

The cache is residue: its contents never participate in claim identity.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import sys

from . import kernel
from ._util import safe_path, write_json


def fingerprint(directory):
    """Identify the exact claim bytes and interpreter that earned a verdict."""
    checked = kernel.verify(directory)
    if not checked["ok"]:
        raise kernel.ClaimError("claim identity does not match its seal")
    return {
        "root": checked["root"],
        "build": kernel.build_digest(directory),
        "platform": platform.platform(),
        "python": sys.version,
    }


def _path(directory, key):
    digest = hashlib.sha256(json.dumps(key, sort_keys=True).encode("utf-8")).hexdigest()
    return safe_path(directory, ".reticuli/reuse/" + digest + ".json")


def remember(directory, verdict):
    """Cache a passing verdict; a failure can never become reusable evidence."""
    key = fingerprint(directory)
    path = _path(directory, key)
    if not isinstance(verdict, dict) or verdict.get("ok") is not True:
        if os.path.exists(path):
            os.unlink(path)
        return None
    write_json(path, {"fingerprint": key, "verdict": verdict})
    return verdict


def lookup(directory):
    """Return a cached passing verdict for the current build and host, if any."""
    key = fingerprint(directory)
    path = _path(directory, key)
    try:
        with open(path, encoding="utf-8") as stream:
            entry = json.load(stream)
    except (OSError, ValueError):
        return None
    if not isinstance(entry, dict) or entry.get("fingerprint") != key:
        return None
    verdict = entry.get("verdict")
    return verdict if isinstance(verdict, dict) and verdict.get("ok") is True else None
