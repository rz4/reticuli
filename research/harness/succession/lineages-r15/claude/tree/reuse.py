"""Verdict reuse: a content-addressed cache, so an audit pays only for what
it has not already earned.

Two things are cached here, the same way. A claim-level verdict is keyed by
a *fingerprint* -- the claim's identity, its concrete (generated) bytes, and
the host that would have to re-earn it (`spec/kernel-api.md`: root, build
digest, platform, interpreter). A layered audit's per-layer verdict is keyed
the same way, by the content a layer actually exercises (its files, its
check, its gate command) plus the host.

REUSE IS A PROMISE, NOT A CONVENIENCE: a verdict is written to the cache only
when it was earned clean, so a lookup can never hand back a failure dressed
as a pass, and an empty cache means everything is re-earned. A cache hit is
reported as `reused`, never `earned`, and names the cache entry -- whose
trust -- it leaned on.

Stdlib only.
"""
import json
import os
import platform
import shutil
import tempfile

from reticuli import kernel, _util

_DEFAULT_CACHE = os.path.join(tempfile.gettempdir(), "reticuli-verdict-cache")


def _cache_root() -> str:
    return os.environ.get("RETICULI_CACHE") or _DEFAULT_CACHE


def _host() -> dict:
    """The host a cached verdict is good for: platform and interpreter."""
    return {"platform": platform.platform(), "python": platform.python_version()}


def _key(payload) -> str:
    return _util.hash_bytes(json.dumps(payload, sort_keys=True).encode("utf-8"))


def _entry_path(key: str) -> str:
    return os.path.join(_cache_root(), key[:2], f"{key}.json")


# -- Claim-level verdicts: keyed by root + build + host. -------------------


def fingerprint(d: str) -> dict:
    """What a verdict for claim `d` is good for: its identity, its present
    concrete bytes, and the host that produced it (`spec/kernel-api.md`).
    """
    doc = kernel.load_recipe(d)
    fp = {"root": kernel.root(doc, d), "build": kernel.build_digest(d)}
    fp.update(_host())
    return fp


def remember(d: str, verdict: dict) -> None:
    """Cache `verdict` under claim `d`'s current fingerprint -- unless the
    verdict says the claim failed: a failing verdict is never remembered,
    so a hit can only ever mean "this passed before, on these exact bytes,
    on a matching host."
    """
    if not verdict.get("ok"):
        return
    _util.write_json(_entry_path(_key(fingerprint(d))), verdict)


def lookup(d: str):
    """The cached verdict for claim `d`'s current fingerprint, or `None`."""
    path = _entry_path(_key(fingerprint(d)))
    if not os.path.isfile(path):
        return None
    try:
        return _util.read_json(path)
    except kernel.ClaimError:
        return None


# -- Layered audits: one cache entry per layer, keyed by what it touches. --


def _layer_key(layer: dict) -> str:
    """Content-address a layer: the bytes of every file it supplies, the
    bytes of its check, and its gate command -- the same bytes and command
    a run would actually exercise -- plus the host that would exercise them.
    """
    files = {}
    for rel, src in layer["files"].items():
        with open(src, "rb") as f:
            files[rel] = _util.hash_bytes(f.read())
    check_rel, check_src = layer["check"]
    with open(check_src, "rb") as f:
        files[check_rel] = _util.hash_bytes(f.read())
    return _key({"files": files, "gate": layer["gate"], "host": _host()})


def _materialize_layer(layer: dict, room: str) -> None:
    os.makedirs(room, exist_ok=True)
    items = dict(layer["files"])
    check_rel, check_src = layer["check"]
    items[check_rel] = check_src
    for rel, src in items.items():
        dst = os.path.join(room, rel)
        os.makedirs(os.path.dirname(dst) or room, exist_ok=True)
        shutil.copy2(src, dst)


def layered_audit(spec: list) -> dict:
    """Audit a stack of layered claims, cache-backed: run each layer's gate
    fresh the first time a given layer's exact bytes and host are seen, and
    hand back the cached verdict -- status `reused`, carrying `source`, the
    cache entry it leaned on -- every time after. A failing layer is never
    cached, so it is always redone until it earns a pass.
    """
    rows = []
    ok = True
    room_root = tempfile.mkdtemp(prefix="reticuli-layered-")
    try:
        for layer in spec:
            key = _layer_key(layer)
            path = _entry_path(key)
            cached = None
            if os.path.isfile(path):
                try:
                    cached = _util.read_json(path)
                except kernel.ClaimError:
                    cached = None

            if cached is not None:
                row = dict(cached)
                row["name"] = layer["name"]
                row["status"] = "reused"
                row["reused"] = True
                row["source"] = f"cache:{key}"
                rows.append(row)
                if not row.get("ok"):
                    ok = False
                continue

            room = os.path.join(room_root, layer["name"])
            _materialize_layer(layer, room)
            result = kernel.run_gate(layer["gate"], room)
            passed = result["status"] == "ok"
            row = {"name": layer["name"], "status": "earned", "reused": False,
                   "ok": passed, "verdict": layer.get("verdict") if passed else None}
            rows.append(row)
            if passed:
                _util.write_json(path, {"ok": True, "verdict": layer.get("verdict")})
            else:
                ok = False
    finally:
        shutil.rmtree(room_root, ignore_errors=True)
    return {"ok": ok, "layers": rows}
