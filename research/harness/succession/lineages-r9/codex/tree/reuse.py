"""Cache passing verdicts under all the bytes and host facts they depend on."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import sys
import tempfile

from . import kernel
from ._kernel import core


def _canonical(value):
    return json.dumps(value, sort_keys=True).encode("utf-8")


def _cache_dir():
    return os.path.abspath(os.path.expanduser(
        os.environ.get("RETICULI_CACHE", "~/.cache/reticuli/verdicts")))


def _key(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _path(value):
    return os.path.join(_cache_dir(), _key(value) + ".json")


def _read(value):
    try:
        with open(_path(value), encoding="utf-8") as source:
            saved = json.load(source)
    except (OSError, ValueError):
        return None
    return saved if saved.get("fingerprint") == value and saved.get("verdict", {}).get("ok") is True else None


def _write(value, verdict, source):
    if verdict.get("ok") is not True:
        return None
    target = _path(value)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    saved = {"fingerprint": value, "verdict": verdict,
             "source": source, "when": core._now()}
    fd, temporary = tempfile.mkstemp(dir=os.path.dirname(target), prefix=".verdict-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(saved, output, sort_keys=True)
            output.write("\n")
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return saved


def fingerprint(directory):
    """Identify a concrete claim build on this interpreter and platform."""
    checked = kernel.verify(directory)
    if not checked["ok"]:
        raise kernel.ClaimError("cannot reuse a claim whose identity has drifted")
    return {"root": checked["root"], "build": kernel.build_digest(directory),
            "platform": platform.platform(), "python": sys.version}


def lookup(directory):
    """Return a previously passing verdict for these exact claim and host facts."""
    saved = _read(fingerprint(directory))
    return saved["verdict"] if saved else None


def remember(directory, verdict):
    """Remember only a passing verdict."""
    if not isinstance(verdict, dict) or verdict.get("ok") is not True:
        return None
    return _write(fingerprint(directory), verdict,
                  {"claim": os.path.realpath(directory)})


def _layer_fingerprint(layer):
    files = dict(layer["files"])
    check_name, check_path = layer["check"]
    if check_name in files:
        raise ValueError("check path also appears in layer files")
    files[check_name] = check_path
    digests = {name: kernel._hash_file(path) for name, path in files.items()}
    return {"layer": layer["name"], "files": digests,
            "gate": layer["gate"], "verdict": layer["verdict"],
            "platform": platform.platform(), "python": sys.version}


def _earn(layer):
    check_name, check_path = layer["check"]
    files = dict(layer["files"])
    files[check_name] = check_path
    with tempfile.TemporaryDirectory(prefix="reticuli-layer-") as room:
        for name, source in files.items():
            destination = core._safe(room, name)
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            shutil.copyfile(source, destination)
        result = kernel.run_gate(layer["gate"], room)
        return {"ok": result["status"] == "ok",
                "gate": result, "verdict": layer["verdict"]}


def layered_audit(layers):
    """Earn each layer cold or report precisely which cached verdict was used."""
    rows = []
    for layer in layers:
        fp = _layer_fingerprint(layer)
        saved = _read(fp)
        if saved is not None:
            rows.append({"name": layer["name"], "ok": True,
                         "status": "reused", "reused": saved["when"],
                         "source": saved["source"], "verdict": saved["verdict"]})
            continue
        verdict = _earn(layer)
        if verdict["ok"]:
            _write(fp, verdict, {"layer": layer["name"], "files": fp["files"]})
        rows.append({"name": layer["name"], "ok": verdict["ok"],
                     "status": "earned" if verdict["ok"] else "failed",
                     "verdict": verdict})
    return {"ok": all(row["ok"] for row in rows), "layers": rows}
