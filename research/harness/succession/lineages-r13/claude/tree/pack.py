"""Pack: a project as a self-claim -- the implementation is generated, the
check is the claim (spec/layers.md's authoring layer).

`pack` turns an existing project directory into a claim IN PLACE: declared
`generated`/`inputs` patterns are expanded against the real files present,
a vacuous gate (every decider generated) is refused before anything is
written, the recipe is written FIRST -- so a gate that itself inspects the
claim it runs inside (`os.path.isfile('reticuli.toml')`) finds it -- and
only then does the gate run, through `kernel.run_gate` (scrubbed,
sandboxed, bounded), never `kernel.sandbox` directly. A declared
`component` names an output supplied by another claim (`from`); its own
sealed claim travels into this one's store.
"""
import glob
import os
import shutil

from . import kernel
from . import render


def _is_pattern(p: str) -> bool:
    return any(c in p for c in "*?[")


def _expand(d: str, patterns: list) -> list:
    out, seen = [], set()
    for pat in patterns or []:
        matches = sorted(glob.glob(pat, root_dir=d)) if _is_pattern(pat) else [pat]
        for m in matches:
            m = m.replace(os.sep, "/")
            if m not in seen:
                seen.add(m)
                out.append(m)
    return out


def _write_manifest(d: str, manifest_name: str, paths: list) -> None:
    lines = [f"{kernel._hash_file(os.path.join(d, p))}  {p}" for p in paths]
    with open(os.path.join(d, manifest_name), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + ("\n" if lines else ""))


def pack(d: str, name: str, generated: list, inputs: list, gate: str, gate_output: str, *,
          envelope: dict = None, claim_format: int = None, component: dict = None,
          mutation_floor: float = None, requires: list = None, by: str = None,
          inputs_manifest: str = None, environment: str = None,
          gate_timeout: float = None) -> dict:
    """Seal `d` as a claim: `generated`/`inputs` are pattern lists expanded
    against `d`'s real files, `gate`/`gate_output` the one gate step. A
    refusal (vacuous gate, missing environment file) leaves `d` untouched."""
    generated_paths = _expand(d, generated)
    input_paths = _expand(d, inputs)

    fmt = claim_format if claim_format is not None else 3
    guidance_key = "guidance" if fmt >= 3 else "request"

    comp_name = (component or {}).get("name")
    comp_outputs = set((component or {}).get("outputs", []))

    steps = []
    for p in generated_paths:
        step = {"kind": "produce", "output": p, "class": "generated"}
        if p in comp_outputs:
            step["from"] = comp_name
        else:
            step[guidance_key] = f"regenerate {p} to pass the gate"
        steps.append(step)
    steps.append({"kind": "gate", "output": gate_output, "class": "validated", "run": gate})

    claim_tbl = {"name": name}
    if fmt != 1:
        claim_tbl["format"] = fmt
    if inputs_manifest:
        claim_tbl["inputs_manifest"] = inputs_manifest
    else:
        claim_tbl["inputs"] = input_paths
    if envelope is not None:
        claim_tbl["envelope"] = envelope
    if mutation_floor is not None:
        claim_tbl["mutation_floor"] = mutation_floor
    if requires is not None:
        claim_tbl["requires"] = requires
    if gate_timeout is not None:
        claim_tbl["gate_timeout"] = gate_timeout
    if environment is not None:
        if not os.path.isfile(os.path.join(d, environment)):
            raise kernel.ClaimError(
                f"pack refuses an environment that names no file: {environment!r}")
        claim_tbl["environment"] = environment

    recipe = {"claim": claim_tbl, "step": steps}

    vacuous = kernel.vacuous_gates(recipe)
    if vacuous:
        raise kernel.ClaimError(
            f"pack refuses a vacuous gate (every decider is generated): {vacuous}")

    if inputs_manifest:
        _write_manifest(d, inputs_manifest, input_paths)

    with open(os.path.join(d, kernel.RECIPE), "w", encoding="utf-8") as f:
        f.write(render.dump_recipe(recipe))

    result = kernel.run_gate(gate, d, recipe)
    if result["status"] != "ok":
        raise kernel.ClaimError(f"pack refuses: the gate did not pass: {result['status']}")

    if by:
        kernel.ledger(d, {"event": "producer", "model": by})

    manifest = kernel.seal(d)

    if component:
        comp_dir = component["claim"]
        dest = os.path.join(d, kernel.STORE, "sealed", comp_name)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if os.path.isdir(dest):
            shutil.rmtree(dest)
        shutil.copytree(comp_dir, dest)

    return {"ok": True, "root": manifest["root"]}
