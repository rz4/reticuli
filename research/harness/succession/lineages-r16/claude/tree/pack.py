"""pack: a project as a self-claim (`spec/layers.md`).

`pack` seals a working tree in place: the caller declares which files are
`generated` (the regrowable implementation, outside the root) and which
are `inputs` (the acceptance criteria and fixtures, pinned), builds the
recipe and writes it FIRST -- the warm gate runs inside the claim it
certifies, recipe included -- refuses a gate whose every decider is itself
generated before ever running it (the vacuous-gate rule,
`spec/claim-format.md`), then runs the declared gate itself through
`kernel.run_gate` (scrubbed env, sandboxed, bounded; never `kernel.sandbox`
directly, so an inherited secret cannot reach the sealed verdict), and
seals only once that gate earns its own verdict fresh. A declared
`component` layers one sealed claim beneath another, content-addressed:
the dependency travels wholesale into the claim's own store, and the
shipped file's produce step is marked `from` the component it came from --
the write half of the contract `registry.audit_deep`'s reader consumes.
"""
import glob
import os
import shutil

from reticuli import kernel
from reticuli import registry
from reticuli import render


def _guidance_key(fmt: int) -> str:
    return "request" if fmt == 1 else "guidance"


def _expand(root: str, patterns: list) -> list:
    """Every pattern in `patterns`, expanded against files under `root`,
    in pattern order, each pattern's own matches sorted and deduplicated."""
    seen = []
    for pattern in patterns:
        matches = sorted(glob.glob(pattern, root_dir=root, recursive=True))
        for m in matches:
            rel = m.replace(os.sep, "/")
            if rel not in seen:
                seen.append(rel)
    return seen


def pack(root: str, name: str, generated: list, inputs: list, gate: str,
         gate_output: str, *, component: dict = None, claim_format: int = None,
         envelope: dict = None, mutation_floor: float = None,
         requires: list = None, by: str = None, inputs_manifest: str = None,
         environment: str = None) -> dict:
    """Seal `root` as a claim named `name`: `generated` stays outside the
    root, `inputs` and the gate's verdict go in. Runs `gate` itself."""
    fmt = claim_format if claim_format is not None else 3
    guidance_key = _guidance_key(fmt)

    generated_files = _expand(root, generated)
    declared_inputs = _expand(root, inputs)

    if environment is not None and not os.path.isfile(os.path.join(root, environment)):
        raise kernel.ClaimError(
            f"pack refused an environment that names no file: {environment!r}")

    comp_name = component.get("name") if component else None
    comp_outputs = set(component.get("outputs", [])) if component else set()

    steps = []
    for output in generated_files:
        step = {"kind": "produce", "output": output, "class": "generated"}
        if output in comp_outputs:
            step["from"] = comp_name
        else:
            step[guidance_key] = f"regenerate {output} to pass the gate"
        steps.append(step)
    steps.append({"kind": "gate", "output": gate_output,
                  "class": "validated", "run": gate})

    claim_table = {"name": name}
    if fmt != 1:
        claim_table["format"] = fmt

    if inputs_manifest:
        claim_table["inputs_manifest"] = inputs_manifest
    else:
        claim_table["inputs"] = declared_inputs

    if envelope is not None:
        claim_table["envelope"] = envelope
    if mutation_floor is not None:
        claim_table["mutation_floor"] = mutation_floor
    if requires is not None:
        claim_table["requires"] = requires
    if environment is not None:
        claim_table["environment"] = environment

    recipe = {"claim": claim_table, "step": steps}

    vacuous = kernel.vacuous_gates(recipe)
    if vacuous:
        raise kernel.ClaimError(
            f"pack refused vacuous gate(s) whose every decider is generated: {vacuous!r}")

    links = None
    if component is not None:
        comp_dir = component["claim"]
        comp_manifest = kernel.read_manifest(comp_dir)
        dest = os.path.join(root, kernel.STORE, "sealed", comp_name)
        if os.path.isdir(dest):
            shutil.rmtree(dest)
        shutil.copytree(comp_dir, dest)
        links = [{"input": output, "component": comp_name,
                  "output": output, "root": comp_manifest["root"]}
                 for output in sorted(comp_outputs)]

    if inputs_manifest:
        manifest_path = os.path.join(root, inputs_manifest)
        with open(manifest_path, "w", encoding="utf-8") as f:
            for path in declared_inputs:
                digest = kernel._hash_file(os.path.join(root, path))
                f.write(f"{digest}  {path}\n")

    with open(os.path.join(root, kernel.RECIPE), "w", encoding="utf-8") as f:
        f.write(render.dump_recipe(recipe))

    outcome = kernel.run_gate(gate, root, recipe)
    if outcome["status"] != "ok":
        raise kernel.ClaimError(f"pack's gate did not earn its verdict: {outcome!r}")

    manifest = registry.seal_with(root, components=links)

    if by:
        kernel.ledger(root, {"event": "producer", "model": by})

    return {"ok": True, "root": manifest["root"], "name": manifest["name"]}
