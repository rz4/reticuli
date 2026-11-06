"""pack: a project becomes a claim.

One authoring boundary, three sources: a traced session (`accept`), a recipe
the project already declares (zero flags), or the declaration language below.
The implementation is GENERATED -- regrowable, outside identity -- and the
check is the CLAIM. Editing the implementation keeps the root; editing the
check moves it.

The ritual is RECIPE-FIRST: the gate judges a claim, and a claim includes its
recipe, so the recipe is on disk before the warm gate runs. Every chained
criterion in this repository writes its verdict only when a recipe file is
present, and a pack that gated first starved them all.
"""
import glob as _glob
import os
import shutil

from . import authoring
from . import kernel
from . import registry
from . import render
from ._util import hash_bytes, safe_path

#: A fresh claim is born here. Guidance is outside identity at format 3, so
#: three correct kernels pack one claim and mint one name.
DEFAULT_FORMAT = authoring.DEFAULT_FORMAT


def _expand(path: str, patterns) -> list:
    """A declared pattern is a SET of files -- and the empty set is a set.

    The chain packs twenty layers with uniform patterns that legitimately
    select nothing on the early layers, so a no-match pattern contributes no
    steps and refuses nothing.
    """
    found = []
    for pattern in patterns or []:
        for match in sorted(_glob.glob(pattern, root_dir=path,
                                       recursive=True)):
            name = match.replace(os.sep, "/")
            if not os.path.isfile(os.path.join(path, match)):
                continue
            if name.split("/")[0] == kernel.STORE:
                continue
            if name not in found:
                found.append(name)
    return found


def _manifest_text(path: str, declared) -> str:
    lines = []
    for name in declared:
        inner = safe_path(path, name)
        digest = "-"
        if inner and os.path.isfile(inner):
            with open(inner, "rb") as handle:
                digest = hash_bytes(handle.read())
        lines.append(f"{digest}  {name}")
    return "\n".join(lines) + "\n"


def _declared_mode(path: str, name=None) -> dict:
    """`reticuli.toml` IS the declaration: run its gates warm and seal."""
    parsed = kernel.load_recipe(path)
    for gate in kernel.gates(parsed):
        outcome = kernel.run_gate(gate["run"], path, parsed)
        if outcome["status"] != "ok":
            raise kernel.ClaimError(
                f"gate {gate.get('output')!r} did not earn its verdict "
                f"({outcome['status']}): "
                f"{(outcome['stderr'] or outcome['stdout'])[-400:]}")
    manifest = kernel.seal(path)
    return {"ok": True, "root": manifest["root"], "name": manifest["name"],
            "generated": len(kernel.generated_outputs(parsed)),
            "inputs": len((parsed.get("claim") or {}).get("inputs") or []),
            "component": None, "path": path}


