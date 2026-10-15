"""A content-addressed verdict cache -- reuse as a promise, not a shortcut.

Re-earning a verdict means recomputing the identity and re-running every
gate on present bytes. That is the only way to *earn* one. But two
audits that ask the same question of the same bytes on the same host are
asking a question this tool has already answered: same root (what the
claim is), same build digest (which concrete bytes), same platform and
interpreter (what the host's answer could even depend on). `fingerprint`
names that question; `remember`/`lookup` cache the answer to it.

The promise this cache keeps: **a failing verdict is never remembered.**
A cached failure would let a later caller skip work on the strength of a
verdict that said no -- the one case where skipping work is never safe,
because the whole point of redoing it is to find out whether "no" is
still true. A passing verdict costs nothing to trust twice; a failing one
must always be re-earned.

`layered_audit` applies the same cache to a composed, multi-layer claim:
each layer's own files are content-addressed, so an unchanged layer's
verdict is reused while a changed one is re-earned -- and every row says
plainly which happened, naming the host and time that earned a reused
verdict rather than silently calling it fresh.

Cache location: `RETICULI_CACHE`, read fresh on every call so a caller
may redirect it per run (as the three-machine test does, to keep an
audit's cache from leaking into another's); a private spot under the
platform's temp directory otherwise. Stdlib only.
"""
import hashlib
import json
import os
import platform
import shutil
import subprocess
import tempfile
import time

from reticuli import kernel

_ENV_CACHE = "RETICULI_CACHE"


def _cache_dir() -> str:
    override = os.environ.get(_ENV_CACHE)
    if override:
        return override
    return os.path.join(tempfile.gettempdir(), "reticuli", "verdict-cache")


def _canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=True).encode("utf-8")


def _digest(obj) -> str:
    return hashlib.sha256(_canonical(obj)).hexdigest()


def _write_atomic(path: str, obj) -> None:
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(obj, sort_keys=True, ensure_ascii=True))
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _read_json(path: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _stamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# -- fingerprint: identity + concrete bytes + host ----------------------------


def fingerprint(d: str) -> dict:
    """A verdict's natural key for claim `d`.

    Two audits sharing a root, a build digest, a platform, and an
    interpreter asked the same question of the same bytes on hardware
    that could give the same answer -- they are comparable. Anything
    else is a different question and gets a different key.
    """
    manifest = kernel.read_manifest(d)
    return {
        "root": manifest["root"],
        "build": kernel.build_digest(d),
        "platform": f"{platform.system().lower()}-{platform.machine()}",
        "python": platform.python_version(),
    }


def remember(d: str, verdict: dict) -> None:
    """Cache `verdict` under `d`'s fingerprint -- unless it failed.

    An absent or falsy `verdict["ok"]` is never written: a cached
    failure is the one thing this cache must not produce.
    """
    if not verdict.get("ok"):
        return
    fp = fingerprint(d)
    path = os.path.join(_cache_dir(), "fingerprints", f"{_digest(fp)}.json")
    _write_atomic(path, {"fingerprint": fp, "verdict": verdict})


def lookup(d: str):
    """The cached verdict matching `d`'s current fingerprint, or `None`."""
    fp = fingerprint(d)
    path = os.path.join(_cache_dir(), "fingerprints", f"{_digest(fp)}.json")
    if not os.path.isfile(path):
        return None
    entry = _read_json(path)
    if entry is None or entry.get("fingerprint") != fp:
        return None
    return entry.get("verdict")


# -- layered audit: one content-addressed cache entry per layer --------------


def _layer_key(layer: dict, digests: dict) -> str:
    return _digest({"name": layer["name"], "gate": layer["gate"], "files": digests})


def _layer_path(key: str) -> str:
    return os.path.join(_cache_dir(), "layers", f"{key}.json")


def _build_room(layer: dict) -> tuple:
    """A fresh directory holding exactly this layer's declared files, and
    the sha256 of each one, keyed by its name inside the room."""
    room = tempfile.mkdtemp(prefix="layer-")
    files = dict(layer.get("files", {}))
    check_name, check_src = layer["check"]
    files[check_name] = check_src

    digests = {}
    for name, src in sorted(files.items()):
        dst = os.path.join(room, name)
        os.makedirs(os.path.dirname(dst) or room, exist_ok=True)
        shutil.copy2(src, dst)
        with open(dst, "rb") as f:
            digests[name] = hashlib.sha256(f.read()).hexdigest()
    return room, digests


def _run_layer_gate(layer: dict, room: str) -> bool:
    result = subprocess.run(layer["gate"], shell=True, cwd=room,
                             capture_output=True)
    return result.returncode == 0


def layered_audit(spec: list) -> dict:
    """Audit each layer of a composed claim, reusing a layer's verdict
    when its own files are byte-for-byte what last earned it.

    `spec` is a list of layers, each a dict with `name`, `files` (a map
    of room-relative path to source path), `check` (a `(name, source
    path)` pair for the acceptance script), and `gate` (the shell
    command to run in the room). Every row of the result names its
    layer and says `earned` (the gate ran, this time) or `reused` (an
    earlier earning matched and was returned instead), and a `reused`
    row always carries `source`: who and when earned the verdict it is
    standing on.
    """
    rows = []
    overall_ok = True
    for layer in spec:
        room, digests = _build_room(layer)
        try:
            key = _layer_key(layer, digests)
            cached = _read_json(_layer_path(key))
            if cached is not None:
                rows.append({
                    "name": layer["name"],
                    "verdict": layer.get("verdict"),
                    "status": "reused",
                    "reused": True,
                    "ok": cached["ok"],
                    "source": cached["source"],
                })
                overall_ok = overall_ok and cached["ok"]
                continue

            ok = _run_layer_gate(layer, room)
            source = {"platform": platform.system().lower(),
                      "python": platform.python_version(),
                      "when": _stamp()}
            if ok:
                _write_atomic(_layer_path(key), {"ok": ok, "source": source})
            rows.append({
                "name": layer["name"],
                "verdict": layer.get("verdict"),
                "status": "earned",
                "reused": False,
                "ok": ok,
                "source": source,
            })
            overall_ok = overall_ok and ok
        finally:
            shutil.rmtree(room, ignore_errors=True)
    return {"ok": overall_ok, "layers": rows}
