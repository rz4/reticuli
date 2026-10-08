"""Reuse is a promise, not a convenience (spec/layers.md's surface layer).

A verdict is keyed by the claim's identity, its concrete bytes, and the
host that earned it (`fingerprint`), never remembered on failure
(`remember`), and recalled only when the current claim still matches that
exact fingerprint (`lookup`). `layered_audit` extends the same promise
across a chain of layers that compose on top of one another: a layer whose
exact inputs and gate were already earned is `reused`, not `earned` --
cheaper is louder, never quieter -- and a layer never seen before is
`earned` cold, with nothing carried in.
"""
import hashlib
import json
import os
import platform
import shutil
import subprocess
import tempfile

from . import _util
from . import kernel

_CACHE_ENV = "RETICULI_CACHE"


def _cache_root() -> str:
    cache = os.environ.get(_CACHE_ENV)
    if cache:
        return cache
    return os.path.join(tempfile.gettempdir(), "reticuli-reuse")


def _host() -> str:
    return f"{platform.system().lower()}-{platform.machine()}"


def fingerprint(d: str) -> dict:
    """What a verdict is keyed on: the claim's identity, its concrete
    bytes, and the host that would be re-earning it."""
    manifest = kernel.read_manifest(d)
    return {
        "root": manifest["root"],
        "build": kernel.build_digest(d),
        "platform": _host(),
        "python": platform.python_version(),
    }


def _digest(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode("utf-8")).hexdigest()


def _verdict_path(fp: dict) -> str:
    return os.path.join(_cache_root(), "verdict-" + _digest(fp) + ".json")


def remember(d: str, verdict: dict) -> None:
    """Cache `verdict` under `d`'s current fingerprint -- but only when it
    is a passing verdict. A failing verdict is never remembered: reuse must
    never let a claim that once failed come back as a free pass."""
    if not verdict.get("ok"):
        return
    fp = fingerprint(d)
    _util.write_json(_verdict_path(fp), {"fingerprint": fp, "verdict": verdict})


def lookup(d: str):
    """The cached verdict for `d`'s current fingerprint, or `None` -- never
    a stale one: a fingerprint mismatch (different bytes, build, or host)
    is a miss, not a near hit."""
    fp = fingerprint(d)
    path = _verdict_path(fp)
    if not os.path.isfile(path):
        return None
    try:
        record = _util.read_json(path)
    except (OSError, ValueError):
        return None
    if record.get("fingerprint") != fp:
        return None
    return record.get("verdict")


def _layer_digest(layer: dict) -> str:
    """The exact bytes and command a layer's gate ran -- its own
    fingerprint, independent of any claim's root."""
    h = hashlib.sha256()
    for name in sorted(layer.get("files", {})):
        with open(layer["files"][name], "rb") as f:
            h.update(name.encode("utf-8"))
            h.update(b"\x00")
            h.update(f.read())
            h.update(b"\x1e")
    check_name, check_src = layer["check"]
    with open(check_src, "rb") as f:
        h.update(check_name.encode("utf-8"))
        h.update(b"\x00")
        h.update(f.read())
        h.update(b"\x1e")
    h.update(layer["gate"].encode("utf-8"))
    return h.hexdigest()


def _layer_path(digest: str) -> str:
    return os.path.join(_cache_root(), "layer-" + digest + ".json")


def layered_audit(spec: list) -> dict:
    """Run each layer's gate in a fresh room, cheapest first: a layer whose
    exact files, check, and gate command were already earned is `reused`
    from the cache -- and the row says so, and whose trust it leaned on --
    instead of re-run; a layer never earned before runs cold and, on a
    pass, is cached for the next caller."""
    layers = []
    ok = True
    for layer in spec:
        digest = _layer_digest(layer)
        cache_path = _layer_path(digest)
        cached = None
        if os.path.isfile(cache_path):
            try:
                cached = _util.read_json(cache_path)
            except (OSError, ValueError):
                cached = None

        if cached is not None:
            layers.append({
                "name": layer["name"], "status": "reused", "reused": True,
                "source": cached.get("when"), "verdict": layer.get("verdict"),
            })
            continue

        room = tempfile.mkdtemp(prefix="reticuli-layer-")
        try:
            for name, src in layer.get("files", {}).items():
                _util.copy_into(src, os.path.join(room, name))
            check_name, check_src = layer["check"]
            _util.copy_into(check_src, os.path.join(room, check_name))
            result = subprocess.run(layer["gate"], shell=True, cwd=room,
                                     capture_output=True)
            passed = result.returncode == 0
        finally:
            shutil.rmtree(room, ignore_errors=True)

        if not passed:
            ok = False
            layers.append({"name": layer["name"], "status": "failed",
                            "reused": False, "verdict": layer.get("verdict")})
            continue

        when = _util.stamp()
        _util.write_json(cache_path, {"ok": True, "when": when, "name": layer["name"]})
        layers.append({"name": layer["name"], "status": "earned", "reused": False,
                        "verdict": layer.get("verdict")})

    return {"ok": ok, "layers": layers}
