"""pack: a project as a self-claim (`spec/claim-format.md`).

The implementation is generated (named by glob, against whatever is on
disk when `pack` runs); the check is the claim (named by explicit
`inputs`, or a manifest of them). `pack` assembles the recipe, refuses a
vacuous gate before touching disk, writes the recipe into the project
*before* running the gate -- a criterion is entitled to find its own
claim in the room it judges -- runs the gate once in place (scrubbed,
sandboxed, bounded, via `kernel.run_gate`, never `kernel.sandbox`
directly), and seals.

Stdlib only.
"""
import glob
import os
import shutil

from . import kernel
from . import render
from . import _util

_GUIDANCE_FMT = "regenerate {output} to pass the gate"


def _format_spec(claim_format):
    """`(format value or None, guidance key)` for the requested era.
    `None` (the default) and any value other than 1 write `format` and
    spell the hint `guidance`; `claim_format=1` writes no `format` key at
    all -- format 1 is the implicit, keyless default -- and spells the
    hint in era 1's own word, `request`."""
    if claim_format is None:
        return 3, "guidance"
    if claim_format == 1:
        return None, "request"
    return claim_format, "guidance"


def _glob_many(root: str, patterns) -> list:
    found = set()
    for pattern in patterns:
        for match in glob.glob(os.path.join(root, pattern), recursive=True):
            if os.path.isfile(match):
                rel = os.path.relpath(match, root).replace(os.sep, "/")
                found.add(rel)
    return sorted(found)


def _manifest_text(root: str, inputs) -> str:
    lines = [
        f"{_util.hash_bytes(_util.safe_path(root, path))}  {path}"
        for path in sorted(inputs)
    ]
    return "\n".join(lines) + ("\n" if lines else "")


def pack(root, name, generated=None, inputs=None, gate=None, gate_output=None, *,
         envelope=None, claim_format=None, mutation_floor=None, requires=None,
         by=None, inputs_manifest=None, environment=None, component=None) -> dict:
    generated = list(generated or [])
    inputs = list(inputs or [])

    if environment is not None:
        env_path = _util.safe_path(root, environment)
        if not os.path.isfile(env_path):
            raise kernel.ClaimError(f"pack: environment names no file: {environment!r}")

    generated_files = _glob_many(root, generated)
    component_outputs = set((component or {}).get("outputs", []))
    fmt, guidance_key = _format_spec(claim_format)

    produce_steps = []
    for path in generated_files:
        step = {"kind": "produce", "output": path, "class": "generated"}
        if component and path in component_outputs:
            step["from"] = component["name"]
        else:
            step[guidance_key] = _GUIDANCE_FMT.format(output=path)
        produce_steps.append(step)

    gate_steps = [{"kind": "gate", "output": gate_output, "class": "validated", "run": gate}]

    claim_table = {"name": name}
    if inputs_manifest:
        claim_table["inputs_manifest"] = inputs_manifest
    else:
        claim_table["inputs"] = sorted(inputs)
    if fmt is not None:
        claim_table["format"] = fmt
    if mutation_floor is not None:
        claim_table["mutation_floor"] = mutation_floor
    if requires is not None:
        claim_table["requires"] = list(requires)
    if envelope is not None:
        claim_table["envelope"] = dict(envelope)
    if environment is not None:
        claim_table["environment"] = environment

    recipe = {"claim": claim_table, "step": produce_steps + gate_steps}

    vacuous = kernel.vacuous_gates(recipe)
    if vacuous:
        raise kernel.ClaimError(
            f"pack refuses a vacuous gate (every decider is generated): {vacuous!r}")

    if inputs_manifest:
        with open(_util.safe_path(root, inputs_manifest), "w", encoding="utf-8") as f:
            f.write(_manifest_text(root, inputs))

    with open(os.path.join(root, kernel.RECIPE), "w", encoding="utf-8") as f:
        f.write(render.dump_recipe(recipe))

    if component:
        comp_dest = os.path.join(root, kernel.STORE, "sealed", component["name"])
        if os.path.isdir(comp_dest):
            shutil.rmtree(comp_dest)
        shutil.copytree(component["claim"], comp_dest)

    result = kernel.run_gate(gate, root, recipe)
    if result["status"] != "ok":
        raise kernel.ClaimError(f"pack: the gate did not pass: {result['status']}")

    manifest = kernel.seal(root)

    if by:
        kernel.ledger(root, {"event": "producer", "model": by})

    return {"ok": True, "root": manifest["root"], "name": manifest["name"]}
