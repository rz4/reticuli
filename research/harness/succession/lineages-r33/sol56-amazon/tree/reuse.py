"""Host-local reuse of passing verdicts.

A cached verdict is evidence about one exact claim realization on one exact
runtime. Consequently its key includes claim/input bytes, command, platform,
and Python. Failed verdicts are never written: absence means redo the work.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import platform
import shutil
import stat
import sys
import tempfile
from collections.abc import Mapping, Sequence
from typing import Any

from . import kernel

_CACHE_VERSION = 1


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True).encode("utf-8")


def _cache_root() -> str:
    configured = os.environ.get("RETICULI_CACHE")
    if configured:
        return os.path.abspath(os.path.expanduser(configured))
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Caches")
    else:
        base = os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache"))
    return os.path.join(base, "reticuli")


def _when() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _runtime() -> tuple[str, str]:
    host = "%s/%s/%s" % (platform.system().lower() or sys.platform,
                           platform.machine(), platform.release())
    python = "%s %s" % (platform.python_implementation(), platform.python_version())
    return host, python


def fingerprint(d: str | os.PathLike[str]) -> dict[str, str]:
    """Return the complete key for reusing a verdict about sealed claim *d*."""
    directory = os.path.abspath(os.fspath(d))
    verification = kernel.verify(directory)
    if not verification.get("ok"):
        raise kernel.ClaimError("cannot fingerprint a claim whose identity does not hold")
    host, python = _runtime()
    return {"root": str(verification["root"]),
            "build": str(kernel.build_digest(directory)),
            "platform": host, "python": python}


def _verdict_path(fp: Mapping[str, str]) -> str:
    key = hashlib.sha256(_canonical(dict(fp))).hexdigest()
    return os.path.join(_cache_root(), "verdicts", key + ".json")


def _atomic_json(path: str, value: Any) -> None:
    parent = os.path.dirname(path); os.makedirs(parent, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".reuse-", dir=parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, sort_keys=True); stream.write("\n"); stream.flush()
            try: os.fsync(stream.fileno())
            except OSError: pass
        os.replace(temporary, path); temporary = ""
    finally:
        if temporary:
            try: os.unlink(temporary)
            except OSError: pass


def _passing(verdict: Any) -> bool:
    return isinstance(verdict, Mapping) and verdict.get("ok") is True


def remember(d: str | os.PathLike[str], verdict: Mapping[str, Any]) -> str | None:
    """Remember a passing verdict. A failure is deliberately a no-op."""
    if not _passing(verdict): return None
    fp = fingerprint(d); path = _verdict_path(fp)
    record = {"version": _CACHE_VERSION, "fingerprint": fp,
              "verdict": dict(verdict), "earned": _when()}
    try: _atomic_json(path, record)
    except (OSError, TypeError, ValueError) as exc:
        raise kernel.ClaimError("cannot remember reusable verdict: " + str(exc)) from None
    return path


def lookup(d: str | os.PathLike[str]) -> dict[str, Any] | None:
    """Return a matching passing verdict, or ``None`` when work must be redone."""
    fp = fingerprint(d); path = _verdict_path(fp)
    try:
        with open(path, encoding="utf-8") as stream: record = json.load(stream)
    except (OSError, ValueError, TypeError): return None
    if (not isinstance(record, dict) or record.get("version") != _CACHE_VERSION
            or record.get("fingerprint") != fp or not _passing(record.get("verdict"))):
        return None
    return dict(record["verdict"])


def _relative(name: Any, label: str) -> str:
    if not isinstance(name, str) or not name or "\0" in name or os.path.isabs(name):
        raise kernel.ClaimError(label + " must be a non-empty relative path")
    portable = name.replace("\\", "/")
    if ".." in portable.split("/"): raise kernel.ClaimError(label + " escapes the audit room")
    return portable


def _source_digest(path: Any) -> str:
    try:
        value = os.path.abspath(os.fspath(path)); info = os.lstat(value)
        if not stat.S_ISREG(info.st_mode): raise OSError("not a regular file")
        digest = hashlib.sha256()
        with open(value, "rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""): digest.update(block)
        return digest.hexdigest()
    except (OSError, TypeError, ValueError) as exc:
        raise kernel.ClaimError("cannot read layered-audit input: " + str(exc)) from None


def _layer_description(layer: Mapping[str, Any]) -> tuple[dict[str, Any], list[tuple[str, str]]]:
    name = layer.get("name")
    if not isinstance(name, str) or not name: raise kernel.ClaimError("audit layer requires a name")
    files = layer.get("files", {})
    if not isinstance(files, Mapping): raise kernel.ClaimError("audit layer files must be a mapping")
    copies: list[tuple[str, str]] = []; members: list[list[str]] = []
    for destination, source in files.items():
        relative = _relative(destination, "layer file"); source_path = os.path.abspath(os.fspath(source))
        copies.append((relative, source_path)); members.append([relative, _source_digest(source_path)])
    check = layer.get("check")
    if (not isinstance(check, Sequence) or isinstance(check, (str, bytes)) or len(check) != 2):
        raise kernel.ClaimError("audit layer check must be a (name, source) pair")
    check_name = _relative(check[0], "layer check"); check_source = os.path.abspath(os.fspath(check[1]))
    copies.append((check_name, check_source))
    gate = layer.get("gate"); verdict = _relative(layer.get("verdict"), "layer verdict")
    if not isinstance(gate, str) or not gate: raise kernel.ClaimError("audit layer requires a gate command")
    host, python = _runtime()
    description = {"version": _CACHE_VERSION, "name": name, "files": sorted(members),
                   "check": [check_name, _source_digest(check_source)], "gate": gate,
                   "verdict": verdict, "platform": host, "python": python}
    return description, copies


def _layer_path(description: Mapping[str, Any]) -> tuple[str, str]:
    key = hashlib.sha256(_canonical(description)).hexdigest()
    return key, os.path.join(_cache_root(), "layers", key + ".json")


def _cached_layer(path: str, description: Mapping[str, Any]) -> dict[str, Any] | None:
    try:
        with open(path, encoding="utf-8") as stream: record = json.load(stream)
    except (OSError, ValueError, TypeError): return None
    if (not isinstance(record, dict) or record.get("version") != _CACHE_VERSION
            or record.get("description") != description or record.get("ok") is not True): return None
    return record


def _copy_files(room: str, copies: list[tuple[str, str]]) -> None:
    seen: dict[str, str] = {}
    for relative, source in copies:
        digest = _source_digest(source)
        if relative in seen:
            if seen[relative] != digest: raise kernel.ClaimError("two different inputs target " + relative)
            continue
        seen[relative] = digest
        target = os.path.abspath(os.path.join(room, relative.replace("/", os.sep)))
        if os.path.commonpath((room, target)) != room: raise kernel.ClaimError("layer file escapes audit room")
        os.makedirs(os.path.dirname(target), exist_ok=True); shutil.copyfile(source, target)


def _earn_layer(layer: Mapping[str, Any], copies: list[tuple[str, str]]) -> dict[str, Any]:
    parent = tempfile.mkdtemp(prefix="reticuli-layer-"); room = os.path.join(parent, "room"); os.makedirs(room)
    try:
        _copy_files(room, copies)
        result = kernel.run_gate(str(layer["gate"]), room)
        ok = result.get("status") == "ok"
        row = {"name": layer["name"], "ok": ok,
               "status": "earned" if ok else str(result.get("status", "failed")),
               "reused": False, "verdict": _relative(layer.get("verdict"), "layer verdict")}
        for key in ("returncode", "stdout", "stderr", "seconds", "quarantine"):
            if key in result: row[key] = result[key]
        return row
    finally: shutil.rmtree(parent, ignore_errors=True)


def layered_audit(layers: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Audit layers, explicitly reporting cold ``earned`` and cached ``reused``.

    A layer has ``name``, ``files`` (room name to source path), ``check`` as a
    ``(room name, source path)`` pair, a shell ``gate``, and a symbolic
    ``verdict`` name. Passing work alone is cached by all bytes and host facts.
    """
    if not isinstance(layers, Sequence) or isinstance(layers, (str, bytes)):
        raise kernel.ClaimError("layers must be a sequence")
    rows: list[dict[str, Any]] = []
    for layer in layers:
        if not isinstance(layer, Mapping): raise kernel.ClaimError("each audit layer must be a mapping")
        description, copies = _layer_description(layer); key, path = _layer_path(description)
        cached = _cached_layer(path, description)
        if cached is not None:
            rows.append({"name": description["name"], "ok": True, "status": "reused",
                         "reused": True, "source": "local verdict cache for " + description["name"],
                         "earned_at": cached.get("earned"), "fingerprint": key,
                         "verdict": description["verdict"]})
            continue
        row = _earn_layer(layer, copies); row["fingerprint"] = key
        if row["ok"]:
            record = {"version": _CACHE_VERSION, "description": description, "ok": True,
                      "earned": _when(), "source": description["name"]}
            try: _atomic_json(path, record)
            except (OSError, TypeError, ValueError) as exc: row["cache_error"] = str(exc)
        rows.append(row)
    return {"ok": all(row.get("ok") is True for row in rows), "layers": rows}


__all__ = ["fingerprint", "layered_audit", "lookup", "remember"]
