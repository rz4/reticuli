"""Cache earned verdicts and report their provenance when reusing them."""

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
    return os.path.abspath(os.path.expanduser(
        os.environ.get("RETICULI_CACHE", os.path.join("~", ".cache", "reticuli", "verdicts"))))


def _cache_file(key):
    return os.path.join(_cache_dir(), hashlib.sha256(_canonical(key)).hexdigest() + ".json")


def _read(key):
    try:
        with open(_cache_file(key), encoding="utf-8") as stream:
            row = json.load(stream)
        return row if row.get("key") == key and row.get("verdict", {}).get("ok") is True else None
    except (OSError, ValueError, AttributeError):
        return None


def _write(key, verdict, *, source=None):
    if verdict.get("ok") is not True:
        return None
    folder = _cache_dir()
    os.makedirs(folder, exist_ok=True)
    row = {"key": key, "verdict": verdict, "earned_at": datetime.now(timezone.utc).isoformat(),
           "source": source or "local audit"}
    fd, temporary = tempfile.mkstemp(prefix=".verdict-", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(row, stream, sort_keys=True)
            stream.write("\n")
        os.replace(temporary, _cache_file(key))
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return row


def fingerprint(directory):
    """Identify the sealed claim, its concrete build, and this judging host."""
    checked = kernel.verify(directory)
    if not checked["ok"]:
        raise kernel.ClaimError("claim identity does not match its seal")
    return {"root": checked["root"], "build": kernel.build_digest(directory),
            "platform": platform.platform(), "python": sys.version}


def lookup(directory):
    """Return a previously earned passing verdict, if it still applies."""
    row = _read({"kind": "claim", **fingerprint(directory)})
    return row["verdict"] if row else None


def remember(directory, verdict):
    """Store a passing verdict; failed or incomplete results are never cached."""
    return _write({"kind": "claim", **fingerprint(directory)}, verdict,
                  source=os.path.realpath(directory))


def _layer_key(layer, dependency):
    files = dict(layer["files"])
    check_name, check_path = layer["check"]
    files[check_name] = check_path
    hashes = {}
    for name, path in sorted(files.items()):
        with open(path, "rb") as stream:
            hashes[name] = hashlib.sha256(stream.read()).hexdigest()
    return {"kind": "layer", "name": layer["name"], "files": hashes,
            "gate": layer["gate"], "verdict": layer["verdict"],
            "dependency": dependency, "platform": platform.platform(),
            "python": sys.version}


def layered_audit(layers):
    """Earn each layer's gate cold, or explicitly cite its cached verdict."""
    rows = []
    dependency = None
    for layer in layers:
        key = _layer_key(layer, dependency)
        digest = hashlib.sha256(_canonical(key)).hexdigest()
        cached = _read(key)
        if cached:
            row = {"name": layer["name"], "status": "reused", "ok": True,
                   "reused": cached["earned_at"], "source": cached["source"],
                   "trust": dependency}
        else:
            with tempfile.TemporaryDirectory(prefix="reticuli-layer-") as room:
                files = dict(layer["files"])
                check_name, check_path = layer["check"]
                files[check_name] = check_path
                for name, path in files.items():
                    target = os.path.join(room, name)
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    shutil.copyfile(path, target)
                try:
                    result = subprocess.run(layer["gate"], shell=True, cwd=room,
                                            capture_output=True, text=True, timeout=120)
                    ok = result.returncode == 0
                    detail = result.stderr if not ok else ""
                except subprocess.TimeoutExpired:
                    ok, detail = False, "gate timed out"
            row = {"name": layer["name"], "status": "earned" if ok else "failed",
                   "ok": ok, "reused": False, "source": "local gate",
                   "trust": dependency}
            if detail:
                row["detail"] = detail
            if ok:
                _write(key, {"ok": True, "gate": layer["gate"]},
                       source=f"{layer['name']} gate on {platform.node()}")
        rows.append(row)
        if not row["ok"]:
            break
        dependency = digest
    return {"ok": len(rows) == len(layers) and all(row["ok"] for row in rows),
            "layers": rows}
