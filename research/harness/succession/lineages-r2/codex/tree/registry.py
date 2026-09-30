"""Content-addressed component registry and layered verification."""
from __future__ import annotations

import os
import shutil
import tempfile

from . import kernel
from ._util import copy_into, declared_inputs, safe_path, write_json

MANIFEST = ".reticuli/manifest.json"
if not hasattr(kernel, "MANIFEST"):
    kernel.MANIFEST = MANIFEST


def _workspace(directory):
    directory = os.path.realpath(directory)
    parent = os.path.dirname(directory)
    if os.path.basename(parent) == "sealed" and os.path.basename(os.path.dirname(parent)) == ".reticuli":
        return os.path.dirname(os.path.dirname(parent))
    return directory


def _stores(directory, ws=None):
    homes = [os.path.join(directory, ".reticuli", "deps"),
             os.path.join(directory, ".reticuli", "sealed"),
             os.path.join(ws or _workspace(directory), ".reticuli", "sealed")]
    return list(dict.fromkeys(homes))


def _component(directory, link, ws=None):
    name = link["component"]
    if not isinstance(name, str) or not name or "/" in name or name in (".", ".."):
        raise kernel.ClaimError("invalid component name")
    for store in _stores(directory, ws):
        path = os.path.join(store, name)
        if os.path.isfile(os.path.join(path, MANIFEST)):
            if kernel.verify(path)["root"] != link["root"] or not kernel.verify(path)["ok"]:
                raise kernel.ClaimError(f"component {name} root mismatch")
            return path
    raise kernel.ClaimError(f"missing component {name}")


def _links(directory):
    return kernel.read_manifest(directory).get("components", [])


def seal_with(directory, *, components=None, proof=None):
    manifest = kernel.seal(directory)
    if components is not None:
        manifest["components"] = components
    if proof is not None:
        manifest["proof"] = proof
    write_json(os.path.join(directory, MANIFEST), manifest)
    return manifest


def detect_components(ws, inputs):
    result = []
    store = os.path.join(ws, ".reticuli", "sealed")
    if not os.path.isdir(store):
        return result
    for name in inputs:
        digest = kernel._hash_file(safe_path(ws, name))
        for component in sorted(os.listdir(store)):
            path = os.path.join(store, component)
            try:
                root = kernel.verify(path)
                if not root["ok"]:
                    continue
                for step in kernel.load_recipe(path).get("step", []):
                    output = step["output"]
                    item = safe_path(path, output)
                    if os.path.isfile(item) and kernel._hash_file(item) == digest:
                        result.append({"input": name, "component": component,
                                       "root": root["root"], "output": output})
            except kernel.ClaimError:
                continue
    return result


def claims(ws):
    store = os.path.join(ws, ".reticuli", "sealed")
    result = []
    if os.path.isdir(store):
        for name in sorted(os.listdir(store)):
            path = os.path.join(store, name)
            if os.path.isfile(os.path.join(path, MANIFEST)):
                checked = kernel.verify(path)
                result.append({"name": name, "root": checked["root"], "phase": kernel.phase(path),
                               "ok": checked["ok"], "path": path})
    return result


def deps(ws):
    entries = []
    for row in claims(ws):
        links = []
        for link in _links(row["path"]):
            try:
                _component(row["path"], link, ws)
                status = "ok"
            except kernel.ClaimError:
                status = "missing"
            links.append({**link, "status": status})
        entries.append({**row, "depends_on": links})
    return {"claims": entries}


def structure(directory, ws=None):
    return {"name": kernel.load_recipe(directory)["claim"]["name"],
            "root": kernel.verify(directory)["root"], "phase": kernel.phase(directory),
            "components": _links(directory)}


def sign_root(directory, ws=None, _seen=None):
    seen = set() if _seen is None else _seen
    path = os.path.realpath(directory)
    if path in seen:
        raise kernel.ClaimError("component cycle")
    seen.add(path)
    try:
        checked = kernel.verify(path)
        if not checked["ok"]:
            raise kernel.ClaimError("claim identity mismatch")
        children = [sign_root(_component(path, link, ws), ws, seen) for link in _links(path)]
        return kernel.sign_node(checked["root"], kernel.build_digest(path), children)
    finally:
        seen.remove(path)


