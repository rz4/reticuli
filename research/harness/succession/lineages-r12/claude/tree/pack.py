"""pack: a project as a self-claim (`spec/layers.md`'s authoring layer).

Seals an existing project directory in place: the implementation travels
as `generated` (regrowable, outside identity) and the acceptance check
the project ships travels as a pinned `input` -- the check IS the claim,
never inferred from which files a hook happened to see written.
`generated`/`inputs` are glob-pattern lists, expanded into the concrete
files they name before anything is pinned, so a pattern that matches
nothing is never hashed literally. A gate whose every decider is itself
generated is refused as vacuous. Runs its gate only through
`kernel.run_gate`, never `kernel.sandbox` directly, so an inherited
secret cannot reach a sealed verdict.

Stdlib only.
"""
import glob
import os
import re

from . import _util
from . import kernel
from . import registry
from . import render

_WILDCARD = re.compile(r"[*?\[]")


def _expand(root: str, patterns: list) -> list:
    """Glob patterns, expanded into the concrete paths they name
    (relative to `root`); a pattern with no wildcard character is kept
    literal, matched on disk or not -- the one road a not-yet-written
    generated file can travel."""
    out = []
    for pat in patterns:
        if _WILDCARD.search(pat):
            matches = sorted(
                os.path.relpath(m, root).replace(os.sep, "/")
                for m in glob.glob(os.path.join(root, pat))
            )
            out.extend(matches)
        else:
            out.append(pat)
    return out


def _write_manifest(root: str, manifest_name: str, paths: list) -> None:
    lines = [f"{_util.hash_bytes(os.path.join(root, p))}  {p}" for p in paths]
    with open(os.path.join(root, manifest_name), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + ("\n" if lines else ""))


def pack(root: str, name: str, generated: list = None, inputs: list = None,
         gate: str = None, gate_output: str = None, *, component: dict = None,
         envelope: dict = None, claim_format: int = None,
         mutation_floor: float = None, requires: list = None,
         by: str = None, inputs_manifest: str = None,
         environment: str = None) -> dict:
    """Seal `root` as a claim named `name`.

    `generated`/`inputs` are glob-pattern lists naming the implementation
    and the acceptance check; `gate`/`gate_output` are the verdict
    command and the file it pins. `component` layers one claim on
    another: `{"name", "claim", "outputs"}` marks the named generated
    outputs as carried `from` that component, and vendors its claim
    under this one's own store. The rest follow `spec/claim-format.md`.
    """
    root = os.path.abspath(root)
    generated_paths = sorted(_expand(root, generated or []))
    input_paths = _expand(root, inputs or [])

    effective_format = 3 if claim_format is None else claim_format
    guidance_key = "request" if effective_format == 1 else "guidance"

    comp_name = (component or {}).get("name")
    comp_outputs = set((component or {}).get("outputs") or [])

    produce_steps = []
    for p in generated_paths:
        step = {"kind": "produce", "output": p, "class": "generated",
                guidance_key: f"regenerate {p} to pass the gate"}
        if comp_name and p in comp_outputs:
            step["from"] = comp_name
        produce_steps.append(step)

    gate_steps = [{"kind": "gate", "output": gate_output, "class": "validated",
                   "run": gate}]

    claim = {"name": name}
    if claim_format != 1:
        claim["format"] = effective_format
    if inputs_manifest:
        claim["inputs_manifest"] = inputs_manifest
    else:
        claim["inputs"] = input_paths
    if envelope is not None:
        claim["envelope"] = envelope
    if mutation_floor is not None:
        claim["mutation_floor"] = mutation_floor
    if requires is not None:
        claim["requires"] = requires
    if environment is not None:
        claim["environment"] = environment

    recipe = {"claim": claim, "step": produce_steps + gate_steps}

    vacuous = set(kernel.vacuous_gates(recipe))
    if gate_output in vacuous:
        raise kernel.ClaimError(
            f"refused: vacuous gate, every decider is generated: {gate_output!r}")

    if inputs_manifest:
        _write_manifest(root, inputs_manifest, input_paths)

    with open(os.path.join(root, kernel.RECIPE), "w", encoding="utf-8") as f:
        f.write(render.dump_recipe(recipe))

    result = kernel.run_gate(gate, root, recipe)
    if result["status"] != "ok":
        raise kernel.ClaimError(
            f"refused: pack's gate did not pass: {gate_output!r} ({result['status']})")

    links = None
    if comp_name:
        comp_dir = os.path.abspath(component["claim"])
        comp_root = kernel.read_manifest(comp_dir)["root"]
        links = [{"input": p, "component": comp_name, "root": comp_root, "output": p}
                 for p in generated_paths if p in comp_outputs]
        dest = os.path.join(root, kernel.STORE, "sealed", comp_name)
        if not os.path.isdir(dest):
            _util.copy_into(comp_dir, dest)

    manifest = registry.seal_with(root, components=links)

    if by:
        kernel.ledger(root, {"event": "producer", "when": _util.stamp(), "model": by})

    return {"ok": True, "root": manifest["root"], "name": manifest["name"]}
