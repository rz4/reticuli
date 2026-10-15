"""A project as a self-claim: the implementation is generated, the check
is the claim.

`pack` turns an ordinary project directory into a sealed claim in place:
`generated`/`inputs` are pattern lists (a literal filename is a pattern
that matches itself; a pattern may legally match zero files -- an empty
selection is a set like any other), expanded against the project tree,
confined to it, and written into a recipe alongside one gate step. The
gate runs exactly once, through `kernel.run_gate` -- never `kernel.sandbox`
directly, which would bypass the declared bound -- and only after the
recipe is on disk, so a gate that checks it is running inside a claim
finds one. A gate whose every decider is itself generated is refused as
vacuous before any of this touches disk.

`component=` layers this claim on another: the named outputs are declared
`from` that component (carried, not independently generated here), and the
component's own recipe, pinned inputs, and present step outputs -- never
its own store -- travel into this claim's `.reticuli/sealed/<name>`, so the
copy is the size of the component itself, not of everything beneath it;
that bound is what keeps a chain of components an incremental build rather
than an unfolding one.

Stdlib only.
"""
import glob
import os
import shutil

from reticuli import kernel, registry, render
from . import _util


# -- expanding declared patterns -----------------------------------------------


def _expand(root: str, patterns: list) -> list:
    """Every pattern, expanded against `root`, in pattern order -- a
    pattern may legally match nothing."""
    out = []
    for pat in patterns:
        out.extend(sorted(glob.glob(pat, root_dir=root)))
    return out


# -- copying a component into this claim's own store ---------------------------


def _copy_component(comp_dir: str, dest: str) -> None:
    """Copy a component's declared content -- recipe, pinned inputs, and
    every present step output -- into `dest`. Never the component's own
    store: copying that would walk its whole ancestry, turning an
    incremental chain build into an unfolding one."""
    os.makedirs(dest, exist_ok=True)
    parsed = kernel.load_recipe(comp_dir)
    recipe_name = _util.recipe_filename(comp_dir)
    shutil.copy2(os.path.join(comp_dir, recipe_name), os.path.join(dest, recipe_name))
    for p in _util.declared_inputs(comp_dir, parsed):
        s = _util.safe_path(comp_dir, p)
        t = os.path.join(dest, p)
        os.makedirs(os.path.dirname(t) or dest, exist_ok=True)
        shutil.copy2(s, t)
    for step in parsed.get("step", []):
        out = step.get("output")
        if not out:
            continue
        full = os.path.join(comp_dir, out)
        if os.path.isfile(full):
            t = os.path.join(dest, out)
            os.makedirs(os.path.dirname(t) or dest, exist_ok=True)
            shutil.copy2(full, t)
    manifest_src = os.path.join(comp_dir, kernel.MANIFEST)
    if os.path.isfile(manifest_src):
        os.makedirs(os.path.join(dest, kernel.STORE), exist_ok=True)
        shutil.copy2(manifest_src, os.path.join(dest, kernel.MANIFEST))


# -- pack -----------------------------------------------------------------------


def pack(root: str, name: str, generated: list, inputs: list, gate: str, gate_output: str, *,
         component: dict = None, claim_format: int = None, envelope: dict = None,
         mutation_floor: float = None, requires: list = None, by: str = None,
         inputs_manifest: str = None, environment: str = None) -> dict:
    """Turn `root` into a sealed claim in place."""
    gen_paths = _expand(root, generated)
    in_paths = _expand(root, inputs)

    confine = list(gen_paths) + list(in_paths)
    if inputs_manifest is not None:
        confine.append(inputs_manifest)
    if environment is not None:
        confine.append(environment)
    for p in confine:
        _util.safe_path(root, p)

    if environment is not None and not os.path.isfile(os.path.join(root, environment)):
        raise kernel.ClaimError(f"pack: environment file not found: {environment!r}")

    fmt = 3 if claim_format is None else claim_format
    guidance_key = "guidance" if fmt >= 3 else "request"

    comp_root = None
    carried = set()
    if component is not None:
        comp_root = kernel.read_manifest(component["claim"])["root"]
        carried = set(component.get("outputs", []))

    produce_steps = []
    for p in gen_paths:
        step = {"kind": "produce", "output": p, "class": "generated"}
        if p in carried:
            step["from"] = component["name"]
        else:
            step[guidance_key] = f"regenerate {p} to pass the gate"
        produce_steps.append(step)

    generated_set = set(gen_paths)
    deciders = kernel.gate_deciders(gate)
    if deciders and all(d in generated_set for d in deciders):
        raise kernel.ClaimError(
            f"pack: gate {gate_output!r} is vacuous -- every decider is generated: {deciders}")

    claim_table = {"name": name}
    if fmt != 1:
        claim_table["format"] = fmt
    if inputs_manifest is not None:
        claim_table["inputs_manifest"] = inputs_manifest
    else:
        claim_table["inputs"] = in_paths
    if envelope is not None:
        claim_table["envelope"] = envelope
    if mutation_floor is not None:
        claim_table["mutation_floor"] = mutation_floor
    if requires is not None:
        claim_table["requires"] = requires
    if environment is not None:
        claim_table["environment"] = environment

    gate_step = {"kind": "gate", "output": gate_output, "run": gate, "class": "validated"}
    recipe = {"claim": claim_table, "step": produce_steps + [gate_step]}

    # the recipe precedes the warm gate: a gate may ask what claim it is in
    recipe_path = os.path.join(root, kernel.RECIPE)
    with open(recipe_path, "w", encoding="utf-8") as f:
        f.write(render.dump_recipe(recipe))

    if inputs_manifest is not None:
        manifest_path = _util.safe_path(root, inputs_manifest)
        lines = [f"{kernel._hash_file(_util.safe_path(root, p))}  {p}" for p in in_paths]
        with open(manifest_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + ("\n" if lines else ""))

    parsed = kernel.load_recipe(root)
    outcome = kernel.run_gate(gate, root, parsed)
    if outcome["status"] != "ok":
        raise kernel.ClaimError(f"pack: gate {gate_output!r} did not pass: {outcome['status']}")

    if by is not None:
        kernel.ledger(root, {"event": "producer", "model": by})

    if component is not None:
        _copy_component(component["claim"],
                         os.path.join(root, kernel.STORE, "sealed", component["name"]))
        links = [{"input": out, "component": component["name"], "root": comp_root, "output": out}
                 for out in component.get("outputs", [])]
        manifest = registry.seal_with(root, components=links)
    else:
        manifest = kernel.seal(root)

    return {"ok": True, "root": manifest["root"], "name": manifest["name"]}
