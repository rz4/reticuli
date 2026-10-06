"""Host-local cache of passing verdicts, including layered audits."""

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


def _cache_dir():
    return os.path.expanduser(os.environ.get(
        "RETICULI_CACHE", "~/.cache/reticuli/verdicts"))


def _key(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def _path(fingerprint):
    return os.path.join(_cache_dir(), _key(fingerprint) + ".json")


def fingerprint(directory):
    """Identify the claim, its present build, and the judging host."""
    checked = kernel.verify(directory)
    if not checked["ok"]:
        raise kernel.ClaimError("claim identity mismatch")
    return {"root": checked["root"], "build": kernel.build_digest(directory),
            "platform": platform.platform(), "python": sys.version}


def _read(fp):
    try:
        with open(_path(fp), encoding="utf-8") as source:
            entry = json.load(source)
        if entry.get("fingerprint") == fp and entry.get("verdict", {}).get("ok") is True:
            return entry
    except (OSError, ValueError, AttributeError):
        pass
    return None


def lookup(directory):
    """Return a previously passing verdict for these exact conditions."""
    entry = _read(fingerprint(directory))
    return entry["verdict"] if entry else None


def _store(fp, verdict, source=None):
    if not isinstance(verdict, dict) or verdict.get("ok") is not True:
        return None
    os.makedirs(_cache_dir(), exist_ok=True)
    entry = {"fingerprint": fp, "verdict": verdict,
             "source": source or {"when": datetime.now(timezone.utc).isoformat(),
                                   "fingerprint": _key(fp)}}
    path = _path(fp)
    fd, temporary = tempfile.mkstemp(prefix=".verdict-", dir=_cache_dir())
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as target:
            json.dump(entry, target, sort_keys=True)
            target.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return verdict


def remember(directory, verdict):
    """Remember only a successful verdict; failures never enter the cache."""
    return _store(fingerprint(directory), verdict)


def _file_digest(path):
    return kernel._hash_file(path)


def _layer_fingerprint(layer, dependencies):
    files = dict(layer["files"])
    check_name, check_path = layer["check"]
    files[check_name] = check_path
    return {"layer": layer["name"],
            "files": {name: _file_digest(path) for name, path in sorted(files.items())},
            "gate": layer["gate"], "verdict": layer["verdict"],
            "dependencies": dependencies,
            "platform": platform.platform(), "python": sys.version}


def _earn_layer(layer):
    with tempfile.TemporaryDirectory(prefix="reticuli-layer-") as room:
        files = dict(layer["files"])
        check_name, check_path = layer["check"]
        files[check_name] = check_path
        for name, source in files.items():
            destination = os.path.join(room, name)
            if os.path.isabs(name) or ".." in name.split(os.sep):
                raise kernel.ClaimError(f"unsafe layer path: {name!r}")
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            shutil.copy2(source, destination)
        result = kernel.run_gate(layer["gate"], room)
        ok = result["status"] == "ok"
        return {"ok": ok, "gate": result["status"],
                "verdict": layer["verdict"],
                "sandbox": result.get("quarantine", "none")}


def layered_audit(layers):
    """Earn or explicitly reuse each layer, binding upper layers to lower ones."""
    rows = []
    dependencies = []
    for layer in layers:
        fp = _layer_fingerprint(layer, dependencies)
        cached = _read(fp)
        if cached is not None:
            row = {"name": layer["name"], "ok": True, "status": "reused",
                   "reused": True, "source": cached["source"],
                   "verdict": cached["verdict"]}
        else:
            verdict = _earn_layer(layer)
            row = {"name": layer["name"], "ok": verdict["ok"],
                   "status": "earned" if verdict["ok"] else "failed",
                   "reused": False, "verdict": verdict}
            if verdict["ok"]:
                _store(fp, verdict, {"when": datetime.now(timezone.utc).isoformat(),
                                     "fingerprint": _key(fp),
                                     "depends_on": list(dependencies)})
        rows.append(row)
        dependencies.append(_key(fp))
        if not row["ok"]:
            break
    return {"ok": len(rows) == len(layers) and all(row["ok"] for row in rows),
            "layers": rows}
