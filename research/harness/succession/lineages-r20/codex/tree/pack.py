"""Turn a project's declared check and implementation into a claim."""

from __future__ import annotations

import glob
import os
import shutil

from . import kernel, registry, render
from ._util import safe_path, write_json


def _expand(root, patterns):
    names = set()
    for pattern in patterns:
        safe_path(root, pattern)
        matches = glob.glob(os.path.join(root, pattern), recursive=True)
        for path in matches:
            name = os.path.relpath(path, root).replace(os.sep, "/")
            safe_path(root, name)
            if os.path.isfile(path):
                kernel._hash_file(path)
                names.add(name)
        if not matches:
            raise kernel.ClaimError(f"pattern names no file: {pattern}")
    return sorted(names)


def pack(root, name, generated, inputs, gate, gate_output,
         *, envelope=None, claim_format=3, component=None,
         mutation_floor=None, requires=None, by=None,
         inputs_manifest=None, environment=None):
    root = os.path.abspath(root)
    made = _expand(root, generated)
    pinned = _expand(root, inputs)
    safe_path(root, gate_output)
    if environment is not None:
        path = safe_path(root, environment)
        if not os.path.isfile(path):
            raise kernel.ClaimError(f"environment file is absent: {environment}")
        kernel._hash_file(path)
    claim = {"name": name}
    if claim_format != 1:
        claim["format"] = claim_format
    if inputs_manifest:
        path = safe_path(root, inputs_manifest)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as stream:
            for item in pinned:
                stream.write(f"{kernel._hash_file(safe_path(root, item))}  {item}\n")
        claim["inputs_manifest"] = inputs_manifest
    elif pinned:
        claim["inputs"] = pinned
    if envelope is not None:
        claim["envelope"] = envelope
    if mutation_floor is not None:
        claim["mutation_floor"] = mutation_floor
    if requires is not None:
        claim["requires"] = requires
    if environment is not None:
        claim["environment"] = environment

    component_names = set()
    links = []
    if component:
        source = os.path.abspath(component["claim"])
        comp_name = component["name"]
        manifest = kernel.read_manifest(source)
        if manifest["name"] != comp_name or not kernel.verify(source)["ok"]:
            raise kernel.ClaimError("component identity does not hold")
        dest = os.path.join(root, kernel.STORE, "sealed", comp_name)
        if os.path.exists(dest):
            shutil.rmtree(dest)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copytree(source, dest, ignore=shutil.ignore_patterns("sealed"))
        for output in component["outputs"]:
            safe_path(root, output)
            source_path = safe_path(source, output)
            kernel._hash_file(source_path)
            local = safe_path(root, output)
            os.makedirs(os.path.dirname(local), exist_ok=True)
            shutil.copyfile(source_path, local)
            component_names.add(output)
            links.append({"input": output, "component": comp_name,
                          "output": output, "root": manifest["root"]})

    steps = []
    for output in made:
        step = {"kind": "produce", "output": output, "class": "generated"}
        if output in component_names:
            step["from"] = component["name"]
        else:
            step["request" if claim_format == 1 else "guidance"] = f"regenerate {output} to pass the gate"
        steps.append(step)
    for output in sorted(component_names - set(made)):
        steps.append({"kind": "produce", "output": output, "class": "generated",
                      "from": component["name"]})
    steps.append({"kind": "gate", "output": gate_output, "class": "validated", "run": gate})
    parsed = {"claim": claim, "step": steps}
    if kernel.vacuous_gates(parsed):
        raise kernel.ClaimError("vacuous gate: every decider is generated")
    recipe_path = os.path.join(root, kernel.RECIPE)
    with open(recipe_path, "w", encoding="utf-8") as stream:
        stream.write(render.dump_recipe(parsed))
    verdict = safe_path(root, gate_output)
    if os.path.lexists(verdict):
        os.unlink(verdict)
    outcome = kernel.run_gate(gate, root, parsed)
    if outcome["status"] != "ok" or not os.path.isfile(verdict):
        raise kernel.ClaimError("pack gate failed: " + (outcome.get("stderr") or outcome["status"])[-500:])
    manifest = registry.seal_with(root, components=links if component else None)
    if by:
        kernel.ledger(root, {"event": "producer", "model": by})
    return {"ok": kernel.verify(root)["ok"], "root": manifest["root"]}
