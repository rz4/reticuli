"""Reuse: keying a verdict by identity + build + host, honestly.

A verdict earned once need not be re-earned by every later audit that sees
the exact same bytes on the exact same kind of host -- but reuse is a
promise, not a convenience (the 2026-10-04 bundle): a layered audit that
skips work already earned must say so, `reused` and never `earned`, and
must name whose trust it leaned on. And a verdict cache must never let a
failure in once recorded quietly become a pass later: a failing verdict is
never remembered, so a miss always means "earn it again", never "it broke
last time, skip it."

`fingerprint(d)` keys a claim directory on its identity (`root`), its
concrete bytes (`build`), and the host (`platform`, `python`) -- the same
four things that decide whether an old verdict still describes the bytes in
front of you now. `remember`/`lookup` round-trip a verdict under that key.
`layered_audit` is the same discipline applied to a stack of layers that are
not full claims: each layer's own files, check, and gate command are its
content address, and the second identical run reuses every layer instead of
re-running the gates.

The cache lives at `$RETICULI_CACHE` if set, otherwise a fixed spot under
the platform temp directory -- host residue, never identity, and never
consulted by the kernel itself.

Only the public kernel surface (`reticuli.kernel`) is used, per
`spec/layers.md`. Stdlib only.
"""
import datetime
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile

from reticuli import kernel


# -- the cache: a content-addressed directory of small JSON files -----------

def _cache_dir() -> str:
    base = os.environ.get("RETICULI_CACHE")
    if not base:
        base = os.path.join(tempfile.gettempdir(), "reticuli-verdict-cache")
    return base


def _key(obj) -> str:
    text = json.dumps(obj, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _cache_get(key: str):
    path = os.path.join(_cache_dir(), key + ".json")
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _cache_put(key: str, value: dict) -> None:
    d = _cache_dir()
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, key + ".json")
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(value, f, sort_keys=True)
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _host() -> dict:
    return {"platform": sys.platform, "python": platform.python_version()}


# -- per-claim fingerprint ----------------------------------------------------

def fingerprint(d: str) -> dict:
    """`d`'s reuse key: identity, concrete bytes, and the host.

    A verdict earned under one fingerprint describes the same claim, the
    same bytes, and the same kind of host -- reusing it on a different
    fingerprint would carry a verdict across a difference it never measured.
    """
    parsed = kernel.load_recipe(d)
    fp = {"root": kernel.root(parsed, d), "build": kernel.build_digest(d)}
    fp.update(_host())
    return fp


def remember(d: str, verdict: dict) -> None:
    """Cache `verdict` under `d`'s fingerprint -- unless it is a failure.

    A failing verdict is never remembered: a cache miss must always mean
    "earn it again", never "this was known broken".
    """
    if not verdict.get("ok"):
        return
    fp = fingerprint(d)
    _cache_put(_key(fp), {"fingerprint": fp, "verdict": verdict})


def lookup(d: str):
    """The cached verdict for `d`'s current fingerprint, or `None`."""
    entry = _cache_get(_key(fingerprint(d)))
    return entry["verdict"] if entry is not None else None


# -- layered audits: content-addressed by files + check + gate, not a root --

def _copy_into(path: str, src: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    shutil.copy2(src, path)


def _layer_fingerprint(layer: dict) -> dict:
    files = {rel: kernel._hash_file(src) for rel, src in layer["files"].items()}
    check_name, check_src = layer["check"]
    fp = {
        "gate": layer["gate"],
        "check": {check_name: kernel._hash_file(check_src)},
        "files": files,
    }
    fp.update(_host())
    return fp


def _earn_layer(layer: dict) -> dict:
    scratch = tempfile.mkdtemp(prefix="reticuli-layer-")
    try:
        for rel, src in layer["files"].items():
            _copy_into(os.path.join(scratch, rel), src)
        check_name, check_src = layer["check"]
        _copy_into(os.path.join(scratch, check_name), check_src)
        result = subprocess.run(layer["gate"], shell=True, cwd=scratch,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return {"ok": result.returncode == 0}
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def layered_audit(spec: list) -> dict:
    """Earn or reuse each layer of `spec`, in order; never spell reuse `earned`.

    Each entry: `name`, `files` (relpath -> source path), `check`
    (`(relpath, source path)`), `gate` (a shell command run with the
    materialized files as its working directory), and `verdict` (a label
    carried through on success, not interpreted).
    """
    rows = []
    for layer in spec:
        fp = _layer_fingerprint(layer)
        key = _key(fp)
        cached = _cache_get(key)
        if cached is not None and cached.get("ok"):
            rows.append({
                "name": layer["name"], "status": "reused", "ok": True,
                "reused": True, "source": cached["source"],
                "verdict": layer.get("verdict"),
            })
            continue

        earned = _earn_layer(layer)
        if earned["ok"]:
            when = datetime.datetime.now(datetime.timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ")
            source = {"when": when, "host": _host()}
            _cache_put(key, {"ok": True, "source": source})
            rows.append({
                "name": layer["name"], "status": "earned", "ok": True,
                "reused": False, "source": None,
                "verdict": layer.get("verdict"),
            })
        else:
            rows.append({
                "name": layer["name"], "status": "earned", "ok": False,
                "reused": False, "source": None, "verdict": None,
            })

    return {"ok": all(row["ok"] for row in rows), "layers": rows}
