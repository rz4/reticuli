"""reticuli.pack -- a project as a self-claim: implementation generated,
check claimed (`spec/layers.md`).

Unlike `authoring.build_claim`, there is no trace and no inference: the
caller declares the boundary directly -- which files are the regrowable
implementation (`generated`, glob patterns), which are the claim itself
(`inputs`, glob patterns), and what gate decides. `pack` refuses a gate
whose every decider is generated (vacuous -- the same boundary rule
`authoring` enforces), then runs the gate once, in place, through
`kernel.run_gate` -- scrubbed, sandboxed, bounded, never `kernel.sandbox`
directly -- and seals.
"""
import glob
import os

from . import kernel
from . import render


def _match(root: str, patterns) -> list:
    found = set()
    for pattern in patterns:
        for path in glob.glob(os.path.join(root, pattern), recursive=True):
            if os.path.isfile(path):
                found.add(os.path.relpath(path, root))
    return sorted(found)


def pack(root: str, name: str, generated_patterns, input_patterns, run: str, output: str) -> dict:
    generated_files = _match(root, generated_patterns)
    input_files = _match(root, input_patterns)

    recipe = {
        "claim": {"name": name, "inputs": input_files},
        "step": [
            *[{"kind": "produce", "output": f, "class": "generated"} for f in generated_files],
            {"kind": "gate", "output": output, "class": "validated", "run": run},
        ],
    }

    vacuous = set(kernel.vacuous_gates(recipe))
    if output in vacuous:
        raise kernel.ClaimError(
            f"gate {output!r} is vacuous: every decider is generated, unclaimed bytes -- "
            "the claim boundary is declared, not inferred from what got written")

    result = kernel.run_gate(run, root, recipe)
    if result["status"] != "ok":
        raise kernel.ClaimError(f"gate {output!r} did not pass: {result['status']}")

    recipe_path = os.path.join(root, kernel.RECIPE)
    with open(recipe_path, "w", encoding="utf-8") as f:
        f.write(render.dump_recipe(recipe))

    manifest = kernel.seal(root)
    return {"ok": True, **manifest}
