"""reticuli.reuse: a content-addressed verdict cache.

Re-earning a verdict is the only way to know it still holds; re-earning
it on bytes nobody touched, on a host nobody changed, is pure cost. A
verdict is cheap to skip exactly when its key has not moved: the
identity it was earned against, the concrete bytes it ran on, and the
host that ran it (platform, interpreter). `fingerprint` names that key
for a sealed claim directory; `remember`/`lookup` round-trip a verdict
keyed by it.

**A failing verdict is never remembered.** Caching is a promise that
re-running would say the same thing, and a failure is the one verdict
that re-running might not repeat -- a fluke of this host, this moment,
rather than of the claim. So only a passing verdict (`ok` true) is
ever written to the cache; a lookup miss always falls through to
re-earning.

`layered_audit` applies the same discipline to a *sequence* of layers,
each a small, independent gate over its own files -- a stand-in for a
composed claim's components (`spec/layers.md`). Every layer reports
whether it was `earned` fresh or `reused` from the cache; a reused
layer always says so, and always names the source it leaned on
(`source`) -- cheaper is louder, never quieter.

Cache location: `RETICULI_CACHE`, a directory; defaults to a path
under the host's temp directory when unset. Residue only, like every
other file this module touches -- never consulted by identity.

Stdlib only.
"""
import hashlib
import json
import os
import platform
import shutil
import tempfile

from . import kernel
from ._util import read_json, safe_path, stamp, write_json

_DEFAULT_CACHE = os.path.join(tempfile.gettempdir(), "reticuli-reuse")


def _cache_dir() -> str:
    return os.environ.get("RETICULI_CACHE") or _DEFAULT_CACHE


def _digest(parts: dict) -> str:
    canon = json.dumps(parts, sort_keys=True, separators=(", ", ": "))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def _entry_path(key: str) -> str:
    return os.path.join(_cache_dir(), key + ".json")


def _host() -> dict:
    return {"platform": platform.platform(), "python": platform.python_version()}


def fingerprint(d: str) -> dict:
    """The cache key for claim directory `d`: its identity (`root`), the
    concrete bytes present (`build`), and the host earning the verdict
    (`platform`, `python`)."""
    manifest = kernel.read_manifest(d)
    fp = {"root": manifest["root"], "build": kernel.build_digest(d)}
    fp.update(_host())
    return fp


def remember(d: str, verdict: dict) -> None:
    """Cache `verdict` under claim `d`'s current fingerprint -- unless
    it is a failure, which is never remembered."""
    if not verdict.get("ok"):
        return
    fp = fingerprint(d)
    write_json(_entry_path(_digest(fp)),
               {"fingerprint": fp, "verdict": verdict, "earned_at": stamp()})


def lookup(d: str):
    """The cached verdict for claim `d`'s current fingerprint, or
    `None` on a miss -- including a miss caused by unreadable cache
    bytes, which is treated the same as never having cached anything."""
    path = _entry_path(_digest(fingerprint(d)))
    if not os.path.isfile(path):
        return None
    try:
        entry = read_json(path)
    except (OSError, ValueError):
        return None
    return entry.get("verdict")


def _layer_key(layer: dict) -> str:
    """The content fingerprint of one `layered_audit` layer: every
    named file's bytes, the check script's bytes, the gate command,
    and the host -- everything that decides the layer's verdict."""
    parts = {}
    for name, path in sorted(layer.get("files", {}).items()):
        parts[f"file:{name}"] = kernel._hash_file(path)
    check_name, check_path = layer["check"]
    parts[f"check:{check_name}"] = kernel._hash_file(check_path)
    parts["gate"] = layer["gate"]
    parts.update(_host())
    return _digest(parts)


def _materialize_layer(layer: dict, room: str) -> None:
    for name, src in layer.get("files", {}).items():
        dst = safe_path(room, name)
        os.makedirs(os.path.dirname(dst) or room, exist_ok=True)
        shutil.copy2(src, dst)
    check_name, check_src = layer["check"]
    dst = safe_path(room, check_name)
    os.makedirs(os.path.dirname(dst) or room, exist_ok=True)
    shutil.copy2(check_src, dst)


def layered_audit(spec: list) -> dict:
    """Re-earn (or reuse) a verdict for each layer of `spec`, in order.

    Each layer is `{"name", "files": {name: path}, "check": (name, path),
    "gate": shell command, "verdict": label}`. A layer whose content
    fingerprint is already cached is `reused`, never re-run; otherwise
    it is materialized into a fresh room and its gate is run fresh
    (`earned`), and a passing result is cached for next time. Returns
    `{"ok": bool, "layers": [row, ...]}`, one row per layer.
    """
    layers = []
    for layer in spec:
        key = _layer_key(layer)
        path = _entry_path("layer-" + key)
        cached = None
        if os.path.isfile(path):
            try:
                cached = read_json(path)
            except (OSError, ValueError):
                cached = None

        if cached is not None:
            layers.append({
                "name": layer["name"],
                "status": "reused",
                "ok": True,
                "reused": True,
                "source": cached.get("earned_at"),
            })
            continue

        room = tempfile.mkdtemp(prefix="reticuli-layer-")
        try:
            _materialize_layer(layer, room)
            result = kernel.run_gate(layer["gate"], room)
            ok = result["status"] == "ok"
        finally:
            shutil.rmtree(room, ignore_errors=True)

        layers.append({"name": layer["name"], "status": "earned", "ok": ok})
        if ok:
            write_json(path, {"verdict": layer.get("verdict"), "earned_at": stamp()})

    return {"ok": all(row["ok"] for row in layers), "layers": layers}
