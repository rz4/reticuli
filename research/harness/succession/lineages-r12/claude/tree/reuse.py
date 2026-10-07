"""Reuse: a verdict cache that is a promise, not a convenience.

A verdict earned by actually running a claim's gates is keyed by its
identity, its concrete bytes, and the host that earned it
(`root` + `build_digest` + `platform` + interpreter): change any of those
and the key changes, so a cache hit can only ever mean "this exact claim,
on this exact host, was already judged" -- never "something similar
passed". A **failing** verdict is never written: a miss costs a redo, a
false hit would cost correctness, and this cache only ever trades the
former.

`layered_audit` extends the same discipline to a stack of layers, each
judged by its own check against its own bytes (plus everything it
depends on): a layer whose content is unchanged since it was last earned
is `reused`, and a reused row always says *whose* trust it leaned on
(`source`) and *when* it was earned -- cheaper is louder, never quieter.
Nothing here touches a claim's root; this is host residue, store it
wherever `RETICULI_CACHE` points and nowhere else.

Stdlib only.
"""
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile

from . import kernel

_ENV_CACHE = "RETICULI_CACHE"


def _cache_root() -> str:
    override = os.environ.get(_ENV_CACHE)
    if override:
        return override
    return os.path.join(tempfile.gettempdir(), "reticuli-reuse")


def _canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True).encode("utf-8")


def _digest(obj) -> str:
    return hashlib.sha256(_canon(obj)).hexdigest()


def _read_entry(path: str):
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _write_entry(path: str, entry: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(entry, f, sort_keys=True)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# -- a claim's own verdict -------------------------------------------------

def fingerprint(d: str) -> dict:
    """The cache key for one claim's current state: identity, concrete
    bytes, and the host that would judge them."""
    d = os.path.abspath(d)
    manifest = kernel.read_manifest(d)
    return {
        "root": manifest["root"],
        "build": kernel.build_digest(d),
        "platform": sys.platform,
        "python": platform.python_version(),
    }


def _verdict_path(fp: dict) -> str:
    return os.path.join(_cache_root(), "verdicts", _digest(fp) + ".json")


def remember(d: str, verdict: dict) -> None:
    """Cache `verdict` under this claim's current fingerprint -- unless it
    is a failure, which is never remembered."""
    if not verdict.get("ok"):
        return
    fp = fingerprint(d)
    _write_entry(_verdict_path(fp), {"fingerprint": fp, "verdict": verdict})


def lookup(d: str):
    """The cached verdict for this claim's current fingerprint, or `None`
    on a miss."""
    entry = _read_entry(_verdict_path(fingerprint(d)))
    return entry.get("verdict") if entry else None


# -- layered audit: a stack of layers, each judged against its own bytes --

def _layer_key(layer: dict) -> str:
    files = {name: kernel._hash_file(path)
             for name, path in sorted(layer.get("files", {}).items())}
    check_name, check_path = layer["check"]
    parts = {
        "name": layer["name"],
        "gate": layer["gate"],
        "verdict": layer.get("verdict"),
        "files": files,
        "check": {check_name: kernel._hash_file(check_path)},
    }
    return _digest(parts)


def _layer_path(key: str) -> str:
    return os.path.join(_cache_root(), "layers", key + ".json")


def _earn_layer(layer: dict) -> bool:
    room = tempfile.mkdtemp(prefix="reticuli-layer-")
    try:
        for name, path in layer.get("files", {}).items():
            dst = os.path.join(room, name)
            os.makedirs(os.path.dirname(dst) or room, exist_ok=True)
            shutil.copy2(path, dst)
        check_name, check_path = layer["check"]
        dst = os.path.join(room, check_name)
        os.makedirs(os.path.dirname(dst) or room, exist_ok=True)
        shutil.copy2(check_path, dst)
        result = subprocess.run(layer["gate"], shell=True, cwd=room)
        return result.returncode == 0
    finally:
        shutil.rmtree(room, ignore_errors=True)


def layered_audit(layers: list, source: str = "self") -> dict:
    """Earn or reuse a verdict for each layer, in order.

    Each layer is `{"name", "files": {name_in_room: path}, "check":
    (name_in_room, path), "gate": shell_command, "verdict": label}`. A
    layer whose content (files + check, by bytes) matches a prior earn is
    `reused` -- never silently spelled `earned` -- and its row carries
    `reused: True` and `source`: whose trust this run leaned on. A layer
    earned cold, or earned because it failed to reuse, is actually run.
    """
    rows = []
    ok = True
    for layer in layers:
        key = _layer_key(layer)
        path = _layer_path(key)
        cached = _read_entry(path)
        if cached is not None:
            rows.append({
                "name": layer["name"], "status": "reused",
                "verdict": layer.get("verdict"),
                "reused": True, "source": cached.get("source", source),
            })
            continue
        passed = _earn_layer(layer)
        if passed:
            _write_entry(path, {"source": source, "verdict": layer.get("verdict")})
            rows.append({"name": layer["name"], "status": "earned",
                         "verdict": layer.get("verdict")})
        else:
            ok = False
            rows.append({"name": layer["name"], "status": "failed",
                         "verdict": layer.get("verdict")})
    return {"ok": ok, "layers": rows}
