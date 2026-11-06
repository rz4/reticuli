"""A project becomes a claim: the implementation generated, the check claimed.

`pack` is the single authoring boundary.  It takes a project that already
works, declares which files are the CRITERIA and which are the
IMPLEMENTATION, earns the gate's verdict warm, and seals.

Four of its properties were each measured into existence:

* **The ritual is recipe-first.**  The gate judges a CLAIM, and a claim
  includes its recipe, so the recipe is in the room when the warm gate runs.
  A criterion is entitled to ask what claim it is in — every check in this
  repository writes its verdict only when a recipe is present — and a pack
  that gated before writing the recipe starved the whole chain's verdicts.
* **A fresh claim is born at format 3.**  Guidance is not identity, and
  pack's own default hint line is a byte that differs between conforming
  tools: at format 1 three correct kernels packed one claim and minted two
  names.  `claim_format=1` still writes the KEYLESS era-1 recipe, because an
  explicit `format = 1` line would mint a different root than every era-1
  claim already sealed.
* **A declared pattern is a SET, and the empty set is a set.**  `generated`
  and `inputs` are a symmetric pair of pattern lists; a pattern matching zero
  files contributes no steps and refuses nothing.
* **Gates run through `kernel.run_gate`, never a sandbox runner directly** —
  that function owns the scrub, the bound, and the confinement together, and
  reaching past it once let an inherited secret reach a verdict.
"""
import glob
import json
import os
import shutil

from . import _util, kernel, registry, render

#: The format a claim is born at.
DEFAULT_FORMAT = 3


def _expand(where: str, patterns, existing=None) -> list:
    """Expand a pattern list in place, preserving the author's order.

    Each pattern's own matches are sorted (so the result does not depend on
    readdir order), and a pattern that selects nothing selects nothing.
    """
    out = list(existing or [])
    for pattern in patterns or []:
        if any(ch in pattern for ch in "*?["):
            matches = sorted(
                os.path.relpath(path, where).replace(os.sep, "/")
                for path in glob.glob(os.path.join(where, pattern))
                if os.path.isfile(path))
        else:
            matches = [pattern] if os.path.isfile(
                os.path.join(where, pattern)) else []
        for match in matches:
            if match not in out:
                out.append(match)
    return out


def _manifest_text(where: str, inputs: list) -> str:
    """`<sha256>  <path>` per line, so the manifest is meaningful alone."""
    lines = []
    for name in inputs:
        path = kernel._safe(where, name)
        lines.append(f"{kernel._hash_file(path)}  {name}")
    return "\n".join(lines) + "\n"


