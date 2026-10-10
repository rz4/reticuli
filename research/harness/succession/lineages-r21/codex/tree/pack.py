"""Turn an existing project and its acceptance check into a claim."""

import glob
import os
import shutil

from . import kernel, registry, render
from ._util import safe_path


def _expand(directory, patterns):
    names = []
    for pattern in patterns or []:
        safe_path(directory, pattern)
        for path in sorted(glob.glob(os.path.join(directory, pattern), recursive=True)):
            if os.path.isfile(path):
                name = os.path.relpath(path, directory).replace(os.sep, "/")
                safe_path(directory, name)
                if name not in names:
                    names.append(name)
    return names


def pack(root, name, generated, inputs, gate, gate_output, *,
         envelope=None, claim_format=3, component=None, mutation_floor=None,
         requires=None, by=None, inputs_manifest=None, environment=None):
    root = os.path.realpath(root)
    made = _expand(root, generated)
    pinned = _expand(root, inputs)
    if set(made) & set(pinned):
        raise kernel.ClaimError("generated files overlap claimed inputs")
    safe_path(root, gate_output)
    if environment is not None:
        if not os.path.isfile(safe_path(root, environment)):
            raise kernel.ClaimError(f"environment names no file: {environment}")
    if claim_format not in (1, 2, 3, 4):
        raise kernel.ClaimError("unsupported claim format")
    claim = {"name": name}
    if claim_format != 1:
        claim["format"] = claim_format
    if inputs_manifest:
        if claim_format < 2:
            raise kernel.ClaimError("inputs_manifest requires format 2 or newer")
        safe_path(root, inputs_manifest)
        with open(safe_path(root, inputs_manifest), "w", encoding="utf-8") as stream:
            for path in pinned:
                stream.write(f"{kernel._hash_file(safe_path(root, path))}  {path}\n")
        claim["inputs_manifest"] = inputs_manifest
    else:
        claim["inputs"] = pinned
    for key, value in (("envelope", envelope), ("mutation_floor", mutation_floor),
                       ("requires", requires), ("environment", environment)):
        if value is not None:
            claim[key] = value
    supplied = set()
    links = []
    if component:
        source = component["claim"]
        verified = kernel.verify(source)
        if not verified["ok"]:
            raise kernel.ClaimError("component identity does not hold")
        cname = component["name"]
        for path in component["outputs"]:
            if path not in made:
                raise kernel.ClaimError(f"component output not generated: {path}")
            supplied.add(path)
            links.append({"input": path, "component": cname,
                          "root": verified["root"], "output": path})
        dest = os.path.join(root, kernel.STORE, "sealed", cname)
        if os.path.exists(dest):
            shutil.rmtree(dest)
        registry._copy_claim(source, dest)
    guidance_key = "request" if claim_format == 1 else "guidance"
    steps = []
    for path in made:
        step = {"kind": "produce", "output": path, "class": "generated"}
        if path in supplied:
            step["from"] = component["name"]
        else:
            step[guidance_key] = f"regenerate {path} to pass the gate"
        steps.append(step)
    steps.append({"kind": "gate", "output": gate_output, "class": "validated", "run": gate})
    parsed = {"claim": claim, "step": steps}
    if kernel.vacuous_gates(parsed):
        raise kernel.ClaimError("vacuous gate: every decider is generated")
    with open(os.path.join(root, kernel.RECIPE), "w", encoding="utf-8") as stream:
        stream.write(render.dump_recipe(parsed))
    result = kernel.run_gate(gate, root, parsed)
    if result["status"] != "ok":
        raise kernel.ClaimError(f"gate failed: {result.get('stderr', '')}")
    if not os.path.isfile(safe_path(root, gate_output)):
        raise kernel.ClaimError(f"gate produced no verdict: {gate_output}")
    manifest = registry.seal_with(root, components=links) if links else kernel.seal(root)
    if by:
        kernel.ledger(root, {"event": "producer", "model": by,
                             "producer": {"model": by}})
    return {"ok": True, "root": manifest["root"], "name": name}
