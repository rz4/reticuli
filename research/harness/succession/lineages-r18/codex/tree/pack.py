"""Turn a project's checks and generated implementation into a claim."""
import glob
import os
import shutil

from . import kernel, registry, render
from ._util import safe_path, write_json


def _expand(root, patterns):
    names = set()
    for pattern in patterns:
        safe_path(root, pattern)
        for path in glob.glob(os.path.join(root, pattern), recursive=True):
            if os.path.isfile(path):
                name = os.path.relpath(path, root).replace(os.sep, "/")
                safe_path(root, name)
                names.add(name)
    return sorted(names)


def pack(root, name, generated, inputs, gate, gate_output, *, envelope=None,
         claim_format=3, component=None, mutation_floor=None, requires=None,
         by=None, inputs_manifest=None, environment=None):
    root = os.fspath(root)
    generated = _expand(root, generated)
    inputs = _expand(root, inputs)
    if environment:
        path = safe_path(root, environment)
        kernel._hash_file(path)
    if inputs_manifest and claim_format < 2:
        raise kernel.ClaimError("inputs_manifest requires format 2")
    claim = {"name": name}
    if claim_format != 1:
        claim["format"] = claim_format
    if inputs_manifest:
        manifest = safe_path(root, inputs_manifest)
        os.makedirs(os.path.dirname(manifest), exist_ok=True)
        with open(manifest, "w", encoding="utf-8") as stream:
            for item in inputs:
                stream.write(f"{kernel._hash_file(safe_path(root, item))}  {item}\n")
        claim["inputs_manifest"] = inputs_manifest
    else:
        claim["inputs"] = inputs
    if environment:
        claim["environment"] = environment
    if envelope is not None:
        claim["envelope"] = envelope
    if mutation_floor is not None:
        claim["mutation_floor"] = mutation_floor
    if requires is not None:
        claim["requires"] = requires
    supplied = set()
    links = []
    if component:
        comp_name = component["name"]
        comp_path = os.fspath(component["claim"])
        checked = kernel.verify(comp_path)
        if not checked["ok"]:
            raise kernel.ClaimError("component identity mismatch")
        for output in component["outputs"]:
            safe_path(root, output)
            if output not in generated and output not in inputs:
                raise kernel.ClaimError("component output is not declared: " + output)
            if kernel._hash_file(safe_path(root, output)) != kernel._hash_file(safe_path(comp_path, output)):
                raise kernel.ClaimError("component output differs: " + output)
            supplied.add(output)
            links.append({"input": output, "component": comp_name,
                          "output": output, "root": checked["root"]})
    steps = []
    for output in generated:
        step = {"kind": "produce", "output": output, "class": "generated"}
        step["request" if claim_format == 1 else "guidance"] = f"regenerate {output} to pass the gate"
        if output in supplied:
            step["from"] = component["name"]
        steps.append(step)
    steps.append({"kind": "gate", "output": gate_output, "class": "validated", "run": gate})
    document = {"claim": claim, "step": steps}
    if kernel.vacuous_gates(document):
        raise kernel.ClaimError("vacuous gate: every decider is generated")
    recipe_path = os.path.join(root, kernel.RECIPE)
    with open(recipe_path, "w", encoding="utf-8") as stream:
        stream.write(render.dump_recipe(document))
    kernel.load_recipe(root)
    result = kernel.run_gate(gate, root, document)
    if result["status"] != "ok" or not os.path.isfile(safe_path(root, gate_output)):
        raise kernel.ClaimError("gate failed: " + result.get("stderr", ""))
    if links:
        destination = os.path.join(root, kernel.STORE, "sealed", component["name"])
        if os.path.exists(destination):
            shutil.rmtree(destination)
        shutil.copytree(comp_path, destination, ignore=shutil.ignore_patterns("sealed", "deps", "ledger.jsonl"))
    manifest = registry.seal_with(root, components=links) if links else kernel.seal(root)
    if by:
        kernel.ledger(root, {"event": "producer", "model": by})
    return {"ok": True, "root": manifest["root"], "name": name}
