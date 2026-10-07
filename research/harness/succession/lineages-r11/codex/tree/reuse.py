"""Cache earned passing verdicts by the exact build and judging host."""

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
from ._kernel import core


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, allow_nan=False).encode("utf-8")


def _cache_dir() -> str:
    return os.environ.get("RETICULI_CACHE", os.path.join(tempfile.gettempdir(), "reticuli-verdicts"))


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fingerprint(directory: str) -> dict[str, str]:
    """Name the identity, concrete build, platform, and interpreter."""
    verified = kernel.verify(directory)
    if not verified["ok"]:
        raise kernel.ClaimError("claim identity does not verify")
    return {"root": verified["root"], "build": kernel.build_digest(directory),
            "platform": platform.platform(), "python": sys.version}


def _key(fingerprint_value: dict) -> str:
    return hashlib.sha256(_canonical(fingerprint_value)).hexdigest()


def _path(key: str) -> str:
    return os.path.join(_cache_dir(), key + ".json")


def _read(key: str) -> dict | None:
    try:
        with open(_path(key), encoding="utf-8") as stream:
            record = json.load(stream)
        if (record.get("key") == key and isinstance(record.get("verdict"), dict)
                and record["verdict"].get("ok") is True):
            return record
    except (OSError, ValueError, AttributeError):
        pass
    return None


def _write(key: str, verdict: dict, source: dict) -> None:
    os.makedirs(_cache_dir(), exist_ok=True)
    core._write_json(_path(key), {"key": key, "verdict": verdict, "source": source})


def lookup(directory: str) -> dict | None:
    """Return a previously earned passing verdict for these exact bytes."""
    record = _read(_key(fingerprint(directory)))
    return record["verdict"] if record else None


def remember(directory: str, verdict: dict) -> None:
    """Remember passing verdicts only; failure never becomes a shortcut."""
    if not isinstance(verdict, dict) or verdict.get("ok") is not True:
        return
    fp = fingerprint(directory)
    _write(_key(fp), verdict, {"when": _stamp(), "fingerprint": fp})


def _layer_key(layer: dict) -> str:
    files = dict(layer["files"])
    check_name, check_path = layer["check"]
    files[check_name] = check_path
    digests = {name: core._hash_file(path) for name, path in sorted(files.items())}
    value = {"files": digests, "gate": layer["gate"],
             "verdict": layer["verdict"], "platform": platform.platform(),
             "python": sys.version}
    return _key(value)


def _run_layer(layer: dict) -> dict:
    with tempfile.TemporaryDirectory(prefix="reticuli-layer-audit-") as room:
        files = dict(layer["files"])
        check_name, check_path = layer["check"]
        files[check_name] = check_path
        for name, path in files.items():
            core._copy_into(path, core._safe(room, name))
        try:
            done = subprocess.run(layer["gate"], shell=True, cwd=room,
                                  capture_output=True, text=True, timeout=120,
                                  check=False)
            ok = done.returncode == 0
            detail = done.stderr
        except subprocess.TimeoutExpired:
            ok, detail = False, "gate timed out"
    return {"ok": ok, "detail": detail}


def layered_audit(layers: list[dict]) -> dict:
    """Earn each layer cold or explicitly cite its cached passing verdict."""
    rows = []
    for layer in layers:
        key = _layer_key(layer)
        cached = _read(key)
        if cached is not None:
            rows.append({"name": layer["name"], "ok": True, "status": "reused",
                         "reused": True, "source": cached["source"]})
            continue
        outcome = _run_layer(layer)
        row = {"name": layer["name"], "ok": outcome["ok"],
               "status": "earned" if outcome["ok"] else "failed",
               "detail": outcome["detail"]}
        rows.append(row)
        if outcome["ok"]:
            _write(key, {"ok": True}, {"when": _stamp(), "layer": layer["name"],
                                       "trust": "local gate execution", "key": key})
    return {"ok": all(row["ok"] for row in rows), "layers": rows}
