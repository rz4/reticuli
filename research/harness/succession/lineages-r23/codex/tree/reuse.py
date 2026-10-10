"""Cache passing verdicts under the exact bytes and judging host."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import sys
import tempfile
from datetime import datetime, timezone

from . import kernel


def _canonical(value):
    return json.dumps(value, sort_keys=True).encode("utf-8")


def _key(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _cache_dir():
    return os.environ.get("RETICULI_CACHE") or os.path.join(
        os.path.expanduser("~"), ".cache", "reticuli", "verdicts")


def _cache_path(key):
    return os.path.join(_cache_dir(), key + ".json")


def _read(key):
    try:
        with open(_cache_path(key), encoding="utf-8") as stream:
            row = json.load(stream)
    except (OSError, ValueError):
        return None
    return row if isinstance(row, dict) and row.get("key") == key else None


def _write(key, value):
    directory = _cache_dir()
    os.makedirs(directory, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="verdict-", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, sort_keys=True)
            stream.write("\n")
        os.replace(temporary, _cache_path(key))
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def fingerprint(directory):
    """Name the exact claim, implementation, platform, and interpreter."""
    verified = kernel.verify(directory)
    if not verified["ok"]:
        raise kernel.ClaimError("claim identity mismatch")
    return {"root": verified["root"], "build": kernel.build_digest(directory),
            "platform": platform.platform(), "python": sys.version}


def lookup(directory):
    fp = fingerprint(directory)
    row = _read(_key(fp))
    if row and row.get("fingerprint") == fp and row.get("verdict", {}).get("ok") is True:
        return row["verdict"]
    return None


def remember(directory, verdict):
    """Persist only a passing verdict. A failure cannot become borrowed trust."""
    if not isinstance(verdict, dict) or verdict.get("ok") is not True:
        return None
    fp = fingerprint(directory)
    key = _key(fp)
    _write(key, {"key": key, "fingerprint": fp, "verdict": verdict,
                 "earned_at": datetime.now(timezone.utc).isoformat()})
    return verdict


def _layer_fingerprint(layer, parents):
    files = dict(layer["files"])
    name, path = layer["check"]
    files[name] = path
    digests = {name: kernel._hash_file(path) for name, path in files.items()}
    return {"name": layer["name"], "files": digests,
            "gate": layer["gate"], "verdict": layer["verdict"],
            "parents": parents, "platform": platform.platform(),
            "python": sys.version}


def layered_audit(layers):
    """Earn each layer once, recording all trust borrowed on later calls."""
    rows = []
    parents = []
    for layer in layers:
        fp = _layer_fingerprint(layer, parents)
        key = _key(fp)
        cached = _read(key)
        if cached and cached.get("fingerprint") == fp and cached.get("verdict", {}).get("ok") is True:
            rows.append({"name": layer["name"], "ok": True,
                         "status": "reused", "reused": True,
                         "source": {"key": key, "earned_at": cached.get("earned_at"),
                                    "parents": list(parents)}})
            parents.append(key)
            continue
        with tempfile.TemporaryDirectory(prefix="reticuli-layer-audit-") as room:
            files = dict(layer["files"])
            name, path = layer["check"]
            files[name] = path
            for name, path in files.items():
                target = os.path.join(room, name)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                shutil.copyfile(path, target)
            run = kernel.run_gate(layer["gate"], room)
            ok = run["status"] == "ok"
            rows.append({"name": layer["name"], "ok": ok,
                         "status": "earned" if ok else "failed",
                         "reused": False, "source": None,
                         "gate": run["status"],
                         "quarantine": run.get("quarantine")})
        if ok:
            _write(key, {"key": key, "fingerprint": fp,
                         "verdict": {"ok": True},
                         "earned_at": datetime.now(timezone.utc).isoformat()})
            parents.append(key)
        else:
            break
    return {"ok": len(rows) == len(layers) and all(row["ok"] for row in rows),
            "layers": rows}
