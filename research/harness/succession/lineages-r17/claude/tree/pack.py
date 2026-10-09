"""Pack: a project as a self-claim (`spec/layers.md`).

`pack(root, name, generated, inputs, gate, gate_output, ...)` writes a
recipe directly into an existing project directory and seals it in place:
the implementation is generated (regrowable, outside identity), the check
is the claim (pinned, inside it). `generated`/`inputs` are patterns,
expanded against the files actually present (`spec/claim-format.md`) --
a literal name with no wildcard passes through unchanged. The recipe is
written to disk BEFORE the gate ever runs, so a gate that asks "am I
running inside a claim?" gets a true answer. A gate whose every decider is
a generated file is vacuous and refused by name, before it is ever run.
Gates run only through `kernel.run_gate` -- never `kernel.sandbox`
directly -- so packing a project never seals an inherited secret into a
verdict.

A declared `component` -- `{"name", "claim", "outputs"}` -- is embedded
under this claim's own store (`.reticuli/sealed/<name>`) so `audit_deep`
can re-earn it without a workspace to resolve it against; a generated
output also named in the component's `outputs` is declared `from` that
component rather than guided, since its bytes are the component's to
produce, not this claim's own producer's.

Stdlib only.
"""
import glob
import os
import shutil

from reticuli import _util, kernel, render


def _expand_patterns(root: str, patterns) -> list:
    """Each pattern, glob-expanded against `root` and sorted; a literal
    name with no wildcard characters passes through unchanged. Order is
    patterns-in-order, matches-sorted-within-a-pattern, deduplicated."""
    out = []
    for pat in patterns:
        is_glob = any(ch in pat for ch in "*?[]")
        matches = sorted(
            os.path.relpath(m, root).replace(os.sep, "/")
            for m in glob.glob(os.path.join(root, pat))
            if os.path.isfile(m))
        if matches:
            out.extend(matches)
        elif not is_glob:
            out.append(pat)
    seen = set()
    result = []
    for p in out:
        if p not in seen:
            seen.add(p)
            result.append(p)
    return result


def pack(root: str, name: str, generated=None, inputs=None, gate: str = None,
          gate_output: str = None, *, component: dict = None, envelope: dict = None,
          claim_format: int = None, mutation_floor: float = None,
          requires: list = None, by: str = None, inputs_manifest: str = None,
          environment: str = None) -> dict:
    generated = generated or []
    inputs = inputs or []
    fmt = 3 if claim_format is None else claim_format
    guidance_key = "request" if fmt == 1 else "guidance"

    gen_paths = _expand_patterns(root, generated)
    in_paths = _expand_patterns(root, inputs)

    carried_from = {}
    if component is not None:
        for out in component.get("outputs", []):
            carried_from[out] = component["name"]

    claim = {"name": name}
    if fmt != 1:
        claim["format"] = fmt

    if environment is not None:
        if not os.path.isfile(os.path.join(root, environment)):
            raise kernel.ClaimError(
                f"environment file missing: {environment!r}")
        claim["environment"] = environment

    if inputs_manifest is not None:
        lines = []
        for p in in_paths:
            with open(os.path.join(root, p), "rb") as f:
                digest = _util.hash_bytes(f.read())
            lines.append(f"{digest}  {p}")
        with open(os.path.join(root, inputs_manifest), "w", encoding="utf-8") as f:
            f.write(("\n".join(lines) + "\n") if lines else "")
        claim["inputs_manifest"] = inputs_manifest
    else:
        claim["inputs"] = in_paths

    if envelope is not None:
        claim["envelope"] = envelope
    if mutation_floor is not None:
        claim["mutation_floor"] = mutation_floor
    if requires is not None:
        claim["requires"] = requires

    steps = []
    for g in gen_paths:
        step = {"kind": "produce", "output": g, "class": "generated"}
        if g in carried_from:
            step["from"] = carried_from[g]
        else:
            step[guidance_key] = f"regenerate {g} to pass the gate"
        steps.append(step)
    steps.append({"kind": "gate", "output": gate_output, "class": "validated",
                  "run": gate})

    doc = {"claim": claim, "step": steps}

    if component is not None:
        dest = os.path.join(root, kernel.STORE, "sealed", component["name"])
        if os.path.isdir(dest):
            shutil.rmtree(dest)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copytree(component["claim"], dest)

    os.makedirs(os.path.join(root, kernel.STORE), exist_ok=True)
    with open(os.path.join(root, kernel.RECIPE), "w", encoding="utf-8") as f:
        f.write(render.dump_recipe(doc))

    vacuous = set(kernel.vacuous_gates(doc))
    if gate_output in vacuous:
        raise kernel.ClaimError(
            f"gate {gate_output!r} is vacuous: every decider is a "
            f"generated file -- it cannot be its own criterion")

    result = kernel.run_gate(gate, root, doc)
    if result["status"] != "ok":
        raise kernel.ClaimError(f"gate {gate_output!r} {result['status']}")

    if by is not None:
        kernel.ledger(root, {"event": "producer", "model": by})

    manifest = kernel.seal(root)
    return {"ok": True, "root": manifest["root"]}