def pack(path: str, name: str, generated=None, inputs=None, gate: str = None,
         gate_output: str = None, component=None, envelope=None,
         claim_format: int = None, mutation_floor=None, requires=None,
         by: str = None, inputs_manifest: str = None, environment: str = None,
         carried=None, tolerance=None, constrains=None, assembles=None,
         gate_timeout=None) -> dict:
    """Declare a project's acceptance boundary and seal it."""
    where = os.path.abspath(path)
    if not os.path.isdir(where):
        raise kernel.ClaimError(f"nothing to pack: no directory at {path!r}")
    if not gate or not gate_output:
        raise kernel.ClaimError(
            "pack needs a gate command and the verdict it pins")

    fmt = DEFAULT_FORMAT if claim_format is None else int(claim_format)
    hint_key = "request" if fmt < 2 else "guidance"

    supplied = {}
    if component:
        for output in component.get("outputs") or []:
            supplied[output] = component["name"]

    produced = _expand(where, generated)
    shipped = _expand(where, carried)
    declared = _expand(where, inputs)
    if environment:
        if not os.path.isfile(os.path.join(where, environment)):
            raise kernel.ClaimError(
                f"the declared environment {environment!r} names no file in "
                f"this claim; a hash-pinned requirements file is a criterion "
                f"and must be present to be pinned")

    claim_table = {"name": name}
    if fmt > 1:
        # format 1 is the implicit default, and writing it explicitly would
        # mint a different root than every era-1 claim already sealed.
        claim_table["format"] = fmt
    claim_table["inputs"] = declared
    if inputs_manifest:
        claim_table["inputs_manifest"] = inputs_manifest
    if environment:
        claim_table["environment"] = environment
    if requires:
        claim_table["requires"] = list(requires)
    if envelope:
        claim_table["envelope"] = dict(envelope)
    if tolerance is not None:
        claim_table["tolerance"] = float(tolerance)
    if mutation_floor is not None:
        claim_table["mutation_floor"] = float(mutation_floor)
    if gate_timeout is not None:
        claim_table["gate_timeout"] = gate_timeout
    if constrains:
        claim_table["constrains"] = dict(constrains)
    if assembles:
        claim_table["assembles"] = list(assembles)

    steps = []
    for output in produced:
        step = {"kind": "produce", "output": output, "class": "generated"}
        if output in supplied:
            step["from"] = supplied[output]
            step[hint_key] = (f"supplied by the {supplied[output]} component")
        else:
            step[hint_key] = f"regenerate {output} to pass the gate"
        steps.append(step)
    for output in shipped:
        steps.append({"kind": "produce", "output": output,
                      "class": "carried"})
    steps.append({"kind": "gate", "output": gate_output,
                  "class": "validated", "run": gate})
    recipe = {"claim": claim_table, "step": steps}

    vacuous = kernel.vacuous_gates(recipe)
    if vacuous:
        raise kernel.ClaimError(
            f"the gate(s) {', '.join(vacuous)} are vacuous: every file that "
            f"decides them is generated, so the root would fit any "
            f"implementation that prints ok. Declare the check as an input")

    # The recipe FIRST: the warm gate runs inside the claim it certifies.
    recipe_path = os.path.join(where, kernel.RECIPE)
    with open(recipe_path, "w", encoding="utf-8") as handle:
        handle.write(render.dump_recipe(recipe))
    if inputs_manifest:
        with open(os.path.join(where, inputs_manifest), "w",
                  encoding="utf-8") as handle:
            handle.write(_manifest_text(where, declared))

    if component:
        drawer = os.path.join(where, kernel.STORE, "sealed",
                              component["name"])
        if os.path.exists(drawer):
            shutil.rmtree(drawer, ignore_errors=True)
        os.makedirs(os.path.dirname(drawer), exist_ok=True)
        # symlinks=True: a component's own drawer links its ancestors, and
        # following those links would copy each ancestor once per PATH that
        # reaches it — the unfolding this project keeps measuring.
        shutil.copytree(component["claim"], drawer, symlinks=True,
                        ignore=shutil.ignore_patterns("scratch"))

    parsed = kernel.load_recipe(where)
    outcome = kernel.run_gate(gate, where, parsed)
    if outcome["status"] != "ok":
        raise kernel.ClaimError(
            f"the gate did not earn its verdict ({outcome['status']}): "
            f"{(outcome['stderr'] or outcome['stdout'])[-400:]}")
    if not os.path.isfile(os.path.join(where, gate_output)):
        raise kernel.ClaimError(
            f"the gate ran clean but wrote no {gate_output!r}; pack refuses "
            f"to seal an unearned verdict")

    if by:
        kernel.ledger(where, {"event": "producer", "model": by,
                              "when": _util.stamp()})
    links = [{"input": output, "component": component["name"],
              "root": kernel.read_manifest(component["claim"])["root"],
              "output": output}
             for output in (component.get("outputs") or [])] if component \
        else None
    manifest = registry.seal_with(where, components=links)
    return {
        "ok": True, "root": manifest["root"], "name": manifest["name"],
        "generated": len(produced), "inputs": len(declared),
        "carried": len(shipped),
        "component": component["name"] if component else None,
        "claim": where, "format": fmt,
    }
