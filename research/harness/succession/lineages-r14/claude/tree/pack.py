"""pack: a project as a self-claim (spec/layers.md).

No session trace is involved here -- every path is declared by the caller,
not inferred: `generated` and `inputs` are a symmetric pair of glob
patterns naming the implementation and the criterion. The implementation
is generated (outside identity, regrowable); the check is the claim. A
gate whose every decider is generated is refused as vacuous, same as the
trace-driven path in `authoring.py`. The gate runs once, warm, through
`kernel.run_gate` alone -- scrubbed, sandboxed, bounded -- after the recipe
is written to disk, so a check that looks for its own claim finds one.
"""
import glob
import os
import shutil

from reticuli import kernel, _util, registry, render

_DEFAULT_FORMAT = 3


def _expand(root_dir: str, patterns) -> list:
    found = set()
    for pat in patterns or ():
        for m in glob.glob(pat, root_dir=root_dir):
            found.add(m.replace(os.sep, "/"))
    return sorted(found)


def _guidance_key(claim_format: int) -> str:
    return "request" if claim_format == 1 else "guidance"


def _write_manifest(root_dir: str, rel_name: str, paths: list) -> None:
    full = _util.safe_path(root_dir, rel_name)
    os.makedirs(os.path.dirname(full) or root_dir, exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        for p in paths:
            digest = _util.hash_bytes(_util.safe_path(root_dir, p))
            f.write(f"{digest}  {p}\n")


def pack(root_dir: str, name: str, generated=(), inputs=(), gate: str = None,
         gate_output: str = None, *, component: dict = None,
         mutation_floor: float = None, requires: list = None, by: str = None,
         inputs_manifest: str = None, envelope: dict = None,
         environment: str = None, claim_format: int = _DEFAULT_FORMAT) -> dict:
    """Seal `root_dir` as a self-claim: `generated`/`inputs` are glob
    patterns, `gate` is the verdict command, `gate_output` its pinned
    output."""
    generated_files = _expand(root_dir, generated)
    input_files = _expand(root_dir, inputs)

    comp_name = (component or {}).get("name")
    component_outputs = set((component or {}).get("outputs") or ())

    key = _guidance_key(claim_format)
    steps = []
    for path in generated_files:
        step = {"kind": "produce", "output": path, "class": "generated"}
        if path in component_outputs:
            step["from"] = comp_name
        else:
            step[key] = f"regenerate {path} to pass the gate"
        steps.append(step)
    steps.append({"kind": "gate", "output": gate_output, "class": "validated", "run": gate})

    claim_table = {"name": name}
    if claim_format != 1:
        claim_table["format"] = claim_format
    if requires:
        claim_table["requires"] = list(requires)
    if mutation_floor is not None:
        claim_table["mutation_floor"] = float(mutation_floor)
    if envelope:
        claim_table["envelope"] = dict(envelope)
    if environment:
        claim_table["environment"] = environment
    if inputs_manifest:
        claim_table["inputs_manifest"] = inputs_manifest
    else:
        claim_table["inputs"] = input_files

    recipe = {"claim": claim_table, "step": steps}

    vacuous = kernel.vacuous_gates(recipe)
    if gate_output in vacuous:
        raise kernel.ClaimError(
            f"pack refuses a vacuous gate (every decider is generated): {gate_output!r}")

    if component:
        comp_dest = os.path.join(root_dir, kernel.STORE, "sealed", comp_name)
        if not os.path.isdir(comp_dest):
            os.makedirs(os.path.dirname(comp_dest), exist_ok=True)
            shutil.copytree(component["claim"], comp_dest)

    if inputs_manifest:
        _write_manifest(root_dir, inputs_manifest, input_files)

    recipe_path = os.path.join(root_dir, kernel.RECIPE)
    with open(recipe_path, "w", encoding="utf-8") as f:
        f.write(render.dump_recipe(recipe))

    res = kernel.run_gate(gate, root_dir, recipe)
    if res["status"] != "ok":
        raise kernel.ClaimError(f"pack's gate did not earn: {res['status']}")

    if by:
        _util.ledger_add(root_dir, {"event": "producer", "model": by})

    components = None
    if component:
        comp_root = kernel.read_manifest(component["claim"])["root"]
        components = [{"component": comp_name, "root": comp_root}]

    manifest = registry.seal_with(root_dir, components=components)
    return {"ok": True, "root": manifest["root"], "name": manifest["name"]}
