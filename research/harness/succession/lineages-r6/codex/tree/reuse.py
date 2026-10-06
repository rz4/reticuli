"""Content keyed verdict reuse with explicit provenance."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from typing import Any

from . import kernel


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True).encode("utf-8")


def _key(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _cache() -> str:
    return os.path.expanduser(os.environ.get("RETICULI_CACHE", "~/.cache/reticuli/verdicts"))


def _path(kind: str, key: str) -> str:
    return os.path.join(_cache(), kind, key + ".json")


def _read(path: str) -> dict[str, Any] | None:
    try:
        with open(path, encoding="utf-8") as stream:
            value = json.load(stream)
        return value if isinstance(value, dict) else None
    except (OSError, ValueError):
        return None


def _write(path: str, value: dict[str, Any]) -> None:
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


def _host() -> dict[str, str]:
    return {"platform": platform.platform(), "python": sys.version}


def fingerprint(directory: str) -> dict[str, str]:
    verified = kernel.verify(directory)
    if not verified["ok"]:
        raise kernel.ClaimError("claim identity mismatch")
    return {"root": verified["root"], "build": kernel.build_digest(directory),
            **_host()}


def lookup(directory: str) -> dict[str, Any] | None:
    fp = fingerprint(directory)
    item = _read(_path("claims", _key(fp)))
    if item and item.get("fingerprint") == fp and item.get("verdict", {}).get("ok") is True:
        return item["verdict"]
    return None


def remember(directory: str, verdict: dict[str, Any]) -> bool:
    if verdict.get("ok") is not True:
        return False
    fp = fingerprint(directory)
    _write(_path("claims", _key(fp)), {"fingerprint": fp, "verdict": verdict,
                                      "earned_at": datetime.now(timezone.utc).isoformat()})
    return True


def _layer_fingerprint(layer: dict[str, Any]) -> dict[str, Any]:
    files = dict(layer["files"])
    check_name, check_path = layer["check"]
    if check_name in files:
        raise ValueError("check path duplicates a layer file")
    files[check_name] = check_path
    digests = {name: kernel._hash_file(path) for name, path in files.items()}
    return {"files": digests, "gate": layer["gate"], **_host()}


def layered_audit(layers: list[dict[str, Any]]) -> dict[str, Any]:
    """Earn each layer's gate, or identify the cached evidence it relies on."""
    rows: list[dict[str, Any]] = []
    for layer in layers:
        fp = _layer_fingerprint(layer)
        key = _key(fp)
        saved = _read(_path("layers", key))
        if saved and saved.get("fingerprint") == fp and saved.get("ok") is True:
            rows.append({"name": layer["name"], "ok": True, "status": "reused",
                         "reused": True, "source": saved["source"]})
            continue
        check_name, check_path = layer["check"]
        with tempfile.TemporaryDirectory(prefix="reticuli-layer-audit-") as room:
            for name, path in {**layer["files"], check_name: check_path}.items():
                target = kernel._safe(room, name)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                shutil.copyfile(path, target)
            outcome = kernel.run_gate(layer["gate"], room)
            ok = outcome["status"] == "ok"
        source = {"layer": layer["name"], "fingerprint": key,
                  "earned_at": datetime.now(timezone.utc).isoformat()}
        rows.append({"name": layer["name"], "ok": ok,
                     "status": "earned" if ok else "failed", "reused": False,
                     "source": source, "gate": outcome})
        if ok:
            _write(_path("layers", key), {"fingerprint": fp, "ok": True,
                                          "source": source})
    return {"ok": all(row["ok"] for row in rows), "layers": rows}
