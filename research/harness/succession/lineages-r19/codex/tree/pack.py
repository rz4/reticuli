"""Turn an existing project and its check into a self-contained claim."""

from __future__ import annotations

import glob
import os

from . import _util, kernel, registry, render, transfer


def _paths(root, patterns):
    result = set()
    for pattern in patterns:
        _util.safe_path(root, pattern)
        for path in glob.glob(os.path.join(root, pattern), recursive=True):
            name = os.path.relpath(path, root).replace(os.sep, "/")
            _util.safe_path(root, name)
            if os.path.isfile(path):
                kernel._hash_file(path)
                result.add(name)
    return sorted(result)


def _existing(root, name):
    path = _util.safe_path(root, name)
    if not os.path.isfile(path):
        raise kernel.ClaimError(f"missing file: {name}")
    kernel._hash_file(path)
    return path


def pack(root, name, generated, inputs, gate, gate_output, *,
         component=None, envelope=None, claim_format=3, mutation_floor=None,
         requires=None, by=None, inputs_manifest=None, environment=None):
    root = os.path.abspath(root)
    os.makedirs(root, exist_ok=True)
    generated_names = _paths(root, generated)
    input_names = _paths(root, inputs)
    if not generated_names:
        raise kernel.ClaimError("no generated files match")
    if set(generated_names) & set(input_names):
        raise kernel.ClaimError("generated files overlap claimed inputs")
    _util.safe_path(root, gate_output)
    if environment is not None:
        _existing(root, environment)
    if inputs_manifest is not None:
        _util.safe_path(root, inputs_manifest)
        if claim_format < 2:
            raise kernel.ClaimError("inputs_manifest needs format 2 or newer")

    claim = {"name": name}
    if claim_format != 1:
        claim["format"] = claim_format
    if inputs_manifest is None:
        if input_names:
            claim["inputs"] = input_names
    else:
        listing = "".join(f"{kernel._hash_file(_existing(root, item))}  {item}\n"
                          for item in input_names)
        with open(_util.safe_path(root, inputs_manifest), "w", encoding="utf-8") as stream:
            stream.write(listing)
        claim["inputs_manifest"] = inputs_manifest
    if envelope is not None:
        claim["envelope"] = envelope
    if mutation_floor is not None:
        claim["mutation_floor"] = mutation_floor
    if requires is not None:
        claim["requires"] = requires
    if environment is not None:
        claim["environment"] = environment

    component_name = component["name"] if component else None
    component_outputs = set(component.get("outputs", [])) if component else set()
    steps = []
    for output in generated_names:
        step = {"kind": "produce", "output": output, "class": "generated"}
        if output in component_outputs:
            step["from"] = component_name
        else:
            step["request" if claim_format < 3 else "guidance"] = f"regenerate {output} to pass the gate"
        steps.append(step)
    steps.append({"kind": "gate", "output": gate_output, "class": "validated", "run": gate})
    parsed = {"claim": claim, "step": steps}
    if kernel.vacuous_gates(parsed):
        raise kernel.ClaimError("vacuous gate: all deciders are generated")

    recipe_path = os.path.join(root, kernel.RECIPE)
    with open(recipe_path, "w", encoding="utf-8") as stream:
        stream.write(render.dump_recipe(parsed))
    parsed = kernel.load_recipe(root)
    links = []
    if component:
        source = os.path.abspath(component["claim"])
        manifest = kernel.read_manifest(source)
        if not kernel.verify(source)["ok"] or manifest["name"] != component_name:
            raise kernel.ClaimError("component identity mismatch")
        target = os.path.join(root, kernel.STORE, "sealed", component_name)
        transfer._copy_declared(source, target, blind=False, dependencies=False)
        for output in sorted(component_outputs):
            _existing(root, output)
            _existing(source, output)
            if kernel._hash_file(os.path.join(root, output)) != kernel._hash_file(os.path.join(source, output)):
                raise kernel.ClaimError("component output differs: " + output)
            links.append({"input": output, "component": component_name,
                          "output": output, "root": manifest["root"]})

    outcome = kernel.run_gate(gate, root, parsed)
    if outcome["status"] != "ok":
        raise kernel.ClaimError("gate " + outcome["status"] + ": " + outcome["stderr"][-300:])
    _existing(root, gate_output)
    manifest = registry.seal_with(root, components=links)
    if by is not None:
        kernel.ledger(root, {"event": "producer", "model": by})
    result = kernel.verify(root)
    if not result["ok"]:
        raise kernel.ClaimError("packed identity mismatch")
    return {"ok": True, "root": manifest["root"], "name": name, "path": root}
