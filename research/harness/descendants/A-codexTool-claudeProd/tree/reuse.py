"""The verdict cache: skipping work already earned, and saying so.

Reuse is a PROMISE, not a convenience.  A layered audit that skips work
already earned must say `reused` and never `earned`, must name whose trust it
leaned on and when that trust was earned, and must redo everything when
nothing is cached.  Cheaper is louder, never quieter: a reader who cannot
tell a re-earned verdict from a remembered one has lost the only distinction
an audit exists to make.

A verdict is keyed by **root + build digest + platform + interpreter**.  The
root alone is not enough (it deliberately ignores the implementation), and
the host belongs in the key because a verdict is a fact about an execution.

**A failure is never remembered.**  A cached "no" would turn a transient
environment problem into a permanent verdict, and the cache is an
optimization: it may only ever skip work whose answer was yes.
"""
import hashlib
import json
import os
import shutil
import tempfile

from . import _util, kernel

#: Where verdicts are remembered — host residue, never identity.
CACHE = "verdicts"


def _cache_dir() -> str:
    where = os.environ.get(kernel._ENV_CACHE_DIR)
    if not where:
        where = os.path.join(os.path.expanduser("~"), ".cache", "reticuli")
    path = os.path.join(where, CACHE)
    os.makedirs(path, exist_ok=True)
    return path


def fingerprint(claimdir: str) -> dict:
    """What a verdict is a verdict ABOUT."""
    checked = kernel.verify(claimdir)
    host = kernel._judging_host()
    return {"root": checked["recomputed"],
            "build": kernel.build_digest(claimdir),
            "platform": host["platform"], "python": host["python"],
            "name": checked["name"]}


def _key(fields: dict) -> str:
    return hashlib.sha256(
        json.dumps(fields, sort_keys=True).encode("utf-8")).hexdigest()


def _read(key: str):
    path = os.path.join(_cache_dir(), key + ".json")
    return _util.read_json(path, None)


def _write(key: str, payload: dict) -> None:
    _util.write_json(os.path.join(_cache_dir(), key + ".json"), payload)


def remember(claimdir: str, verdict: dict) -> bool:
    """Remember a PASSING verdict for these exact bytes on this exact host."""
    if not verdict or not verdict.get("ok"):
        return False
    fields = fingerprint(claimdir)
    _write(_key(fields), {
        "verdict": {"ok": True, "verdict": verdict.get("verdict", "earned"),
                    "gates": verdict.get("gates") or []},
        "fingerprint": fields, "when": _util.stamp(),
        "source": f"{fields['platform']}/{fields['python']}",
    })
    return True


def lookup(claimdir: str):
    """A remembered verdict for these bytes on this host, or nothing."""
    try:
        fields = fingerprint(claimdir)
    except kernel.ClaimError:
        return None
    entry = _read(_key(fields))
    if not isinstance(entry, dict) or not entry.get("verdict"):
        return None
    return entry


def _layer_key(layer: dict) -> str:
    """A layer's identity in the cache: its bytes, its check, its gate."""
    host = kernel._judging_host()
    files = {}
    for name, source in sorted((layer.get("files") or {}).items()):
        files[name] = kernel._hash_file(source) \
            if os.path.isfile(source) else None
    check_name, check_source = layer.get("check") or (None, None)
    return _key({
        "name": layer.get("name"), "files": files, "gate": layer.get("gate"),
        "verdict": layer.get("verdict"), "check": check_name,
        "check_digest": kernel._hash_file(check_source)
        if check_source and os.path.isfile(check_source) else None,
        "platform": host["platform"], "python": host["python"],
    })


def layered_audit(spec: list) -> dict:
    """Judge a stack of layers, reusing only what was already earned here."""
    rows, ok = [], True
    for layer in spec:
        key = _layer_key(layer)
        entry = _read(key)
        if isinstance(entry, dict) and entry.get("ok"):
            rows.append({"name": layer.get("name"), "status": "reused",
                         "reused": True, "ok": True,
                         "source": entry.get("source"),
                         "earned_when": entry.get("when")})
            continue
        room = tempfile.mkdtemp(prefix="reticuli-layer-")
        try:
            for name, source in (layer.get("files") or {}).items():
                _util.copy_into(source, _util.safe_path(room, name))
            check_name, check_source = layer.get("check") or (None, None)
            if check_name:
                _util.copy_into(check_source,
                                _util.safe_path(room, check_name))
            outcome = kernel.run_gate(layer.get("gate"), room, None)
        finally:
            shutil.rmtree(room, ignore_errors=True)
        earned = outcome["status"] == "ok"
        host = kernel._judging_host()
        rows.append({"name": layer.get("name"), "status": "earned",
                     "reused": False, "ok": earned,
                     "quarantine": outcome["quarantine"],
                     "detail": (outcome["stderr"] or outcome["stdout"])[-300:]
                     if not earned else ""})
        if earned:
            _write(key, {"ok": True, "when": _util.stamp(),
                         "source": f"{host['platform']}/{host['python']}",
                         "name": layer.get("name")})
        ok = ok and earned
    return {"ok": ok, "layers": rows}