def pull(directory, ws):
    if not kernel.verify(directory)["ok"]:
        raise kernel.ClaimError("claim identity mismatch")
    parsed = kernel.load_recipe(directory)
    names = set(declared_inputs(directory, parsed))
    names.update(step["output"] for step in parsed.get("step", []))
    for name in names:
        source = safe_path(directory, name)
        if os.path.isfile(source):
            copy_into(source, safe_path(ws, name))
    return {"materialized": True, "root": kernel.verify(directory)["root"]}


def rebuild_chain(directory, producer, into, *, ws=None, reuse=False, _seen=None):
    seen = set() if _seen is None else _seen
    path = os.path.realpath(directory)
    if path in seen:
        raise kernel.ClaimError("component cycle")
    seen.add(path)
    links = _links(path)
    rebuilt = []
    sources = {}
    try:
        for link in links:
            source = _component(path, link, ws)
            if reuse:
                component_path = source
            else:
                component_path = os.path.join(tempfile.mkdtemp(prefix="reticuli-component-"), link["component"])
                rebuild_chain(source, producer, component_path, ws=ws, reuse=False, _seen=seen)
            rebuilt.append({"component": link["component"], "root": link["root"]})
            sources[link["input"]] = safe_path(component_path, link["output"])
        parsed = kernel.load_recipe(path)
        produced = {step["output"] for step in parsed.get("step", []) if step.get("kind") == "produce"}
        result = kernel.rebuild(path, producer, into,
                                produce_from={n: p for n, p in sources.items() if n in produced},
                                input_from={n: p for n, p in sources.items() if n not in produced})
        if links:
            manifest = kernel.read_manifest(into)
            manifest["components"] = links
            write_json(os.path.join(into, MANIFEST), manifest)
            store = os.path.join(into, ".reticuli", "sealed")
            for link in links:
                source = _component(path, link, ws)
                shutil.copytree(source, os.path.join(store, link["component"]), dirs_exist_ok=True,
                                ignore=shutil.ignore_patterns("ledger.jsonl"))
        return {**result, "rebuilt_components": rebuilt}
    finally:
        seen.remove(path)


def audit_deep(directory, *, ws=None, _seen=None):
    seen = set() if _seen is None else _seen
    path = os.path.realpath(directory)
    if path in seen:
        raise kernel.ClaimError("component cycle")
    seen.add(path)
    own = kernel.audit(path)
    layers = []
    try:
        for link in _links(path):
            name = link["component"]
            try:
                source = _component(path, link, ws)
                with tempfile.TemporaryDirectory(prefix="reticuli-deep-") as room:
                    shutil.copytree(source, room, dirs_exist_ok=True)
                    # The dependent's shipped output is what this layer must judge.
                    copy_into(safe_path(path, link["input"]), safe_path(room, link["output"]))
                    checked = audit_deep(room, ws=ws, _seen=seen)
                layers.append({"name": name, "root": link["root"], "ok": checked["ok"],
                               "status": "ok" if checked["ok"] else "failed",
                               "bytes_from": [link["input"]]})
            except (kernel.ClaimError, OSError):
                layers.append({"name": name, "root": link["root"], "ok": False,
                               "status": "unresolved", "bytes_from": [link["input"]]})
        return {"ok": own["ok"] and all(x["ok"] for x in layers),
                "root": own.get("root"), "layers": layers, "audit": own}
    finally:
        seen.remove(path)


def crosscheck_deep(m1, m2, m3):
    report = kernel.crosscheck(m1, m2, m3)
    deep = {key: audit_deep(path) for key, path in zip(("M1", "M2", "M3"), (m1, m2, m3))}
    report["deep"] = deep
    if not all(item["ok"] for item in deep.values()):
        report["satisfied"] = False
        report["verdict"] = "reject"
    return report


def record_proof_deep(m1, m2, m3):
    deep = crosscheck_deep(m1, m2, m3)
    if deep["satisfied"]:
        return kernel.record_proof(m1, m2, m3)
    return deep
