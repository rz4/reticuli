"""Pack: a project as a self-claim (spec/layers.md, "authoring"; v1's
`pack`, keyword-compatible with the repository's own `scripts/selfclaim.py`
consumer).

A packed project is sealed IN PLACE: the implementation (`generated`, one
or more glob patterns expanded against the project directory, forward-slash
paths) is regrowable and outside identity; the check (`inputs`, named
exactly) is the claim. `pack` refuses a gate every one of whose deciders is
itself generated -- a vacuous check over a wrong implementation would seal
at the same root as a real one (spec/claim-format.md) -- runs the gate once,
through `kernel.run_gate` (scrubbed, sandboxed, bounded; never
`kernel.sandbox` directly), and seals through `registry.seal_with`, the
exchange layer's own sealing primitive, so a declared `component` lands as
ordinary manifest residue (`components`) like any other layered claim.
"""
import glob
import os
import shutil

from reticuli import _util
from reticuli import kernel
from reticuli import registry
from reticuli import render


def _expand_globs(d: str, patterns) -> list:
    out = []
    for pattern in patterns:
        for full in sorted(glob.glob(os.path.join(d, pattern))):
            if os.path.isfile(full):
                rel = os.path.relpath(full, d).replace(os.sep, "/")
                if rel not in out:
                    out.append(rel)
    return sorted(out)


def pack(d: str, name: str, generated, inputs, gate: str, gate_output: str, *,
          envelope=None, claim_format=None, mutation_floor=None,
          requires=None, by=None, inputs_manifest=None,
          environment=None, component=None) -> dict:
    """Seal `d` in place as a self-claim: `generated` (glob patterns,
    expanded to the files currently present) is the regrowable
    implementation, `inputs` the claim. See the module docstring for the
    keyword surface.
    """
    gen_paths = _expand_globs(d, generated)
    inputs = list(inputs)

    for p in set(gen_paths) | set(inputs):
        _util.safe_path(d, p)

    comp_outputs = set(component["outputs"]) if component else set()
    steps = []
    for out in gen_paths:
        step = {"kind": "produce", "output": out, "class": "generated"}
        if component is not None and out in comp_outputs:
            step["from"] = component["name"]
        steps.append(step)
    steps.append({"kind": "gate", "output": gate_output, "class": "validated", "run": gate})

    claim = {"name": name}
    if inputs_manifest is not None:
        claim["inputs_manifest"] = inputs_manifest
    else:
        claim["inputs"] = inputs

    fmt = claim_format if claim_format is not None else (2 if inputs_manifest is not None else None)
    if fmt is not None:
        claim["format"] = fmt
    if envelope is not None:
        claim["envelope"] = envelope
    if mutation_floor is not None:
        claim["mutation_floor"] = mutation_floor
    if requires is not None:
        claim["requires"] = requires
    if environment is not None:
        claim["environment"] = environment

    draft = {"claim": claim, "step": steps}

    vac = kernel.vacuous_gates(draft)
    if vac:
        raise kernel.ClaimError(
            f"gate(s) {vac} are vacuous: every decider is a generated output")

    if environment is not None and not os.path.isfile(_util.safe_path(d, environment)):
        raise kernel.ClaimError(f"environment names no file: {environment!r}")

    missing = kernel.preflight(draft)
    if missing:
        raise kernel.ClaimError(f"environment: missing requirement(s) {missing}")

    with open(os.path.join(d, kernel.RECIPE), "w", encoding="utf-8") as f:
        f.write(render.dump_recipe(draft))

    if inputs_manifest is not None:
        lines = []
        for p in sorted(inputs):
            full = _util.safe_path(d, p)
            with open(full, "rb") as f:
                digest = _util.hash_bytes(f.read())
            lines.append(f"{digest}  {p}")
        with open(os.path.join(d, inputs_manifest), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + ("\n" if lines else ""))

    comp_links = None
    if component is not None:
        comp_name = component["name"]
        comp_dest = os.path.join(d, kernel.STORE, "sealed", comp_name)
        if os.path.isdir(comp_dest):
            shutil.rmtree(comp_dest)
        os.makedirs(os.path.dirname(comp_dest), exist_ok=True)
        shutil.copytree(component["claim"], comp_dest)
        comp_root = kernel.verify(comp_dest)["root"]
        comp_links = [{"component": comp_name, "root": comp_root, "output": out}
                      for out in sorted(comp_outputs)]

    outcome = kernel.run_gate(gate, d, draft)
    if outcome["status"] != "ok":
        raise kernel.ClaimError(f"gate {gate_output!r} did not pass: {outcome['status']}")

    if by is not None:
        kernel.ledger(d, {"event": "producer", "vendor": "unknown", "model": by, "blind": True})

    manifest = registry.seal_with(d, components=comp_links)
    return {"ok": True, "root": manifest["root"], "name": manifest.get("name")}
