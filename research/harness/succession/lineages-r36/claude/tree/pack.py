"""A project becomes a claim: the implementation generated, the check pinned.

`pack` is the single authoring boundary. It takes what a project already
has -- some files that are the implementation, some that are the criteria,
and a command that decides -- and writes the recipe, earns the verdict, and
seals.

The ritual is RECIPE-FIRST, and that order is load-bearing. The gate judges
a CLAIM, and a claim includes its recipe, so a criterion is entitled to ask
what claim it is in; every check in this repository writes its verdict only
when a recipe is present. A pack that gated before writing the recipe would
starve them all.

A fresh claim is born at FORMAT 3, where producer guidance is outside
identity. Three correct kernels once packed one project and minted two
names, the divergent byte being a default guidance line -- and no criterion
can pin guidance text, because by doctrine guidance cannot reject a
realization. So the format moves it out of the root instead.
"""
import glob as _glob
import os
import shutil

from . import _util
from . import kernel
from . import render

DEFAULT_FORMAT = 3


def _expand(where: str, patterns) -> list:
    """A declared pattern is a SET of paths, and an empty set is a set.

    `generated` and `inputs` are a symmetric pair of pattern lists. A
    pattern matching no file contributes nothing and refuses nothing: the
    chains pack every layer with uniform patterns that legitimately select
    nothing on the early ones.
    """
    found, seen = [], set()
    for pattern in patterns or []:
        if any(ch in pattern for ch in "*?[") is False:
            if pattern not in seen:
                seen.add(pattern)
                found.append(pattern)
            continue
        for path in sorted(_glob.glob(os.path.join(where, pattern),
                                      recursive=True)):
            if not os.path.isfile(path):
                continue
            relative = os.path.relpath(path, where).replace(os.sep, "/")
            if relative not in seen:
                seen.add(relative)
                found.append(relative)
    return found


