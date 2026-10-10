"""Cache earned verdicts under the exact claim, build, and judging host."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

from . import kernel


def _canonical(value):
    return json.dumps(value, sort_keys=True).encode("utf-8")


def _cache_dir():
    return os.path.expanduser(os.environ.get("RETICULI_CACHE", "~/.cache/reticuli/verdicts"))


def fingerprint(directory):
    """Identify the sealed claim, its present implementation, and this judge."""
    verified = kernel.verify(directory)
    if not verified["ok"]:
        raise kernel.ClaimError("claim identity mismatch")
    return {
        "root": verified["root"],
        "build": kernel.build_digest(directory),
        "platform": platform.platform(),
        "python": f"{sys.implementation.name} {sys.version.split()[0]} ({sys.executable})",
    }


def _path(key):
    digest = hashlib.sha256(_canonical(key)).hexdigest()
    return os.path.join(_cache_dir(), digest + ".json")


def _save(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".verdict-", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, sort_keys=True)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _passing(verdict):
    return isinstance(verdict, dict) and verdict.get("ok") is True


def remember(directory, verdict):
    """Remember only passing verdicts; return whether one was stored."""
    if not _passing(verdict):
        return False
    key = fingerprint(directory)
    _save(_path(key), {"fingerprint": key, "verdict": verdict,
                       "when": datetime.now(timezone.utc).isoformat(),
                       "source": os.path.realpath(directory)})
    return True


def lookup(directory):
    key = fingerprint(directory)
    try:
        with open(_path(key), encoding="utf-8") as stream:
            row = json.load(stream)
    except (OSError, ValueError):
        return None
    if not isinstance(row, dict) or row.get("fingerprint") != key or not _passing(row.get("verdict")):
        return None
    return row


def _layer_key(layer):
    files = dict(layer["files"])
    check_name, check_path = layer["check"]
    files[check_name] = check_path
    digests = {}
    for name, path in files.items():
        digests[name] = kernel._hash_file(path)
    return {"name": layer["name"], "files": digests, "gate": layer["gate"],
            "verdict": layer.get("verdict"), "platform": platform.platform(),
            "python": f"{sys.implementation.name} {sys.version.split()[0]} ({sys.executable})"}


def layered_audit(layers):
    """Run each layer cold or report the source of a cached passing verdict."""
    rows = []
    for layer in layers:
        key = _layer_key(layer)
        path = _path({"layer": key})
        cached = None
        try:
            with open(path, encoding="utf-8") as stream:
                cached = json.load(stream)
        except (OSError, ValueError):
            pass
        if isinstance(cached, dict) and cached.get("fingerprint") == key and _passing(cached.get("verdict")):
            rows.append({"name": layer["name"], "status": "reused", "ok": True,
                         "reused": cached.get("when"), "source": cached.get("source") or path,
                         "verdict": cached["verdict"]})
            continue
        with tempfile.TemporaryDirectory(prefix="reticuli-layer-") as room:
            files = dict(layer["files"])
            check_name, check_path = layer["check"]
            files[check_name] = check_path
            for name, source in files.items():
                target = os.path.join(room, name)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                shutil.copyfile(source, target)
            done = subprocess.run(layer["gate"], shell=True, cwd=room,
                                  capture_output=True, text=True)
            ok = done.returncode == 0
            verdict = {"ok": ok, "returncode": done.returncode,
                       "stdout": done.stdout, "stderr": done.stderr}
        if ok:
            _save(path, {"fingerprint": key, "verdict": verdict,
                         "when": datetime.now(timezone.utc).isoformat(),
                         "source": os.path.realpath(check_path)})
        rows.append({"name": layer["name"], "status": "earned" if ok else "failed",
                     "ok": ok, "verdict": verdict})
    return {"ok": all(row["ok"] for row in rows), "layers": rows}
