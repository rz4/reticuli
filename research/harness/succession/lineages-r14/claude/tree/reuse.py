"""reticuli.reuse -- a verdict cache keyed by identity + build + host
(spec/layers.md: the surface layer).

Re-earning a verdict costs a gate run; the same bytes, on the same host,
against the same claim, earn the same answer every time. `fingerprint` names
exactly the four facts that decide whether a cached verdict still applies
(`root`: which claim; `build`: which concrete bytes; `platform`/`python`:
which host) -- and `remember`/`lookup` cache a verdict under that key.

REUSE IS A PROMISE, NOT A CONVENIENCE: a failing verdict is never cached
(`remember` silently declines one), so a claim that is currently broken is
always re-earned fresh rather than remembered as broken forever. And a
layered audit that skips work already earned must say so -- a reused row is
never spelled `earned`, and it names the earlier verdict it leaned on.

Storage defaults to the claim's own store (so a single claim's cache needs
no coordination) and is overridden by `RETICULI_CACHE`, so many claims --
for instance the ad hoc layers `layered_audit` builds, each in its own
throwaway directory -- can share one cache across calls.
"""
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile

from reticuli import kernel, _util

_CACHE_ENV = "RETICULI_CACHE"
_CACHE_SUBDIR = os.path.join(".reticuli", "cache")
_LAYER_CACHE_DEFAULT = os.path.join(tempfile.gettempdir(), "reticuli-layer-cache")


# -- the cache: content-addressed, write-once on success only --------------

def _key(fp: dict) -> str:
    text = json.dumps(fp, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _cache_write(cache_dir: str, fp: dict, payload: dict) -> None:
    os.makedirs(cache_dir, exist_ok=True)
    _util.write_json(os.path.join(cache_dir, _key(fp) + ".json"), payload)


def _cache_read(cache_dir: str, fp: dict):
    path = os.path.join(cache_dir, _key(fp) + ".json")
    if not os.path.isfile(path):
        return None
    try:
        payload = _util.read_json(path)
    except (OSError, ValueError):
        return None
    if payload.get("fingerprint") != fp:
        return None
    return payload


# -- fingerprint / remember / lookup over a sealed claim directory ---------

def fingerprint(d: str) -> dict:
    """The key a verdict for `d` is cached under: `root` (which claim),
    `build` (which concrete bytes), `platform`/`python` (which host). Any
    one of them changing means the cached verdict no longer applies."""
    manifest = kernel.read_manifest(d)
    return {
        "root": manifest["root"],
        "build": kernel.build_digest(d),
        "platform": sys.platform,
        "python": platform.python_version(),
    }


def _cache_dir(d: str) -> str:
    override = os.environ.get(_CACHE_ENV)
    if override:
        return override
    return os.path.join(d, _CACHE_SUBDIR)


def remember(d: str, verdict: dict) -> None:
    """Cache `verdict` under `d`'s current fingerprint -- unless it failed.
    A failing verdict is never written, so the next call re-earns it fresh."""
    if not verdict.get("ok"):
        return
    fp = fingerprint(d)
    payload = {"fingerprint": fp, "verdict": verdict}
    _cache_write(_cache_dir(d), fp, payload)


def lookup(d: str):
    """The verdict cached for `d`'s current fingerprint, or `None`."""
    payload = _cache_read(_cache_dir(d), fingerprint(d))
    if payload is None:
        return None
    return payload.get("verdict")


# -- layered_audit: cache a verdict per layer, honestly labeled ------------

def _layer_fingerprint(layer: dict) -> dict:
    """The identity of one layer's obligation: the bytes it supplies, the
    bytes of its own check, and the gate command that judges them, plus the
    host -- the same four-part shape as `fingerprint`, generalized to a
    layer that is never itself sealed as a claim."""
    parts = {}
    for name, path in sorted(layer.get("files", {}).items()):
        parts[f"file:{name}"] = _util.hash_bytes(path)
    check_name, check_path = layer["check"]
    parts[f"file:{check_name}"] = _util.hash_bytes(check_path)
    parts["gate"] = layer["gate"]
    parts["platform"] = sys.platform
    parts["python"] = platform.python_version()
    return parts


def _layer_cache_dir() -> str:
    return os.environ.get(_CACHE_ENV) or _LAYER_CACHE_DEFAULT


def _earn_layer(layer: dict) -> bool:
    """Materialize `layer`'s files and check into a scratch room and run its
    gate once; `True` iff it exits clean."""
    room = tempfile.mkdtemp(prefix="reticuli-layer-")
    try:
        for name, path in layer.get("files", {}).items():
            shutil.copy2(path, os.path.join(room, name))
        check_name, check_path = layer["check"]
        shutil.copy2(check_path, os.path.join(room, check_name))
        result = subprocess.run(layer["gate"], shell=True, cwd=room,
                                 capture_output=True, text=True, timeout=120)
        return result.returncode == 0
    finally:
        shutil.rmtree(room, ignore_errors=True)


def layered_audit(spec) -> dict:
    """Earn (or reuse) a verdict for each layer in `spec` -- a list of
    `{"name", "files", "check", "gate", "verdict"}` dicts -- and report, per
    layer, whether this call earned it cold or reused a verdict earned
    before. A reused row always names `source`, the earlier verdict it
    leaned on; `earned` is never spelled for a layer that skipped its gate."""
    cache_dir = _layer_cache_dir()
    layers_out = []
    ok = True

    for layer in spec:
        fp = _layer_fingerprint(layer)
        cached = _cache_read(cache_dir, fp)
        if cached is not None:
            verdict = cached.get("verdict", {})
            layers_out.append({
                "name": layer.get("name"),
                "status": "reused",
                "reused": True,
                "source": verdict.get("source"),
                "ok": verdict.get("ok", False),
            })
            if not verdict.get("ok"):
                ok = False
            continue

        earned_ok = _earn_layer(layer)
        source = {"key": _key(fp), "when": _util.stamp()}
        layers_out.append({
            "name": layer.get("name"),
            "status": "earned",
            "reused": False,
            "source": source,
            "ok": earned_ok,
        })
        if earned_ok:
            _cache_write(cache_dir, fp, {"fingerprint": fp,
                                         "verdict": {"ok": True, "source": source}})
        else:
            ok = False

    return {"ok": ok, "layers": layers_out}
