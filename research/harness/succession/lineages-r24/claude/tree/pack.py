"""pack: a project as a self-claim (spec/layers.md "authoring").

A project directory becomes a claim in place: `generated`/`inputs` are
pattern lists (a pattern may legitimately select the empty set) expanded
against the files present, the recipe is written to the project BEFORE the
gate ever runs (a gate may itself check that it is running inside the claim
it certifies), and the gate runs once through `kernel.run_gate` -- never
`kernel.sandbox` directly. A vacuous gate (every decider itself generated)
is refused before any of that. `component=` layers one claim on another: the
named outputs are declared `from` the component in the recipe, the
component travels into the claim's own store (a symlink -- the chain stays
O(1) per layer, never a recursive copy of ancestry already present), and
the link survives a reseal as `registry` residue so `registry.audit_deep`
can walk it.
"""
import glob
import os

from reticuli import kernel, registry, render


def _expand(d: str, patterns: list) -> list:
    """Each pattern, expanded against files present under `d`, in pattern
    order; a pattern may match zero files (contributes nothing, refuses
    nothing) -- the empty-selection rule."""
    seen = set()
    out = []
    for pattern in patterns:
        for match in sorted(glob.glob(os.path.join(d, pattern))):
            if not os.path.isfile(match):
                continue
            rel = os.path.relpath(match, d).replace(os.sep, "/")
            if rel not in seen:
                seen.add(rel)
                out.append(rel)
    return out


def _write_manifest(d: str, filename: str, inputs: list) -> None:
    lines = []
    for p in inputs:
        digest = kernel._hash_file(os.path.join(d, p))
        lines.append(f"{digest}  {p}")
    text = "\n".join(lines)
    if text:
        text += "\n"
    with open(os.path.join(d, filename), "w", encoding="utf-8") as f:
        f.write(text)


def pack(root: str, name: str, generated: list, inputs: list, gate: str,
          gate_output: str = None, *, component: dict = None,
          claim_format: int = None, envelope: dict = None,
          mutation_floor: float = None, requires: list = None,
          by: str = None, inputs_manifest: str = None,
          environment: str = None) -> dict:
    """Seal `root` in place: the implementation is generated, the check
    (declared by `inputs`/`gate`) is the claim."""
    if not gate_output:
        raise kernel.ClaimError("refused: pack requires gate_output")

    effective_format = claim_format if claim_format is not None else 3
    guidance_key = "request" if effective_format < 3 else "guidance"

    generated_list = _expand(root, generated)
    inputs_list = _expand(root, inputs)
    comp_outputs = set(component["outputs"]) if component else set()

    steps = []
    for g in generated_list:
        step = {"kind": "produce", "output": g, "class": "generated"}
        if component and g in comp_outputs:
            step["from"] = component["name"]
        else:
            step[guidance_key] = f"regenerate {g} to pass the gate"
        steps.append(step)
    steps.append({"kind": "gate", "output": gate_output, "class": "validated", "run": gate})

    claim_table = {"name": name, "inputs": inputs_list}
    if claim_format is None or claim_format != 1:
        claim_table["format"] = effective_format
    if envelope is not None:
        claim_table["envelope"] = envelope
    if mutation_floor is not None:
        claim_table["mutation_floor"] = mutation_floor
    if requires is not None:
        claim_table["requires"] = requires
    if inputs_manifest is not None:
        claim_table["inputs_manifest"] = inputs_manifest
    if environment is not None:
        claim_table["environment"] = environment

    parsed = {"claim": claim_table, "step": steps}

    vacuous = kernel.vacuous_gates(parsed)
    if gate_output in vacuous:
        raise kernel.ClaimError(
            f"refused: gate {gate_output!r} is vacuous (every decider is generated); "
            "claim the deciding file or declare it generated explicitly")

    with open(os.path.join(root, kernel.RECIPE), "w", encoding="utf-8") as f:
        f.write(render.dump_recipe(parsed))

    if inputs_manifest is not None:
        _write_manifest(root, inputs_manifest, inputs_list)

    res = kernel.run_gate(gate, root, recipe=parsed)
    if res["status"] != "ok":
        raise kernel.ClaimError(f"refused: pack's gate did not pass: {res['status']}")

    if by:
        kernel.ledger(root, {"event": "producer", "model": by})

    components_list = None
    if component:
        comp_manifest = kernel.read_manifest(component["claim"])
        components_list = [
            {"component": component["name"], "root": comp_manifest["root"],
             "input": o, "output": o}
            for o in component["outputs"]
        ]
        store_dir = os.path.join(root, kernel.STORE, "sealed")
        os.makedirs(store_dir, exist_ok=True)
        link_path = os.path.join(store_dir, component["name"])
        if not os.path.exists(link_path):
            os.symlink(component["claim"], link_path)

    manifest = registry.seal_with(root, components=components_list)
    return {"ok": True, "root": manifest["root"], "name": manifest["name"]}
