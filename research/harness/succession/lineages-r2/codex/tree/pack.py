"""Pack a project as a claim whose implementation can be regrown."""
from __future__ import annotations

import glob
import os
import shutil

from . import kernel, render, registry
from ._util import safe_path, copy_into


def _expand(root, patterns):
    names = []
    for pattern in patterns:
        safe_path(root, pattern)
        for path in sorted(glob.glob(os.path.join(root, pattern), recursive=True)):
            if os.path.isfile(path):
                name = os.path.relpath(path, root).replace(os.sep, "/")
                safe_path(root, name)
                if name not in names:
                    names.append(name)
    return names


def pack(root, name, generated, inputs, gate, gate_output,
         *, envelope=None, claim_format=None, component=None):
    root = os.path.realpath(root)
    produced = _expand(root, generated)
    pinned = _expand(root, inputs)
    if not produced:
        raise kernel.ClaimError("no generated files matched")
    if not pinned:
        # The kernel's decider analysis makes this refusal concrete below.
        pass
    if set(produced) & set(pinned):
        raise kernel.ClaimError("file cannot be both generated and input")
    safe_path(root, gate_output)
    claim = {"name": name, "inputs": pinned}
    if claim_format is not None:
        claim["format"] = claim_format
    if envelope is not None:
        claim["envelope"] = envelope
    steps = [{"kind": "produce", "output": item, "class": "generated"} for item in produced]
    links = []
    if component is not None:
        comp_name = component["name"]
        comp_path = component["claim"]
        if not isinstance(comp_name, str) or not comp_name or "/" in comp_name or comp_name in (".", ".."):
            raise kernel.ClaimError("invalid component name")
        checked = kernel.verify(comp_path)
        if not checked["ok"]:
            raise kernel.ClaimError("component identity mismatch")
        for item in component["outputs"]:
            safe_path(root, item)
            matched = next((step for step in steps if step["output"] == item), None)
            if matched is None:
                raise kernel.ClaimError("component output is not generated: " + item)
            matched["from"] = comp_name
            links.append({"input": item, "component": comp_name,
                          "root": checked["root"], "output": item})
    steps.append({"kind": "gate", "output": gate_output, "class": "validated", "run": gate})
    recipe = {"claim": claim, "step": steps}
    if kernel.vacuous_gates(recipe):
        raise kernel.ClaimError("vacuous gate: every decider is generated")
    recipe_path = os.path.join(root, kernel.RECIPE)
    with open(recipe_path, "w", encoding="utf-8") as stream:
        stream.write(render.dump_recipe(recipe))
    parsed = kernel.load_recipe(root)
    verdict = safe_path(root, gate_output)
    if os.path.isfile(verdict):
        os.unlink(verdict)
    outcome = kernel.run_gate(gate, root, parsed)
    if outcome["status"] != "ok":
        raise kernel.ClaimError("gate " + outcome["status"] + ": " + outcome.get("stderr", "")[-300:])
    kernel._hash_file(verdict)
    if links:
        store = os.path.join(root, kernel.STORE, "sealed", comp_name)
        if os.path.exists(store):
            shutil.rmtree(store)
        shutil.copytree(comp_path, store)
        manifest = registry.seal_with(root, components=links)
    else:
        manifest = kernel.seal(root)
    return {"ok": kernel.verify(root)["ok"], "root": manifest["root"], "path": root}
