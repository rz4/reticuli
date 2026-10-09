"""reuse: a content-addressed verdict cache.

A verdict is earned by running gates; once earned for exact bytes, on an
exact host, it does not need re-earning by a layer that asks the identical
question again. `fingerprint` keys a verdict by what the answer actually
depends on -- a claim's identity and the concrete bytes present (root,
build digest), and the host that would have to redo the work if it did not
reuse (platform, interpreter) -- never by anything else, so a verdict is
never handed back for bytes, or a host, it was not earned on.

REUSE IS A PROMISE, NOT A CONVENIENCE: a lookup that skips work already
earned must say so -- `reused`, never `earned` -- and name whose trust it
leaned on. And a failing verdict is never remembered: a cached failure
would let one transient flake poison every later run, forever, which is a
far worse failure mode than simply re-earning the answer one more time.

`layered_audit` applies the same cache to a stack of layer specs (files,
a check script, a gate command) that are not full claims -- the shape
`checks/measure_check.py` exercises directly.
"""
import fcntl
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile

from reticuli import _util, kernel


# --------------------------------------------------------------- the cache
def _cache_path() -> str:
    """Where verdicts are cached: `RETICULI_CACHE` if set, else a shared
    default outside any particular claim (the cache is host residue, never
    identity -- `spec/claim-format.md`)."""
    return os.environ.get("RETICULI_CACHE") or os.path.join(
        tempfile.gettempdir(), "reticuli-reuse-cache.json")


def _load(path: str) -> dict:
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    return doc if isinstance(doc, dict) else {}


def _write(path: str, doc: dict) -> None:
    directory = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(doc, f, sort_keys=True)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _get(key: str):
    """The cached entry for `key`, or `None`."""
    return _load(_cache_path()).get(key)


def _put(key: str, entry: dict) -> None:
    """Merge `entry` into the shared cache under `key`, holding an
    exclusive lock across the read-modify-write."""
    path = _cache_path()
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    lock_path = path + ".lock"
    with open(lock_path, "w") as lock_f:
        fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)
        try:
            doc = _load(path)
            doc[key] = entry
            _write(path, doc)
        finally:
            fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)


def _key(parts: dict) -> str:
    """A stable cache key from a fingerprint-shaped dict: canonical JSON,
    the same serialization identity uses (`spec/identity.md`)."""
    return hashlib.sha256(
        json.dumps(parts, sort_keys=True).encode("utf-8")).hexdigest()


def _host() -> dict:
    """The host a cached verdict would have to be redone on, if it were
    not reused."""
    return {"platform": sys.platform,
            "python": f"{platform.python_implementation()} {platform.python_version()}"}


# ---------------------------------------------------------------- claim-keyed
def fingerprint(d: str) -> dict:
    """What a verdict for claim `d` actually depends on: its identity, the
    concrete bytes present, and the host that would have to redo it."""
    v = kernel.verify(d)
    out = {"root": v["root"], "build": kernel.build_digest(d)}
    out.update(_host())
    return out


def remember(d: str, verdict: dict) -> None:
    """Cache `verdict` for `d`'s current fingerprint -- unless it is a
    failure. A failing verdict is never remembered."""
    if not verdict.get("ok"):
        return
    key = _key(fingerprint(d))
    entry = dict(verdict)
    entry["source"] = {"earned_when": _util.stamp(), "cache": _cache_path()}
    _put(key, entry)


def lookup(d: str):
    """The cached verdict for `d`'s current fingerprint, or `None` if
    nothing was ever earned for exactly these bytes on this host."""
    return _get(_key(fingerprint(d)))


# --------------------------------------------------------------- layered audit
def _layer_key(layer: dict) -> str:
    """A content-addressed key for one layer spec: the bytes of every file
    it supplies, its check script, its gate command, and the host that
    would have to re-run it -- nothing path- or clock-dependent."""
    parts = {"gate": layer["gate"]}
    parts.update(_host())
    for name, path in layer["files"].items():
        with open(path, "rb") as f:
            parts[f"file:{name}"] = _util.hash_bytes(f.read())
    check_name, check_path = layer["check"]
    with open(check_path, "rb") as f:
        parts[f"check:{check_name}"] = _util.hash_bytes(f.read())
    return _key(parts)


def _earn_layer(layer: dict) -> bool:
    """Run one layer's gate cold, in a fresh room holding only its own
    declared files and check script. True on a clean exit."""
    room = tempfile.mkdtemp()
    try:
        for name, path in layer["files"].items():
            _util.copy_into(path, os.path.join(room, name))
        check_name, check_path = layer["check"]
        _util.copy_into(check_path, os.path.join(room, check_name))
        result = subprocess.run(layer["gate"], shell=True, cwd=room,
                                 capture_output=True)
        return result.returncode == 0
    finally:
        shutil.rmtree(room, ignore_errors=True)


def layered_audit(spec: list) -> dict:
    """Audit a stack of layer specs, reusing any verdict already earned
    for a layer's exact bytes, command, and host -- and saying so.

    Each layer is `{"name", "files" (output name -> source path),
    "check" ((output name, source path)), "gate" (shell command)}`. A
    verdict is earned by running the gate cold; from then on an
    identical layer is `reused`, never `earned` again, and the row
    always carries `source` -- when it was earned and which cache it
    came from, so cheaper is louder, never quieter.
    """
    rows = []
    for layer in spec:
        key = _layer_key(layer)
        cached = _get(key)
        if cached is not None:
            rows.append({"name": layer["name"], "status": "reused",
                         "ok": cached["ok"], "reused": True,
                         "source": cached["source"]})
            continue

        ok = _earn_layer(layer)
        row = {"name": layer["name"], "status": "earned" if ok else "failed",
               "ok": ok, "reused": False}
        if ok:
            source = {"earned_when": _util.stamp(), "cache": _cache_path()}
            _put(key, {"ok": True, "source": source})
            row["source"] = source
        rows.append(row)

    return {"ok": all(r["ok"] for r in rows), "layers": rows}
