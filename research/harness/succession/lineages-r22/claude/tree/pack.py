"""Pack: a project directory becomes a self-claim -- the implementation is
generated, the check is the claim.

`pack` turns `generated`/`inputs` pattern lists (each may expand to zero
files -- an empty match is an empty set, not a refusal) into a recipe,
refuses a vacuous gate before touching disk, writes the recipe, runs the
gate once through `kernel.run_gate` (never `kernel.sandbox` directly, so
every run is scrubbed and sandboxed the one way the format allows), and
seals. A `component` layers this claim on another: the named outputs are
declared `from` the component, its claim travels into this claim's own
store (`.reticuli/sealed/<name>`), and the link lands on the manifest so
`registry.audit_deep` can re-earn the whole chain. The authoring default
is format 3 (guidance is not identity); `claim_format=1` writes the
keyless era-1 recipe, spelling its hint `request` rather than `guidance`,
so every claim already sealed under that era keeps minting its root.
"""
import glob
import os
import shutil

from . import kernel
from . import registry
from . import render


def _expand_one(root: str, pattern: str) -> list:
    matches = glob.glob(os.path.join(root, pattern))
    rels = sorted(os.path.relpath(m, root).replace(os.sep, "/")
                  for m in matches if os.path.isfile(m))
    return rels


def _expand(root: str, patterns) -> list:
    """Every pattern's own matches, sorted, concatenated in the patterns'
    own order and deduplicated -- a pattern that matches nothing
    contributes nothing, never a refusal (an empty set is a set)."""
    out, seen = [], set()
    for pat in patterns:
        for m in _expand_one(root, pat):
            if m not in seen:
                seen.add(m)
                out.append(m)
    return out


def pack(root: str, name: str, generated, inputs, gate: str, gate_output: str,
          *, component=None, envelope=None, claim_format=None,
          mutation_floor=None, requires=None, by=None,
          inputs_manifest=None, environment=None) -> dict:
    """Seal `root` as a claim named `name`: `generated`/`inputs` are
    pattern lists expanded against `root`'s own files; `gate` is the
    command that earns `gate_output`. See the module docstring for the
    keyword surface (`component`, `envelope`, `claim_format`,
    `mutation_floor`, `requires`, `by`, `inputs_manifest`,
    `environment`)."""
    gen_list = _expand(root, generated)
    in_list = _expand(root, inputs)

    fmt = claim_format if claim_format is not None else 3
    hint_key = "request" if fmt == 1 else "guidance"

    claim = {"name": name}
    if fmt != 1:
        claim["format"] = fmt
    if envelope is not None:
        claim["envelope"] = envelope
    if mutation_floor is not None:
        claim["mutation_floor"] = mutation_floor
    if requires is not None:
        claim["requires"] = requires
    if environment is not None:
        claim["environment"] = environment

    comp_name = (component or {}).get("name")
    comp_outputs = set((component or {}).get("outputs") or [])

    steps = []
    for g in gen_list:
        step = {"kind": "produce", "output": g, "class": "generated"}
        if comp_name and g in comp_outputs:
            step["from"] = comp_name
        else:
            step[hint_key] = f"regenerate {g} to pass the gate"
        steps.append(step)
    steps.append({"kind": "gate", "output": gate_output, "class": "validated", "run": gate})

    manifest_lines = None
    if inputs_manifest:
        manifest_lines = [f"{kernel._hash_file(os.path.join(root, p))}  {p}" for p in in_list]
        claim["inputs_manifest"] = inputs_manifest
    else:
        claim["inputs"] = in_list

    recipe = {"claim": claim, "step": steps}

    vacuous = kernel.vacuous_gates(recipe)
    if vacuous:
        raise kernel.ClaimError(
            f"pack refuses a vacuous gate (every decider is generated): {vacuous}")

    if manifest_lines is not None:
        with open(os.path.join(root, inputs_manifest), "w", encoding="utf-8") as f:
            f.write("\n".join(manifest_lines) + ("\n" if manifest_lines else ""))

    with open(os.path.join(root, kernel.RECIPE), "w", encoding="utf-8") as f:
        f.write(render.dump_recipe(recipe))

    gate_path = os.path.join(root, gate_output)
    if os.path.isfile(gate_path):
        os.remove(gate_path)
    result = kernel.run_gate(gate, root, recipe)
    if result["status"] != "ok" or not os.path.isfile(gate_path):
        raise kernel.ClaimError(f"pack: gate did not earn {gate_output!r}: {result}")

    if component is not None:
        comp_claim_dir = component["claim"]
        comp_manifest = kernel.read_manifest(comp_claim_dir)
        dest = os.path.join(root, kernel.STORE, "sealed", comp_name)
        if not os.path.isdir(dest):
            shutil.copytree(comp_claim_dir, dest)
        links = [
            {"input": o, "component": comp_name, "root": comp_manifest["root"], "output": o}
            for o in sorted(comp_outputs)
        ]
        manifest = registry.seal_with(root, components=links)
    else:
        manifest = kernel.seal(root)

    if by:
        kernel.ledger(root, {"event": "producer", "model": by})

    return {"ok": True, "root": manifest["root"], "name": manifest["name"]}
