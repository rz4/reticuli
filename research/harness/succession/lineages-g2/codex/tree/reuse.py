"""Cache earned verdicts under exact claim, build, and host fingerprints."""

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


def _host():
    return {"platform": platform.platform(), "python": sys.version}


def fingerprint(directory):
    """Identify exactly the claim, generated build, and judging host."""
    verified = kernel.verify(directory)
    if not verified["ok"]:
        raise kernel.ClaimError("claim identity mismatch")
    return {"root": verified["root"], "build": kernel.build_digest(directory),
            **_host()}


def _cache_dir():
    return os.path.realpath(os.environ.get("RETICULI_CACHE") or
                            os.path.join(os.path.expanduser("~"), ".cache",
                                         "reticuli", "verdicts"))


def _key(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode("utf-8")).hexdigest()


def _read(key):
    path = os.path.join(_cache_dir(), key + ".json")
    try:
        with open(path, encoding="utf-8") as stream:
            value = json.load(stream)
        return value if isinstance(value, dict) else None
    except (OSError, ValueError):
        return None


def _write(key, value):
    folder = _cache_dir()
    os.makedirs(folder, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=folder,
                                         prefix=".verdict-", delete=False) as stream:
            temporary = stream.name
            json.dump(value, stream, sort_keys=True)
        os.replace(temporary, os.path.join(folder, key + ".json"))
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def lookup(directory):
    """Return a previously earned passing verdict for these exact bytes."""
    fp = fingerprint(directory)
    entry = _read(_key({"kind": "claim", "fingerprint": fp}))
    if entry and entry.get("fingerprint") == fp and entry.get("verdict", {}).get("ok") is True:
        return entry
    return None


def remember(directory, verdict):
    """Persist only a passing verdict; failure must always be rechecked."""
    if not isinstance(verdict, dict) or verdict.get("ok") is not True:
        return None
    fp = fingerprint(directory)
    entry = {"fingerprint": fp, "verdict": verdict, "when": _now()}
    _write(_key({"kind": "claim", "fingerprint": fp}), entry)
    return entry


def _layer_fingerprint(layer):
    files = dict(layer["files"])
    check_name, check_path = layer["check"]
    files[check_name] = check_path
    digests = {name: kernel._hash_file(path) for name, path in files.items()}
    return {"name": layer["name"], "files": digests, "gate": layer["gate"],
            "verdict": layer["verdict"], **_host()}


def layered_audit(layers):
    """Run each uncached layer and label every carried verdict honestly."""
    rows = []
    for layer in layers:
        fp = _layer_fingerprint(layer)
        key = _key({"kind": "layer", "fingerprint": fp})
        cached = _read(key)
        if cached and cached.get("fingerprint") == fp and cached.get("ok") is True:
            rows.append({"name": layer["name"], "ok": True, "status": "reused",
                         "reused": True, "source": cached["source"]})
            continue

        with tempfile.TemporaryDirectory(prefix="reticuli-layered-") as room:
            sources = dict(layer["files"])
            check_name, check_path = layer["check"]
            sources[check_name] = check_path
            for name, source in sources.items():
                if not isinstance(name, str) or os.path.isabs(name) or ".." in name.split("/"):
                    raise kernel.ClaimError("invalid layer file name")
                target = os.path.join(room, name)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                shutil.copy2(source, target)
            try:
                done = subprocess.run(layer["gate"], shell=True, cwd=room,
                                      capture_output=True, text=True, timeout=120)
                ok = done.returncode == 0
                detail = done.stderr if not ok else ""
            except (OSError, subprocess.TimeoutExpired) as exc:
                ok, detail = False, str(exc)

        row = {"name": layer["name"], "ok": ok,
               "status": "earned" if ok else "failed", "reused": False}
        if ok:
            source = {"name": layer["name"], "verdict": layer["verdict"],
                      "when": _now(), "fingerprint": key}
            row["source"] = source
            _write(key, {"fingerprint": fp, "ok": True, "source": source})
        else:
            row["detail"] = detail
        rows.append(row)
    return {"ok": all(row["ok"] for row in rows), "layers": rows}
