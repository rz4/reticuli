"""Cache earned passing verdicts by claim bytes and judging host."""

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
    return os.environ.get("RETICULI_CACHE") or os.path.join(
        os.path.expanduser("~"), ".cache", "reticuli", "verdicts")


def _canonical(value):
    return json.dumps(value, sort_keys=True).encode("utf-8")


def _key(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def fingerprint(directory):
    """Identify the claim, concrete build, and interpreter that earned a verdict."""
    checked = kernel.verify(directory)
    if not checked["ok"]:
        raise kernel.ClaimError("claim identity has drifted")
    return {"root": checked["root"], "build": kernel.build_digest(directory),
            "platform": platform.platform(), "python": sys.version}


def _path(fingerprint_value):
    return os.path.join(_cache_dir(), _key(fingerprint_value) + ".json")


def _read(path, expected):
    try:
        with open(path, encoding="utf-8") as stream:
            entry = json.load(stream)
    except (OSError, ValueError):
        return None
    if (not isinstance(entry, dict) or entry.get("fingerprint") != expected
            or not isinstance(entry.get("verdict"), dict)
            or entry["verdict"].get("ok") is not True):
        return None
    return entry


def lookup(directory):
    """Return a previously earned passing verdict for the current build."""
    fp = fingerprint(directory)
    entry = _read(_path(fp), fp)
    return entry["verdict"] if entry else None


def remember(directory, verdict):
    """Persist a passing verdict; failures are never cache entries."""
    if not isinstance(verdict, dict) or verdict.get("ok") is not True:
        return None
    fp = fingerprint(directory)
    return _write(_path(fp), {"fingerprint": fp, "verdict": verdict,
                              "earned": _now()})


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write(path, entry):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".verdict-", dir=os.path.dirname(path))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(entry, stream, sort_keys=True)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return path


def _layer_fingerprint(layer):
    files = dict(layer["files"])
    check_name, check_source = layer["check"]
    files[check_name] = check_source
    digests = {name: kernel._hash_file(source) for name, source in files.items()}
    return ({"name": layer["name"], "files": digests,
             "gate": layer["gate"], "verdict": layer["verdict"],
             "platform": platform.platform(), "python": sys.version}, files)


def layered_audit(layers):
    """Run each layer cold or cite the passing result previously earned for it."""
    rows = []
    for layer in layers:
        fp, files = _layer_fingerprint(layer)
        path = _path(fp)
        cached = _read(path, fp)
        if cached:
            rows.append({"name": layer["name"], "ok": True, "status": "reused",
                         "reused": cached["earned"], "source": path})
            continue
        with tempfile.TemporaryDirectory(prefix="reticuli-layer-") as room:
            for name, source in files.items():
                if not name or os.path.isabs(name) or ".." in name.split("/"):
                    raise kernel.ClaimError(f"unsafe layer path: {name!r}")
                target = os.path.join(room, name)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                shutil.copyfile(source, target)
            result = kernel.run_gate(layer["gate"], room)
        ok = result["status"] == "ok"
        row = {"name": layer["name"], "ok": ok,
               "status": "earned" if ok else result["status"], "gate": result}
        rows.append(row)
        if ok:
            _write(path, {"fingerprint": fp, "verdict": {"ok": True},
                          "earned": _now()})
    return {"ok": all(row["ok"] for row in rows), "layers": rows}
