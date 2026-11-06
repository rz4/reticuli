"""The verdict cache: skipping work already earned, and SAYING SO.

Re-earning a verdict is the expensive part of verification, and a layered
audit over a deep chain re-earns the same inner layers again and again. A
cache is the obvious economy and a dangerous one, so it is bound by three
rules:

  * REUSED IS NEVER SPELLED EARNED. A row that was not re-run says
    `reused`, names when the verdict was earned and whose trust it leaned
    on. Cheaper is louder, never quieter.
  * A FINGERPRINT KEYS ON EVERYTHING THAT COULD CHANGE THE ANSWER: the
    root (which claim), the build digest (which bytes), the platform and
    the interpreter (which host). A verdict is about a host as much as a
    claim.
  * A FAILURE IS NEVER REMEMBERED. A refusal may be environmental, and a
    cached one would make a one-off failure permanent; a pass is a positive
    fact about bytes, and that is all this cache holds.
"""
import os
import platform
import shutil
import subprocess
import sys
import tempfile

from . import _util
from . import kernel
from . import render


def _cache_dir() -> str:
    configured = os.environ.get("RETICULI_CACHE")
    if configured:
        return configured
    return os.path.join(os.path.expanduser("~"), ".cache", "reticuli",
                        "verdicts")


def fingerprint(claim: str) -> dict:
    """What a cached verdict is about: this claim, these bytes, this host."""
    checked = kernel.verify(claim)
    return {"root": checked["recomputed"],
            "build": kernel.build_digest(claim),
            "platform": sys.platform,
            "python": f"{platform.python_implementation()} "
                      f"{platform.python_version()}"}


def _key(found: dict) -> str:
    return _util.hash_bytes(
        "|".join(f"{k}={found[k]}" for k in sorted(found)))


def remember(claim: str, verdict: dict, where: str | None = None) -> str:
    """Record a PASSING verdict against this fingerprint."""
    if not verdict or not verdict.get("ok"):
        return ""
    found = fingerprint(claim)
    path = os.path.join(_cache_dir(), _key(found) + ".json")
    _util.write_json(path, {"fingerprint": found, "when": _util.stamp(),
                            "host": platform.node() or "unknown",
                            "verdict": {"ok": True,
                                        "gates": verdict.get("gates") or []}})
    return path


def lookup(claim: str, where: str | None = None):
    """A cached verdict for exactly these bytes on this host, or None."""
    found = fingerprint(claim)
    path = os.path.join(_cache_dir(), _key(found) + ".json")
    entry = _util.read_json(path)
    if not isinstance(entry, dict) or entry.get("fingerprint") != found:
        return None
    return entry


def forget(claim: str) -> None:
    found = fingerprint(claim)
    path = os.path.join(_cache_dir(), _key(found) + ".json")
    if os.path.isfile(path):
        os.remove(path)


def _stage(layer: dict, room: str) -> None:
    """Build one layer of a spec into a claim-shaped room."""
    os.makedirs(room, exist_ok=True)
    generated = []
    for name, source in sorted((layer.get("files") or {}).items()):
        _util.copy_into(source, _util.safe_path(room, name))
        generated.append(name)
    check_name, check_source = layer["check"]
    _util.copy_into(check_source, _util.safe_path(room, check_name))
    verdict = layer.get("verdict") or "OK"
    # the spec names a CHECK and the verdict it should pin; pinning it is
    # this layer's business, so the gate earns the file it declares
    run = f"{layer['gate']} && printf ok > {verdict}"
    recipe = {"claim": {"name": layer["name"], "format": 3,
                        "inputs": [check_name]},
              "step": [{"kind": "produce", "output": name,
                        "class": "generated"} for name in generated]
                      + [{"kind": "gate", "output": verdict,
                          "class": "validated", "run": run}]}
    with open(os.path.join(room, kernel.RECIPE), "w",
              encoding="utf-8") as handle:
        handle.write(render.dump_recipe(recipe))
    parsed = kernel.load_recipe(room)
    outcome = kernel.run_gate(run, room, parsed)
    if outcome["status"] != "ok":
        raise kernel.ClaimError(
            f"the layer {layer['name']!r} does not earn its verdict warm: "
            f"{(outcome['stderr'] or outcome['stdout'])[-200:]}")
    kernel.seal(room)


def layered_audit(spec) -> dict:
    """Audit a chain of layers, reusing whatever was already earned.

    Each row says which it was. Nothing cached means everything is redone --
    the cache is an economy, never a source of verdicts.
    """
    rooms = tempfile.mkdtemp(prefix="reticuli-layers-")
    rows = []
    try:
        for layer in spec or []:
            room = os.path.join(rooms, layer["name"])
            _stage(layer, room)
            cached = lookup(room)
            if cached:
                rows.append({"name": layer["name"], "status": "reused",
                             "ok": True, "reused": True,
                             "when": cached.get("when"),
                             "source": cached.get("host") or "a cache",
                             "root": cached["fingerprint"]["root"]})
                continue
            verdict = kernel.audit(room)
            if verdict["ok"]:
                remember(room, verdict)
            rows.append({"name": layer["name"], "status": "earned",
                         "ok": bool(verdict["ok"]), "reused": False,
                         "when": _util.stamp(), "source": None,
                         "root": verdict["recomputed"],
                         "gates": verdict["gates"]})
        return {"ok": all(row["ok"] for row in rows) if rows else True,
                "layers": rows}
    finally:
        shutil.rmtree(rooms, ignore_errors=True)
