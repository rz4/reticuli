"""Turn a project into a claim whose implementation is generated."""

import glob
import os
import shutil

from . import kernel, registry, render
from ._util import copy_into, safe_path


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


def _component(root, component):
    if not component:
        return [], set()
    name = component["name"]
    source = component["claim"]
    if not kernel.verify(source)["ok"]:
        raise kernel.ClaimError("component identity changed")
    manifest = kernel.read_manifest(source)
    target = os.path.join(root, kernel.STORE, "sealed", name)
    if os.path.realpath(source) != os.path.realpath(target):
        if os.path.lexists(target):
            if os.path.isdir(target) and not os.path.islink(target):
                shutil.rmtree(target)
            else:
                os.unlink(target)
        registry._copy_claim(source, target)
    links = []
    outputs = set(component.get("outputs", []))
    for output in sorted(outputs):
        safe_path(root, output)
        origin = safe_path(source, output)
        if not os.path.isfile(origin):
            raise kernel.ClaimError("component output missing: " + output)
        destination = safe_path(root, output)
        if not os.path.exists(destination):
            copy_into(origin, destination)
        elif kernel._hash_file(destination) != kernel._hash_file(origin):
            raise kernel.ClaimError("component output differs: " + output)
        links.append({"input": output, "component": name, "output": output,
                      "root": manifest["root"]})
    return links, outputs


def pack(root, name, generated, inputs, gate, gate_output,
         *, component=None, envelope=None, claim_format=3,
         mutation_floor=None, requires=None, by=None,
         inputs_manifest=None, environment=None):
    root = os.path.abspath(root)
    generated_names = _expand(root, generated)
    input_names = _expand(root, inputs)
    links, carried = _component(root, component)
    if not input_names and not inputs_manifest and kernel.gate_deciders(gate):
        # An interpreter running only implementation code cannot decide a claim.
        raise kernel.ClaimError("vacuous gate: no claimed decider")
    for path in input_names:
        if path in generated_names:
            raise kernel.ClaimError("path declared both generated and input: " + path)
    claim = {"name": name}
    if claim_format != 1:
        claim["format"] = claim_format
    if inputs_manifest:
        safe_path(root, inputs_manifest)
        with open(safe_path(root, inputs_manifest), "w", encoding="utf-8") as stream:
            for path in input_names:
                stream.write(f"{kernel._hash_file(safe_path(root, path))}  {path}\n")
        claim["inputs_manifest"] = inputs_manifest
    else:
        claim["inputs"] = input_names
    if envelope is not None:
        claim["envelope"] = envelope
    if mutation_floor is not None:
        claim["mutation_floor"] = float(mutation_floor)
    if requires is not None:
        claim["requires"] = requires
    if environment is not None:
        safe_path(root, environment)
        if not os.path.isfile(os.path.join(root, environment)):
            raise kernel.ClaimError("environment file missing: " + environment)
        claim["environment"] = environment
    steps = []
    for path in generated_names:
        step = {"kind": "produce", "output": path, "class": "generated"}
        if path in carried:
            step["from"] = component["name"]
        else:
            step["request" if claim_format == 1 else "guidance"] = f"regenerate {path} to pass the gate"
        steps.append(step)
    steps.append({"kind": "gate", "output": gate_output, "class": "validated", "run": gate})
    parsed = {"claim": claim, "step": steps}
    bad = kernel.vacuous_gates(parsed)
    if bad:
        raise kernel.ClaimError("vacuous gate: " + ", ".join(bad))
    recipe_path = os.path.join(root, kernel.RECIPE)
    with open(recipe_path, "w", encoding="utf-8") as stream:
        stream.write(render.dump_recipe(parsed))
    verdict_path = safe_path(root, gate_output)
    if os.path.exists(verdict_path):
        os.unlink(verdict_path)
    result = kernel.run_gate(gate, root, parsed)
    if result["status"] != "ok" or not os.path.isfile(verdict_path):
        raise kernel.ClaimError("gate failed: " + result.get("stderr", result["status"]))
    sealed = registry.seal_with(root, components=links)
    if by:
        kernel.ledger(root, {"event": "producer", "model": by})
    return {"ok": True, "root": sealed["root"], "name": name,
            "gates": [{"output": gate_output, **result}]}
