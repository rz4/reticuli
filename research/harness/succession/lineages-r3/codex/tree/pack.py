"""Seal a project with its implementation declared as generated output."""

from __future__ import annotations

import glob
import hashlib
import os
import shutil

from . import kernel, render
from ._util import safe_path


def _expand(root, patterns):
    names = set()
    for pattern in patterns:
        safe_path(root, pattern)
        matches = glob.glob(os.path.join(root, pattern), recursive=True)
        for path in matches:
            if os.path.isfile(path):
                name = os.path.relpath(path, root).replace(os.sep, "/")
                safe_path(root, name)
                names.add(name)
    return sorted(names)


def pack(root, name, generated, inputs, gate, gate_output, *,
         envelope=None, claim_format=None, component=None,
         mutation_floor=None, requires=None, by=None,
         inputs_manifest=None, environment=None):
    root = os.path.abspath(root)
    if not os.path.isdir(root):
        raise kernel.ClaimError("project directory is missing")
    outputs = _expand(root, generated)
    pinned = _expand(root, inputs)
    if not outputs:
        raise kernel.ClaimError("pack has no generated files")
    if environment is not None:
        path = safe_path(root, environment)
        if not os.path.isfile(path):
            raise kernel.ClaimError("environment file is missing: " + environment)
    safe_path(root, gate_output)
    if set(outputs) & set(pinned):
        raise kernel.ClaimError("file declared both generated and pinned")
    carried = {}
    links = []
    if component is not None:
        child_name = component["name"]
        source = component["claim"]
        checked = kernel.verify(source)
        if not checked["ok"]:
            raise kernel.ClaimError("component identity mismatch")
        destination = os.path.join(root, kernel.STORE, "sealed", child_name)
        if os.path.exists(destination):
            shutil.rmtree(destination)
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        shutil.copytree(source, destination)
        for output in component["outputs"]:
            safe_path(source, output)
            safe_path(root, output)
            if not os.path.isfile(os.path.join(root, output)):
                os.makedirs(os.path.dirname(os.path.join(root, output)), exist_ok=True)
                shutil.copyfile(os.path.join(source, output), os.path.join(root, output))
            carried[output] = child_name
            links.append({"input": output, "component": child_name,
                          "root": checked["root"], "output": output})
            if output not in outputs:
                outputs.append(output)
    claim = {"name": name}
    if claim_format is not None or inputs_manifest is not None:
        claim["format"] = claim_format if claim_format is not None else 2
    if inputs_manifest is None:
        claim["inputs"] = pinned
    else:
        safe_path(root, inputs_manifest)
        with open(os.path.join(root, inputs_manifest), "w", encoding="utf-8") as stream:
            for path in pinned:
                with open(os.path.join(root, path), "rb") as item:
                    digest = hashlib.sha256(item.read()).hexdigest()
                stream.write(f"{digest}  {path}\n")
        claim["inputs_manifest"] = inputs_manifest
    if envelope is not None:
        claim["envelope"] = envelope
    if mutation_floor is not None:
        claim["mutation_floor"] = mutation_floor
    if requires is not None:
        claim["requires"] = requires
    if environment is not None:
        claim["environment"] = environment
    steps = []
    for path in sorted(outputs):
        item = {"kind": "produce", "output": path, "class": "generated"}
        if path in carried:
            item["from"] = carried[path]
        steps.append(item)
    steps.append({"kind": "gate", "output": gate_output,
                  "class": "validated", "run": gate})
    parsed = {"claim": claim, "step": steps}
    if kernel.vacuous_gates(parsed):
        raise kernel.ClaimError("vacuous gate: its deciders are generated")
    with open(os.path.join(root, kernel.RECIPE), "w", encoding="utf-8") as stream:
        stream.write(render.dump_recipe(parsed))
    parsed = kernel.load_recipe(root)
    outcome = kernel.run_gate(gate, root, parsed)
    if outcome["status"] != "ok":
        raise kernel.ClaimError("gate " + outcome["status"] + ": " + outcome.get("stderr", ""))
    if not os.path.isfile(safe_path(root, gate_output)):
        raise kernel.ClaimError("gate did not write its verdict: " + gate_output)
    manifest = kernel.seal(root)
    if links:
        manifest["components"] = links
        from ._util import write_json
        write_json(os.path.join(root, kernel.MANIFEST), manifest)
    if by is not None:
        kernel.ledger(root, {"event": "producer", "model": by})
    return {"ok": kernel.verify(root)["ok"], "root": manifest["root"], "path": root}
