"""Reuse: skipping work already earned, out loud.

A verdict cache is a promise, not a convenience. Skipped work is reported as
`reused` -- never as `earned` -- it names whose trust it leaned on and when
that trust was earned, and with nothing cached everything is redone. Cheaper
is louder, never quieter.
"""
import os
import platform
import shutil
import sys
import tempfile

from . import kernel
from ._util import copy_into, hash_bytes, read_json, write_json


def _cache_dir() -> str:
    override = os.environ.get("RETICULI_CACHE")
    if override:
        return override
    base = os.environ.get("XDG_CACHE_HOME") or \
        os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(base, "reticuli", "verdicts")


def _host() -> dict:
    return {"platform": sys.platform,
            "python": "CPython " + platform.python_version()}


def fingerprint(claim: str) -> dict:
    """What a cached verdict is keyed on: identity, bytes, and host.

    The root alone is not enough -- it names an equivalence class, and a
    verdict is about the member in front of you -- and the host matters
    because a gate can pass on one platform and fail on another.
    """
    checked = kernel.verify(claim)
    return {"root": checked["recomputed"],
            "build": kernel.build_digest(claim), **_host()}


def _key(mark: dict) -> str:
    return hash_bytes("|".join(str(mark[k]) for k in sorted(mark)))


def remember(claim: str, verdict: dict) -> dict | None:
    """Record a PASSING verdict. A failure is never remembered.

    A cached failure would be a claim about the future: the next run may be
    on repaired bytes, a fixed host, or an installed tool.
    """
    if not verdict or not verdict.get("ok"):
        return None
    mark = fingerprint(claim)
    entry = {"fingerprint": mark, "verdict": {"ok": True,
                                              "gates": verdict.get("gates")
                                              or []},
             "when": kernel._now(), "source": os.path.abspath(claim)}
    write_json(os.path.join(_cache_dir(), _key(mark) + ".json"), entry)
    return entry


def lookup(claim: str) -> dict | None:
    """A verdict earned earlier on exactly these bytes, or nothing."""
    try:
        mark = fingerprint(claim)
    except kernel.ClaimError:
        return None
    entry = read_json(os.path.join(_cache_dir(), _key(mark) + ".json"))
    if not isinstance(entry, dict) or entry.get("fingerprint") != mark:
        return None
    return entry


def _layer_key(layer: dict) -> str:
    parts = []
    for name, source in sorted((layer.get("files") or {}).items()):
        with open(source, "rb") as handle:
            parts.append(f"{name}:{hash_bytes(handle.read())}")
    check_name, check_source = layer["check"]
    with open(check_source, "rb") as handle:
        parts.append(f"{check_name}:{hash_bytes(handle.read())}")
    parts.append("gate:" + (layer.get("gate") or ""))
    parts.append("verdict:" + (layer.get("verdict") or ""))
    host = _host()
    parts.extend(f"{k}:{v}" for k, v in sorted(host.items()))
    return hash_bytes("|".join(parts))


def _earn(layer: dict) -> dict:
    """Run one layer's gate cold, in a room holding only its own bytes."""
    room = tempfile.mkdtemp(prefix="reticuli-layer-")
    try:
        for name, source in (layer.get("files") or {}).items():
            copy_into(source, os.path.join(room, name))
        check_name, check_source = layer["check"]
        copy_into(check_source, os.path.join(room, check_name))
        outcome = kernel.run_gate(layer["gate"], room, None)
        verdict = layer.get("verdict")
        if outcome["status"] == "ok" and verdict:
            with open(os.path.join(room, verdict), "w",
                      encoding="utf-8") as handle:
                handle.write("ok\n")
        return {"ok": outcome["status"] == "ok", "status": outcome["status"],
                "quarantine": outcome["quarantine"],
                "detail": (outcome["stderr"] or outcome["stdout"])[-300:]}
    finally:
        shutil.rmtree(room, ignore_errors=True)


def layered_audit(spec) -> dict:
    """Judge a stack of layers, reusing what this host already earned."""
    rows = []
    for layer in spec or []:
        key = _layer_key(layer)
        path = os.path.join(_cache_dir(), "layers", key + ".json")
        cached = read_json(path)
        if isinstance(cached, dict) and cached.get("ok"):
            rows.append({"name": layer.get("name"), "status": "reused",
                         "ok": True, "reused": True,
                         "source": cached.get("source")
                         or "this host's verdict cache",
                         "earned_at": cached.get("when"),
                         "quarantine": cached.get("quarantine")})
            continue
        outcome = _earn(layer)
        if outcome["ok"]:
            write_json(path, {"ok": True, "when": kernel._now(),
                              "source": "this host's verdict cache",
                              "quarantine": outcome["quarantine"],
                              "layer": layer.get("name")})
        rows.append({"name": layer.get("name"), "status": "earned",
                     "ok": outcome["ok"], "reused": False, "source": None,
                     "earned_at": kernel._now(),
                     "quarantine": outcome["quarantine"],
                     "detail": None if outcome["ok"] else outcome["detail"]})
    return {"ok": all(row["ok"] for row in rows) if rows else True,
            "layers": rows,
            "reused": sum(1 for row in rows if row["reused"]),
            "earned": sum(1 for row in rows if not row["reused"])}