def _write_manifest(where: str, name: str, inputs) -> None:
    """A format-2 corpus listing: one entry per line, `<sha256>  <path>`, so
    the file is meaningful on its own. It is itself a pinned input, which is
    what keeps the corpus committed to by the root."""
    lines = ["# inputs pinned by this claim, one per line"]
    for path in inputs:
        full = os.path.join(where, path)
        if os.path.isfile(full):
            lines.append(f"{_util.hash_file(full)}  {path}")
    with open(os.path.join(where, name), "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def _component_claim(where: str, component: dict) -> dict:
    """Copy the component's CLAIM into this claim's store, so a claim
    travels with its dependency, and describe the links for the deep audit.

    The record carries the input, the component, its root and the output it
    came from: pack WRITES this record and `registry.audit_deep` READS it,
    and the two halves are one contract.
    """
    source = component.get("claim")
    name = component.get("name")
    outputs = list(component.get("outputs") or [])
    manifest = kernel.read_manifest(source)
    drawer = os.path.join(where, kernel.STORE, "sealed", name)
    if os.path.isdir(drawer):
        shutil.rmtree(drawer)

    def ignore(directory, names):
        if os.path.realpath(directory) == \
                os.path.realpath(os.path.join(source, kernel.STORE)):
            return {"sealed", "deps", "scratch"}
        return set()
    shutil.copytree(source, drawer, symlinks=False, ignore=ignore)
    return {"name": name, "root": manifest["root"],
            "links": [{"input": output, "component": name,
                       "root": manifest["root"], "output": output}
                      for output in outputs]}


def pack(path: str, name: str | None = None, generated=None, inputs=None,
         gate: str | None = None, gate_output: str | None = None,
         component=None, envelope=None, claim_format: int | None = None,
         mutation_floor=None, requires=None, by: str | None = None,
         inputs_manifest: str | None = None, environment: str | None = None,
         tolerance=None, carried=None, accept=None) -> dict:
    """Write the recipe, earn the verdict warm, and seal.

    Returns the sealed root with the counts a caller reports, so a chain
    builder can print one line per layer.
    """
    where = os.path.abspath(path)
    if not os.path.isdir(where):
        raise kernel.ClaimError(f"nothing to pack: no directory at {path}")
    fmt = DEFAULT_FORMAT if claim_format is None else int(claim_format)
    if fmt < 1:
        raise kernel.ClaimError(f"a claim format is a positive integer, "
                                f"not {claim_format!r}")
    name = name or os.path.basename(where)

    declared_inputs = _expand(where, inputs)
    produced = _expand(where, generated)
    carried_files = _expand(where, carried)
    if environment:
        if not os.path.isfile(os.path.join(where, environment)):
            raise kernel.ClaimError(
                f"the declared environment names no file: {environment!r}")
    if not gate:
        raise kernel.ClaimError(
            "a claim needs a gate: the command that decides whether a "
            "realization is accepted")
    verdicts = [gate_output] if gate_output else list(accept or [])
    if not verdicts:
        raise kernel.ClaimError(
            "a gate needs an output to pin: name the verdict file")

    supplied = {}
    component_record = None
    if component:
        component_record = _component_claim(where, component)
        supplied = {link["output"]: component_record["name"]
                    for link in component_record["links"]}
        for output in supplied:
            if output not in produced:
                produced.append(output)

    produced = [p for p in produced
                if p not in verdicts and p not in declared_inputs
                and p not in carried_files]
    if inputs_manifest:
        _write_manifest(where, inputs_manifest, declared_inputs)

    table = {"name": name}
    if fmt > 1:
        table["format"] = fmt
    if requires:
        table["requires"] = list(requires)
    if inputs_manifest:
        table["inputs_manifest"] = inputs_manifest
    if environment:
        table["environment"] = environment
    table["inputs"] = declared_inputs
    if envelope:
        table["envelope"] = dict(envelope)
    if tolerance is not None:
        table["tolerance"] = float(tolerance)
    if mutation_floor is not None:
        table["mutation_floor"] = float(mutation_floor)

    hint = "guidance" if fmt >= 3 else "request"
    steps = []
    for output in produced:
        step = {"kind": "produce", "output": output, "class": "generated"}
        if output in supplied:
            step["from"] = supplied[output]
        step[hint] = f"regenerate {output} to pass the gate"
        steps.append(step)
    for output in carried_files:
        steps.append({"kind": "produce", "output": output,
                      "class": "carried"})
    for output in verdicts:
        steps.append({"kind": "gate", "output": output,
                      "class": "validated", "run": gate})
    recipe = {"claim": table, "step": steps}

    vacuous = kernel.vacuous_gates(recipe)
    if vacuous:
        raise kernel.ClaimError(
            f"the gate {vacuous[0]!r} is vacuous: every file deciding it is "
            f"generated, so the root would fit any implementation that "
            f"prints ok. Declare the check as an input to make it a "
            f"criterion")

    # recipe FIRST: the warm gate runs inside the claim it certifies
    with open(os.path.join(where, kernel.RECIPE), "w",
              encoding="utf-8") as handle:
        handle.write(render.dump_recipe(recipe))
    legacy = os.path.join(where, kernel.LEGACY_RECIPE)
    if os.path.isfile(legacy):
        os.remove(legacy)

    parsed = kernel.load_recipe(where)
    for step in kernel.gates(parsed):
        outcome = kernel.run_gate(step["run"], where, parsed)
        if outcome["status"] != "ok" or \
                not os.path.isfile(os.path.join(where, step["output"])):
            raise kernel.ClaimError(
                f"the gate {step['output']!r} does not pass here "
                f"({outcome['status']}), so there is no verdict to pin: "
                f"{(outcome['stderr'] or outcome['stdout'])[-300:]}")

    manifest = kernel.seal(
        where, components=(component_record["links"]
                           if component_record else None))
    if by:
        kernel.ledger(where, {"event": "producer", "model": by,
                              "calls": 1, "blind": False})
    return {"ok": True, "root": manifest["root"], "name": manifest["name"],
            "generated": len(produced) + len(carried_files),
            "inputs": len(declared_inputs) +
            (1 if inputs_manifest else 0) + (1 if environment else 0),
            "component": component_record["name"] if component_record
            else None,
            "format": fmt, "path": where,
            "verdicts": verdicts}
