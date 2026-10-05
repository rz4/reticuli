"""Turn a project into a claim whose implementation can be regrown."""

import glob
import os
import shutil

from . import kernel, render
from ._util import safe_path, copy_into


def _expand(directory, patterns):
    found = set()
    for pattern in patterns or []:
        safe_path(directory, pattern) if not glob.has_magic(pattern) else None
        for path in glob.glob(os.path.join(directory, pattern), recursive=True):
            if os.path.isfile(path):
                name = os.path.relpath(path, directory).replace(os.sep, "/")
                safe_path(directory, name)
                found.add(name)
    return sorted(found)


def pack(root, name, generated, inputs, gate, gate_output,
         *, envelope=None, claim_format=3, component=None,
         mutation_floor=None, requires=None, by=None,
         inputs_manifest=None, environment=None):
    root = os.path.abspath(root)
    produced = _expand(root, generated)
    pinned = _expand(root, inputs)
    if environment is not None:
        env_path = safe_path(root, environment)
        if not os.path.isfile(env_path):
            raise kernel.ClaimError("missing declared environment: " + environment)
        if environment not in pinned:
            pinned.append(environment)
    if set(produced) & set(pinned):
        raise kernel.ClaimError("a file cannot be generated and claimed")
    safe_path(root, gate_output)
    if inputs_manifest:
        safe_path(root, inputs_manifest)
        with open(os.path.join(root, inputs_manifest), "w", encoding="utf-8") as stream:
            for path in sorted(pinned):
                stream.write(kernel._hash_file(safe_path(root, path)) + "  " + path + "\n")
    claim = {"name": name}
    if claim_format != 1:
        claim["format"] = claim_format
    if inputs_manifest:
        claim["inputs_manifest"] = inputs_manifest
    else:
        claim["inputs"] = sorted(pinned)
    for key, value in (("envelope", envelope), ("mutation_floor", mutation_floor),
                       ("requires", requires), ("environment", environment)):
        if value is not None:
            claim[key] = value
    supplied = set()
    links = []
    if component:
        cname, source = component["name"], component["claim"]
        verified = kernel.verify(source)
        if not verified["ok"]:
            raise kernel.ClaimError("component identity mismatch")
        for output in component["outputs"]:
            safe_path(root, output)
            supplied.add(output)
            links.append({"component": cname, "root": verified["root"], "output": output})
        dest = os.path.join(root, kernel.STORE, "sealed", cname)
        if os.path.isdir(dest):
            shutil.rmtree(dest)
        shutil.copytree(source, dest)
    hint = "guidance" if claim_format >= 3 else "request"
    steps = []
    for output in produced:
        row = {"kind": "produce", "output": output, "class": "generated",
               hint: f"regenerate {output} to pass the gate"}
        if output in supplied:
            row["from"] = component["name"]
        steps.append(row)
    steps.append({"kind": "gate", "output": gate_output,
                  "class": "validated", "run": gate})
    parsed = {"claim": claim, "step": steps}
    if kernel.vacuous_gates(parsed):
        raise kernel.ClaimError("vacuous gate: every decider is generated")
    recipe_path = os.path.join(root, kernel.RECIPE)
    with open(recipe_path, "w", encoding="utf-8") as stream:
        stream.write(render.dump_recipe(parsed))
    verdict = safe_path(root, gate_output)
    if os.path.isfile(verdict):
        os.unlink(verdict)
    result = kernel.run_gate(gate, root, parsed)
    if result["status"] != "ok" or not os.path.isfile(verdict):
        raise kernel.ClaimError("gate did not produce its verdict: " + str(result))
    sealed = kernel.seal(root)
    if links:
        sealed["components"] = links
        from ._util import write_json
        write_json(os.path.join(root, kernel.MANIFEST), sealed)
    if by:
        kernel.ledger(root, {"event": "producer", "model": by, "blind": False})
    return {"ok": True, "root": sealed["root"], "path": root}
