"""Host-bound verdict cache and honest layered audit results."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

from . import kernel


def _cache_dir():
    return os.environ.get("RETICULI_CACHE", os.path.join(os.path.expanduser("~"), ".cache", "reticuli", "verdicts"))


def _key(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode("utf-8")).hexdigest()


def fingerprint(directory):
    """Name a verdict by claim identity, concrete build, and judging host."""
    verified = kernel.verify(directory)
    if not verified["ok"]:
        raise kernel.ClaimError("claim identity mismatch")
    return {"root": verified["root"], "build": kernel.build_digest(directory),
            "platform": platform.platform(), "python": sys.version}


def _path(fingerprint_value):
    return os.path.join(_cache_dir(), _key(fingerprint_value) + ".json")


def lookup(directory):
    """Return an earned passing verdict for exactly this fingerprint."""
    fp = fingerprint(directory)
    try:
        with open(_path(fp), encoding="utf-8") as stream:
            saved = json.load(stream)
    except (OSError, ValueError):
        return None
    if saved.get("fingerprint") != fp or not saved.get("verdict", {}).get("ok"):
        return None
    return saved


def remember(directory, verdict):
    """Persist only a successful verdict; failures cannot poison the cache."""
    if not isinstance(verdict, dict) or verdict.get("ok") is not True:
        return None
    fp = fingerprint(directory)
    saved = {"fingerprint": fp, "verdict": verdict,
             "earned_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    path = _path(fp)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(saved, stream, sort_keys=True)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return saved


def _layer_fingerprint(spec):
    files = {}
    for name, path in {**spec["files"], spec["check"][0]: spec["check"][1]}.items():
        files[name] = kernel._hash_file(path)
    return {"files": files, "gate": spec["gate"],
            "platform": platform.platform(), "python": sys.version}


def layered_audit(specs):
    """Run each layer cold once, then identify every cached verdict as reused."""
    rows = []
    os.makedirs(_cache_dir(), exist_ok=True)
    for spec in specs:
        fp = _layer_fingerprint(spec)
        path = os.path.join(_cache_dir(), "layer-" + _key(fp) + ".json")
        saved = None
        try:
            with open(path, encoding="utf-8") as stream:
                saved = json.load(stream)
        except (OSError, ValueError):
            pass
        if saved and saved.get("fingerprint") == fp and saved.get("ok") is True:
            rows.append({"name": spec["name"], "ok": True, "status": "reused",
                         "reused": saved["earned_at"], "source": saved["source"]})
            continue
        with tempfile.TemporaryDirectory(prefix="reticuli-layer-") as room:
            for name, source in {**spec["files"], spec["check"][0]: spec["check"][1]}.items():
                if os.path.isabs(name) or ".." in name.split("/"):
                    raise kernel.ClaimError("unsafe layer path")
                destination = os.path.join(room, name)
                os.makedirs(os.path.dirname(destination), exist_ok=True)
                with open(source, "rb") as input_stream, open(destination, "wb") as output_stream:
                    output_stream.write(input_stream.read())
            done = subprocess.run(spec["gate"], shell=True, cwd=room,
                                  capture_output=True, text=True, timeout=120)
            ok = done.returncode == 0
        row = {"name": spec["name"], "ok": ok,
               "status": "earned" if ok else "failed"}
        rows.append(row)
        if ok:
            saved = {"fingerprint": fp, "ok": True,
                     "earned_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                     "source": {"layer": spec["name"], "files": fp["files"],
                                "platform": fp["platform"], "python": fp["python"]}}
            with open(path, "w", encoding="utf-8") as stream:
                json.dump(saved, stream, sort_keys=True)
    return {"ok": all(row["ok"] for row in rows), "layers": rows}
