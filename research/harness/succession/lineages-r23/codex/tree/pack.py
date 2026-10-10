"""Author a project claim from its declared implementation and checks."""
import glob
import os
import shutil

from . import kernel, registry, render
from ._util import safe_path


def _expand(directory, patterns):
    found = []
    for pattern in patterns:
        safe_path(directory, pattern)
        matches = sorted(glob.glob(os.path.join(directory, pattern), recursive=True))
        for path in matches:
            if os.path.isfile(path):
                name = os.path.relpath(path, directory).replace(os.sep, "/")
                if name not in found:
                    found.append(name)
    return found


def pack(root, name, generated, inputs, gate, gate_output, *,
         envelope=None, claim_format=3, component=None, mutation_floor=None,
         requires=None, by=None, inputs_manifest=None, environment=None):
    root = os.path.abspath(root)
    generated = _expand(root, generated)
    inputs = _expand(root, inputs)
    if environment is not None:
        path = safe_path(root, environment)
        kernel._hash_file(path)
    if not generated:
        raise kernel.ClaimError("pack needs a generated implementation")
    if set(generated) & set(inputs):
        raise kernel.ClaimError("generated and pinned inputs overlap")
    claim = {"name": name}
    if claim_format != 1:
        claim["format"] = claim_format
    if inputs_manifest:
        safe_path(root, inputs_manifest)
        with open(os.path.join(root, inputs_manifest), "w", encoding="utf-8") as out:
            for item in inputs:
                out.write(kernel._hash_file(os.path.join(root, item)) + "  " + item + "\n")
        claim["inputs_manifest"] = inputs_manifest
    else:
        claim["inputs"] = inputs
    if envelope is not None:
        claim["envelope"] = envelope
    if mutation_floor is not None:
        claim["mutation_floor"] = mutation_floor
    if requires is not None:
        claim["requires"] = requires
    if environment is not None:
        claim["environment"] = environment
    steps = []
    supplied = set()
    links = []
    if component is not None:
        source = os.path.abspath(component["claim"])
        manifest = kernel.read_manifest(source)
        if not kernel.verify(source)["ok"]:
            raise kernel.ClaimError("component identity mismatch")
        cname = component["name"]
        if cname != manifest["name"]:
            raise kernel.ClaimError("component name mismatch")
        for output in component["outputs"]:
            safe_path(root, output)
            kernel._hash_file(os.path.join(source, output))
            if output not in generated and output not in inputs:
                raise kernel.ClaimError("component output is not declared")
            supplied.add(output)
            links.append({"input": output, "component": cname,
                          "output": output, "root": manifest["root"]})
        destination = os.path.join(root, kernel.STORE, "sealed", cname)
        if os.path.exists(destination):
            shutil.rmtree(destination)
        registry._copy_claim(source, destination)
        # Preserve links to a component's own immediate dependencies without
        # copying its whole ancestor store into every descendant.
        sidecar = os.path.join(source, kernel.STORE, "components.json")
        if os.path.isfile(sidecar):
            shutil.copyfile(sidecar, os.path.join(destination, kernel.STORE, "components.json"))
    hint_key = "request" if claim_format == 1 else "guidance"
    for output in generated:
        step = {"kind": "produce", "output": output, "class": "generated"}
        if output in supplied:
            step["from"] = component["name"]
        else:
            step[hint_key] = f"regenerate {output} to pass the gate"
        steps.append(step)
    steps.append({"kind": "gate", "output": gate_output,
                  "class": "validated", "run": gate})
    recipe = {"claim": claim, "step": steps}
    if kernel.vacuous_gates(recipe):
        raise kernel.ClaimError("vacuous gate: every decider is generated")
    recipe_path = os.path.join(root, kernel.RECIPE)
    with open(recipe_path, "w", encoding="utf-8") as out:
        out.write(render.dump_recipe(recipe))
    result = kernel.run_gate(gate, root, recipe)
    if result["status"] != "ok":
        raise kernel.ClaimError("gate failed: " + result.get("stderr", ""))
    kernel._hash_file(os.path.join(root, gate_output))
    manifest = registry.seal_with(root, components=links)
    if by:
        kernel.ledger(root, {"event": "producer", "model": by})
    return {"ok": True, "root": manifest["root"], "name": name}
