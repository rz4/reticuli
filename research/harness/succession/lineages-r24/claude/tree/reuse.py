"""reticuli.reuse: a verdict cache, keyed by identity + build + host.

Redoing a cold audit costs real time and money. A verdict earned once may be
reused for an identical claim on an identical host -- same root (what was
pinned), same build (what was generated), same platform and interpreter
(what ran it) -- without re-running a single gate.

Reuse is a promise, not a convenience: a failing verdict is never
remembered (so a transient failure can never be served up as cached
success), and a layered audit that serves a cached verdict must say so --
`reused`, never `earned` -- and name whose trust it leaned on. The cache
itself is host residue: `RETICULI_CACHE` overrides where it lives; nothing
here touches identity.

Stdlib only; builds on the public kernel surface, never a kernel private.
"""
import hashlib
import json
import os
import platform
import subprocess
import tempfile

from reticuli import kernel

_DEFAULT_CACHE = os.path.join(tempfile.gettempdir(), "reticuli-reuse-cache.json")


def fingerprint(d):
    """The reuse key for claim directory `d`: identity (root), concrete
    bytes (build), and the host that would run the gates (platform,
    interpreter) -- the four facts that must all match for a verdict
    earned elsewhere to apply here."""
    parsed = kernel.load_recipe(d)
    return {
        "root": kernel.root(parsed, d),
        "build": kernel.build_digest(d),
        "platform": platform.platform(),
        "python": platform.python_version(),
    }


def _cache_path(d=None):
    override = os.environ.get("RETICULI_CACHE")
    if override:
        return override
    if d is not None:
        return os.path.join(d, ".reticuli", "reuse-cache.json")
    return _DEFAULT_CACHE


def _fp_key(fp):
    return hashlib.sha256(
        json.dumps(fp, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _cache_load(path):
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _cache_save(path, data):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, sort_keys=True)
    os.replace(tmp, path)


def remember(d, verdict):
    """Cache `verdict` under `d`'s current fingerprint. A failing verdict
    (no truthy `ok`) is never remembered -- reuse only ever serves up a
    verdict that was once a genuine pass."""
    if not verdict.get("ok"):
        return None
    fp = fingerprint(d)
    key = _fp_key(fp)
    path = _cache_path(d)
    data = _cache_load(path)
    data[key] = {"fingerprint": fp, "verdict": verdict}
    _cache_save(path, data)
    return key


def lookup(d):
    """The cached verdict for `d`'s current fingerprint, or `None` if
    nothing earned matches root + build + host exactly."""
    fp = fingerprint(d)
    key = _fp_key(fp)
    path = _cache_path(d)
    entry = _cache_load(path).get(key)
    return entry["verdict"] if entry else None


# ==== layered_audit: reuse across an ordered stack of file-content layers ===

def _hash_path(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _layer_fingerprint(layer):
    h = hashlib.sha256()
    for rel in sorted(layer["files"]):
        h.update(rel.encode("utf-8"))
        h.update(_hash_path(layer["files"][rel]).encode("utf-8"))
    check_rel, check_src = layer["check"]
    h.update(check_rel.encode("utf-8"))
    h.update(_hash_path(check_src).encode("utf-8"))
    h.update(layer["gate"].encode("utf-8"))
    return h.hexdigest()


def _materialize_layer(layer, room):
    for rel, src in layer["files"].items():
        dst = os.path.join(room, rel)
        parent = os.path.dirname(dst)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(src, "rb") as sf, open(dst, "wb") as df:
            df.write(sf.read())
    check_rel, check_src = layer["check"]
    dst = os.path.join(room, check_rel)
    parent = os.path.dirname(dst)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(check_src, "rb") as sf, open(dst, "wb") as df:
        df.write(sf.read())


def _earn_layer(layer):
    with tempfile.TemporaryDirectory() as room:
        _materialize_layer(layer, room)
        proc = subprocess.run(layer["gate"], shell=True, cwd=room,
                               capture_output=True, text=True)
        return proc.returncode == 0


def layered_audit(spec):
    """Run an ordered stack of layers (each: `name`, `files`, `check`,
    `gate`, `verdict`), earning each cold the first time and reusing a
    cached pass for any layer whose files, check, and gate are byte-
    identical to a previously earned run. Every row names its status --
    `earned` or `reused` -- and a reused row names its source: cheaper is
    always louder, never quieter."""
    path = _cache_path()
    data = _cache_load(path)
    rows = []
    for layer in spec:
        name = layer["name"]
        fp = _layer_fingerprint(layer)
        cached = data.get(fp)
        if cached is not None:
            rows.append({
                "name": name,
                "status": "reused",
                "ok": True,
                "reused": True,
                "source": cached["source"],
                "verdict": cached["verdict"],
            })
            continue
        ok = _earn_layer(layer)
        verdict = layer.get("verdict") if ok else None
        row = {"name": name, "status": "earned", "ok": ok, "verdict": verdict}
        rows.append(row)
        if ok:
            data[fp] = {"source": f"{name}@{fp[:16]}", "verdict": verdict}
            _cache_save(path, data)
    return {"ok": all(r["ok"] for r in rows), "layers": rows}
