"""Host-bound verdict cache and explicit accounting for layered reuse."""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile

from . import kernel


def _canonical(value):
    return json.dumps(value, sort_keys=True).encode("utf-8")


def _cache_dir():
    return os.environ.get("RETICULI_CACHE", os.path.join(os.path.expanduser("~"),
                                                         ".cache", "reticuli", "verdicts"))


def _path(fingerprint):
    key = hashlib.sha256(_canonical(fingerprint)).hexdigest()
    return os.path.join(_cache_dir(), key + ".json")


def _host():
    return {"platform": platform.platform(), "python": sys.version}


def fingerprint(directory):
    """Key a verdict by sealed identity, concrete build, and judging host."""
    verified = kernel.verify(directory)
    if not verified["ok"]:
        raise kernel.ClaimError("claim identity does not hold")
    return {"root": verified["root"], "build": kernel.build_digest(directory),
            **_host()}


def _passing(verdict):
    return (isinstance(verdict, dict) and verdict.get("ok") is True
            and all(isinstance(gate, dict) and gate.get("status") == "ok"
                    for gate in verdict.get("gates", [])))


def remember(directory, verdict):
    """Persist only passing verdicts; return whether one was recorded."""
    if not _passing(verdict):
        return False
    fp = fingerprint(directory)
    path = _path(fp)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    record = {"fingerprint": fp, "verdict": verdict,
              "earned_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=os.path.dirname(path),
                                     delete=False) as stream:
        temporary = stream.name
        json.dump(record, stream, sort_keys=True)
    os.replace(temporary, path)
    return True


def lookup(directory):
    """Return a previously earned verdict only for the current fingerprint."""
    fp = fingerprint(directory)
    try:
        with open(_path(fp), encoding="utf-8") as stream:
            record = json.load(stream)
    except (OSError, ValueError):
        return None
    if record.get("fingerprint") != fp or not _passing(record.get("verdict")):
        return None
    return record["verdict"]


def _hash_file(path):
    return kernel._hash_file(path)


def _layer_fingerprint(layer, parent):
    name, check_path = layer["check"]
    files = dict(layer["files"])
    files[name] = check_path
    return {"name": layer["name"], "files": {name: _hash_file(path)
             for name, path in sorted(files.items())}, "gate": layer["gate"],
            "verdict": layer["verdict"], "parent": parent, **_host()}


def layered_audit(layers):
    """Earn each layer cold or report the exact earlier verdict it reuses."""
    rows = []
    parent = None
    for layer in layers:
        fp = _layer_fingerprint(layer, parent)
        path = _path(fp)
        prior = None
        try:
            with open(path, encoding="utf-8") as stream:
                prior = json.load(stream)
        except (OSError, ValueError):
            pass
        if (isinstance(prior, dict) and prior.get("fingerprint") == fp
                and prior.get("ok") is True):
            row = {"name": layer["name"], "status": "reused", "ok": True,
                   "reused": prior["earned_at"], "source": prior["source"]}
        else:
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
            row = {"name": layer["name"], "status": "earned" if ok else "failed",
                   "ok": ok, "stdout": done.stdout, "stderr": done.stderr}
            if ok:
                earned_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
                source = {"layer": layer["name"], "parent": parent}
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as stream:
                    json.dump({"fingerprint": fp, "ok": True,
                               "earned_at": earned_at, "source": source}, stream)
        rows.append(row)
        if not row["ok"]:
            break
        parent = hashlib.sha256(_canonical(fp)).hexdigest()
    return {"ok": len(rows) == len(layers) and all(row["ok"] for row in rows),
            "layers": rows}
