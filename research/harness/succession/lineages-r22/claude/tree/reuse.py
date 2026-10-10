"""Surface: reusing an already-earned verdict rather than re-earning it
blind (spec/layers.md).

A verdict's `fingerprint` keys on identity, concrete bytes, and host: same
root, same build digest, same platform, same interpreter -- anything else
changing means the verdict is about a different fact. `remember` writes a
passing verdict to the claim's own residue, keyed by that fingerprint;
REUSE IS A PROMISE, NOT A CONVENIENCE, so a failing verdict is never
written -- a hit in this cache always means something earned, never
something that failed and was forgotten about.

`layered_audit` applies the same discipline across one or more build
layers that share a cache (`RETICULI_CACHE`): a layer whose declared files,
check, and gate command are byte-identical to one already in the cache is
`reused`, not re-run; a miss is `earned` cold and then written. A reused
row still names when it was earned and whose trust it leaned on -- cheaper
is louder, never quieter -- and `reused` is never spelled `earned`.
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
from . import _util

CACHE_FILE = "reuse-cache.json"
CACHE_ENV = "RETICULI_CACHE"


def fingerprint(d: str) -> dict:
    """A verdict's key: identity + concrete bytes + host."""
    manifest = kernel.read_manifest(d)
    return {
        "root": manifest["root"],
        "build": kernel.build_digest(d),
        "platform": sys.platform,
        "python": platform.python_version(),
    }


def _fp_key(fp: dict) -> str:
    return "|".join(str(fp[k]) for k in ("root", "build", "platform", "python"))


def _load_cache(path: str) -> dict:
    if not path or not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def remember(d: str, verdict: dict) -> None:
    """Record `verdict` under the claim's own residue, keyed by its
    current `fingerprint` -- a no-op when the verdict did not pass."""
    if not verdict.get("ok"):
        return
    path = os.path.join(d, kernel.STORE, CACHE_FILE)
    cache = _load_cache(path)
    cache[_fp_key(fingerprint(d))] = verdict
    _util.write_json(path, cache)


def lookup(d: str):
    """The remembered verdict for `d`'s current fingerprint, or `None`."""
    path = os.path.join(d, kernel.STORE, CACHE_FILE)
    cache = _load_cache(path)
    return cache.get(_fp_key(fingerprint(d)))


# ------------------------------------------------------------- layered --

def _layer_fingerprint(layer: dict) -> str:
    """A layer's identity: the bytes of every declared file, its check,
    and the gate command that judges them -- not its name or label, so
    two layers with the same obligations and different names still share
    one cache entry."""
    h = hashlib.sha256()
    h.update(layer.get("gate", "").encode("utf-8"))
    for name in sorted(layer.get("files", {})):
        h.update(b"\0file:" + name.encode("utf-8"))
        with open(layer["files"][name], "rb") as f:
            h.update(f.read())
    check_name, check_src = layer["check"]
    h.update(b"\0check:" + check_name.encode("utf-8"))
    with open(check_src, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def layered_audit(spec: list) -> dict:
    """Judge each layer in `spec`, in order, in a fresh room built from
    exactly its declared files and check. A layer already in the shared
    cache (`RETICULI_CACHE`) is reused rather than re-run; everything
    earned this call is written back for the next one."""
    cache_path = os.environ.get(CACHE_ENV)
    cache = _load_cache(cache_path)

    rows = []
    ok = True
    for layer in spec:
        fp = _layer_fingerprint(layer)
        cached = cache.get(fp)
        if cached is not None:
            rows.append({
                "name": layer.get("name"), "status": "reused",
                "reused": True, "source": cached.get("source", fp),
                "when": cached.get("when"), "verdict": layer.get("verdict"),
            })
            continue

        room = tempfile.mkdtemp()
        try:
            for name, src in layer.get("files", {}).items():
                target = os.path.join(room, name)
                os.makedirs(os.path.dirname(target) or room, exist_ok=True)
                shutil.copy2(src, target)
            check_name, check_src = layer["check"]
            shutil.copy2(check_src, os.path.join(room, check_name))
            result = subprocess.run(layer["gate"], shell=True, cwd=room,
                                     capture_output=True, text=True)
            passed = result.returncode == 0
        finally:
            shutil.rmtree(room, ignore_errors=True)

        if passed:
            source = f"earned:{layer.get('name', fp)}"
            cache[fp] = {"source": source, "when": _util.stamp()}
            rows.append({
                "name": layer.get("name"), "status": "earned",
                "reused": False, "source": source, "verdict": layer.get("verdict"),
            })
        else:
            ok = False
            rows.append({
                "name": layer.get("name"), "status": "failed",
                "reused": False, "source": None, "verdict": layer.get("verdict"),
            })

    if cache_path:
        _util.write_json(cache_path, cache)
    return {"ok": ok, "layers": rows}
