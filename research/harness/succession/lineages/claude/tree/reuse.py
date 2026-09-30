"""reticuli.reuse -- key a verdict by identity, build, and host.

A verdict earned on this exact root, these exact concrete bytes
(`build_digest`), this exact platform and interpreter is safe to hand
back on a later, identical run -- nothing about the claim or the host
that could change its outcome has changed.  The fingerprint carries all
four; any mismatch is a fresh claim as far as `lookup` is concerned.

Failing verdicts are never remembered: a failure carries no information
beyond "try again," so caching one would only let a stale bad answer
outlive the reason for it.

Stdlib only.  Never the network.
"""
import hashlib
import json
import os
import platform

from . import kernel

_CACHE = os.path.join(kernel.STORE, "reuse.json")


def fingerprint(d: str) -> dict:
    """`{root, build, platform, python}` for the claim sealed at `d`."""
    manifest = kernel.read_manifest(d)
    return {
        "root": manifest["root"],
        "build": kernel.build_digest(d),
        "platform": platform.platform(),
        "python": platform.python_version(),
    }


def _digest(fp: dict) -> str:
    payload = json.dumps(fp, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _load(d: str) -> dict:
    path = os.path.join(d, _CACHE)
    try:
        with open(path, encoding="utf-8") as f:
            entries = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    return entries if isinstance(entries, dict) else {}


def remember(d: str, verdict: dict) -> None:
    """Record `verdict` under this run's fingerprint -- unless it failed."""
    if not verdict.get("ok"):
        return
    fp = fingerprint(d)
    entries = _load(d)
    entries[_digest(fp)] = {"fingerprint": fp, "verdict": verdict}
    path = os.path.join(d, _CACHE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entries, f, sort_keys=True)


def lookup(d: str):
    """The remembered verdict for this exact fingerprint, or `None`."""
    fp = fingerprint(d)
    entry = _load(d).get(_digest(fp))
    if entry is None or entry.get("fingerprint") != fp:
        return None
    return entry.get("verdict")