def pack(path: str, name=None, generated=None, inputs=None, gate=None,
         gate_output=None, component=None, envelope=None, claim_format=None,
         mutation_floor=None, requires=None, by=None, inputs_manifest=None,
         environment=None, accept=None, into=None, claim=None,
         carried=None, constrains=None, assembles=None, tolerance=None,
         gate_timeout=None, pytest=None, force=False, ws=None) -> dict:
    """Seal a project as a claim, earning its verdict first."""
    if accept:
        if not into:
            raise kernel.ClaimError(
                "a session pack needs somewhere to put the claim: -o DIR")
        return authoring.build_claim(
            path, accept, into, name=name, claim=claim, generated=generated,
            claim_format=claim_format or DEFAULT_FORMAT)

    if pytest and not gate:
        target = pytest if isinstance(pytest, str) else "tests"
        gate_output = gate_output or "OK"
        gate = f"python3 -m pytest -q {target} && printf ok > {gate_output}"
        inputs = list(inputs or []) + [target]

    if not generated and not gate:
        if os.path.isdir(path) and (
                os.path.isfile(os.path.join(path, kernel.RECIPE))
                or os.path.isfile(os.path.join(path, kernel.LEGACY_RECIPE))):
            return _declared_mode(path, name)
        raise kernel.ClaimError(
            f"nothing to pack in {path}: no recipe to read, and no "
            f"implementation or gate declared")
    if not os.path.isdir(path):
        raise kernel.ClaimError(f"nothing to pack in {path}: no such directory")
    if not gate or not gate_output:
        raise kernel.ClaimError(
            "a claim needs a gate and the verdict it pins: "
            "gate=..., gate_output=...")

    fmt = DEFAULT_FORMAT if claim_format is None else int(claim_format)
    name = name or os.path.basename(os.path.abspath(path))
    hint = "guidance" if fmt >= 3 else "request"

    supplied, component_name, component_root = [], None, None
    if component:
        component_name = component.get("name")
        supplied = list(component.get("outputs") or [])
        component_root = kernel.read_manifest(component["claim"])["root"]

    produced = [p for p in _expand(path, generated) if p not in supplied]
    carried_files = [c for c in _expand(path, carried)
                     if c not in supplied and c not in produced]
    declared_inputs = [i for i in _expand(path, inputs)
                       if i not in produced and i not in supplied
                       and i not in carried_files and i != gate_output]

    if environment:
        where = safe_path(path, environment)
        if not where or not os.path.isfile(where):
            raise kernel.ClaimError(
                f"[claim] environment names no file: {environment!r}")

    table = {"name": name}
    if fmt > 1:
        table["format"] = fmt
    table["inputs"] = declared_inputs
    if requires:
        table["requires"] = list(requires)
    if gate_timeout is not None:
        table["gate_timeout"] = float(gate_timeout)
    if mutation_floor is not None:
        table["mutation_floor"] = float(mutation_floor)
    if tolerance is not None:
        table["tolerance"] = float(tolerance)
    if envelope:
        table["envelope"] = dict(envelope)
    if environment:
        table["environment"] = environment
    if inputs_manifest:
        table["inputs_manifest"] = inputs_manifest
    if constrains:
        table["constrains"] = dict(constrains)
    if assembles:
        table["assembles"] = list(assembles)

    steps = []
    for output in supplied:
        steps.append({"kind": "produce", "output": output,
                      "class": "generated", "from": component_name,
                      hint: f"supplied by the {component_name} component"})
    for output in produced:
        steps.append({"kind": "produce", "output": output,
                      "class": "generated",
                      hint: f"regenerate {output} to pass the gate"})
    for output in carried_files:
        steps.append({"kind": "produce", "output": output,
                      "class": "carried"})
    steps.append({"kind": "gate", "output": gate_output,
                  "class": "validated", "run": gate})
    proposed = {"claim": table, "step": steps}

    vacuous = kernel.vacuous_gates(proposed)
    if vacuous:
        raise kernel.ClaimError(
            f"vacuous gate(s) {', '.join(str(v) for v in vacuous)}: every "
            f"file deciding the verdict is generated, so the root would fit "
            f"any implementation that prints ok. Declare the check as an "
            f"input")

    if inputs_manifest:
        with open(os.path.join(path, inputs_manifest), "w",
                  encoding="utf-8") as handle:
            handle.write(_manifest_text(path, declared_inputs))

    recipe_name = kernel.RECIPE
    if os.path.isfile(os.path.join(path, kernel.LEGACY_RECIPE)) \
            and not os.path.isfile(os.path.join(path, kernel.RECIPE)):
        recipe_name = kernel.LEGACY_RECIPE
    with open(os.path.join(path, recipe_name), "w", encoding="utf-8") as f:
        f.write(render.toml(proposed))

    links = None
    if component:
        drawer = os.path.join(path, kernel.SEALED, component_name)
        if not os.path.isdir(drawer):
            registry._copy_claim(component["claim"], drawer)
        links = [{"input": output, "component": component_name,
                  "root": component_root, "output": output}
                 for output in supplied]

    parsed = kernel.load_recipe(path)
    outcome = kernel.run_gate(gate, path, parsed)
    if outcome["status"] != "ok":
        raise kernel.ClaimError(
            f"gate {gate_output!r} did not earn its verdict "
            f"({outcome['status']}): "
            f"{(outcome['stderr'] or outcome['stdout'])[-400:]}")

    manifest = (registry.seal_with(path, components=links) if links
                else kernel.seal(path))
    if by:
        kernel.ledger(path, {"event": "producer", "model": by,
                             "blind": False})
    return {"ok": True, "root": manifest["root"], "name": manifest["name"],
            "generated": len(produced) + len(supplied),
            "inputs": len(declared_inputs), "component": component_name,
            "path": path, "gate": outcome["status"],
            "quarantine": outcome["quarantine"]}
