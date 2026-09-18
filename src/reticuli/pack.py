"""Pack a project into a self-claim.

Declare a project's code as produce outputs (generated — the implementation), its
check harness as pinned inputs, and a gate that runs the check. Sealing makes the
project a Reticuli claim: `ret rebuild .` regrows a fresh implementation, runs the
gate, and — because the code is generated and the root is the claim — lands on the
*same root*. A project that passes its own check is a point in its own basin.
"""
from __future__ import annotations

import glob
import os
import shutil
import sys

from . import _util, kernel, render


def _match(root: str, patterns: list[str]) -> list[str]:
    files: list[str] = []
    for pat in patterns:
        for f in sorted(glob.glob(pat, root_dir=root, recursive=True)):
            if os.path.isfile(os.path.join(root, f)) and f not in files:
                files.append(f)
    return files


def _produce_step(f: str, component: dict | None, fmt: int = 1) -> dict:
    # at format 3+ producer guidance leaves the root, and the recipe spells
    # it `guidance`; older formats keep `request`, byte-for-byte
    key = "guidance" if fmt >= 3 else "request"
    step = {"kind": "produce", "output": f, key: f"regenerate {f} to pass the gate",
            "class": "generated"}
    if component and f in component["outputs"]:
        step["from"] = component["name"]           # supplied by a component, still generated
        step[key] = f"supplied by the {component['name']} component"
    return step


def _relay_gate(r: dict, gate: str, root: str, output: str | None) -> None:
    """The gate's own voice, in full, on STDERR — stdout is the report's.
    A gate that passed while warning on stderr warned for a reason."""
    for stream in ("stdout", "stderr"):
        if r[stream]:
            print(r[stream], end="", file=sys.stderr)
    if r["returncode"] != 0 or (output and not os.path.isfile(os.path.join(root, output))):
        # The TAIL of stderr, never the head: a traceback's first 200
        # characters are boilerplate; the line that says what went wrong is
        # the last one.
        detail = (r["stderr"] or r["stdout"] or "").strip()
        if len(detail) > 1500:
            detail = "…" + detail[-1500:]
        raise kernel.ClaimError(f"pack: the gate did not pass warm ({gate}): {detail}")


def pack_declared(root: str) -> dict:
    """Seal a project whose reticuli.toml already IS the declaration.

    Nothing is inferred and the recipe is not rewritten: the declared
    environment is furnished, every gate step runs warm through the one gate
    entry point, and the claim seals in place. Acceptance criteria must pass
    before a claim is created — the same rule as every other packing path."""
    root = os.path.abspath(root)
    recipe = kernel.load_recipe(root)
    venv_bin = kernel.furnish(recipe, root)
    for step in recipe.get("step", []):
        if step.get("kind") != "gate":
            continue
        r = kernel.run_gate(step["run"], root, recipe, extra_path=venv_bin)
        _relay_gate(r, step["run"], root, step.get("output"))
    manifest = kernel.seal(root)
    gen = [s for s in recipe.get("step", [])
           if s.get("kind") == "produce"
           and s.get("class", "generated") == "generated"]
    claim = recipe.get("claim") or {}
    return {"ok": True, "name": manifest["name"], "root": manifest["root"],
            "generated": len(gen), "inputs": len(claim.get("inputs") or [])}


def pack(root: str, name: str, generated: list[str], inputs: list[str],
         gate: str, gate_output: str, component: dict | None = None,
         mutation_floor: float | None = None, requires: list[str] | None = None,
         by: str | None = None, inputs_manifest: str | None = None,
         environment: str | None = None, envelope: dict | None = None,
         claim_format: int | None = None) -> dict:
    """Seal a project as a self-claim. With `component` ({name, claim, outputs})
    the listed generated files are declared `from` that component — generated code
    the claim layers on: `ret rebuild --recursive` rebuilds the component first
    and threads its output up, so the self-host becomes layered."""
    root = os.path.abspath(root)
    input_files = _match(root, inputs)
    generated_files = [f for f in _match(root, generated) if f not in input_files]
    if not generated_files:
        raise kernel.ClaimError(
            f"pack: no generated files matched {generated} under {root}. "
            f"Patterns are relative to the claim directory; "
            f"{len(input_files)} file(s) matched --input and are excluded "
            f"from generated, since a file cannot be both.")

    links = None
    if component:
        missing = [f for f in component["outputs"] if f not in generated_files]
        if missing:
            raise kernel.ClaimError(f"pack: component outputs not among generated files: {missing}")
        root_c = kernel.read_manifest(component["claim"])["root"]
        links = [{"input": f, "component": component["name"], "root": root_c, "output": f}
                 for f in component["outputs"]]

    claim: dict = {"name": name, "inputs": input_files}
    if inputs_manifest:
        # Move the input list out of the recipe body and into a pinned file.
        # A corpus of any size then costs one line in the recipe instead of
        # hundreds, while remaining fully committed to: the manifest is itself
        # a pinned input, so changing the corpus changes the manifest and moves
        # the root. Each line carries the file's digest too, which costs
        # nothing and makes the manifest readable on its own.
        rows = []
        for rel in input_files:
            with open(os.path.join(root, rel), "rb") as fh:
                rows.append(f"{_util.hash_bytes(fh.read())}  {rel}")
        listing = "\n".join(rows)
        with open(os.path.join(root, inputs_manifest), "w", encoding="utf-8") as f:
            f.write(listing + "\n")
        claim = {"name": name, "format": 2, "inputs_manifest": inputs_manifest}
    if mutation_floor is not None:
        claim["mutation_floor"] = float(mutation_floor)   # the floor a crosscheck holds a redo to
    if requires:
        claim["requires"] = list(requires)      # what the gate needs from the host
    if environment:
        # the hash-pinned dependency set the gates run inside; automatically a
        # pinned input, so the versions are criteria (spec/claim-format.md)
        if not os.path.isfile(os.path.join(root, environment)):
            raise kernel.ClaimError(
                f"pack: --environment names no file: {environment} (generate "
                "one with a tool that emits hashes, e.g. `uv pip compile "
                "--generate-hashes`)")
        claim["environment"] = environment
    if envelope:
        # cost ceilings a redo commits to; a hard condition of the claim
        claim["envelope"] = dict(envelope)
    if claim_format is not None:
        # format 3 takes producer guidance out of the root; the steps below
        # spell it `guidance` to match
        claim["format"] = claim_format
    fmt = claim.get("format", 1)
    recipe = {
        "claim": claim,
        "step": [_produce_step(f, component, fmt) for f in generated_files]
                + [{"kind": "gate", "output": gate_output, "run": gate, "class": "validated"}],
    }
    if kernel.vacuous_gates(recipe):
        raise kernel.ClaimError(
            "pack: vacuous gate — every script the gate executes is a generated produce file, so "
            "the verdict would depend on no claim. Declare the check with --input.")
    with open(os.path.join(root, kernel.RECIPE), "w", encoding="utf-8") as f:
        f.write(render.dump_recipe(recipe))

    venv_bin = kernel.furnish(recipe, root)   # a declared environment is built first
    r = kernel.run_gate(gate, root, recipe,   # scrubbed + bounded, via the one gate entry point
                        extra_path=venv_bin)
    _relay_gate(r, gate, root, gate_output)

    if by:
        # WHO wrote the implementation, as ledger residue -- never in the root,
        # because authorship is not part of what a claim demands. Without it
        # `assess` cannot say whether a rebuild used a different model, so the
        # independence line has nothing to compare and says so.
        _util.ledger_add(root, {"event": "producer", "role": "original",
                                "model": by,
                                "vendor": os.environ.get("RETICULI_VENDOR")})
    manifest = kernel.seal(root)
    if links:
        # v2's `seal` takes no components argument, so the links are written onto
        # the sealed manifest here — residue beside the identity, never inside it
        # (spec/claim-format.md: manifest = {name, root} plus optional components).
        manifest["components"] = links
        _util.write_json(os.path.join(root, kernel.MANIFEST), manifest)
    if component:
        # the component's CLAIM must be resolvable from this claim for a deep
        # audit and for export: register it in the claim's own drawer unless
        # it already lives there (a self-claim hosts its layers in place)
        src = os.path.abspath(component["claim"])
        dst = os.path.join(root, kernel.STORE, "sealed", component["name"])
        if os.path.abspath(dst) != src and not os.path.exists(dst):
            shutil.copytree(src, dst)
    return {"ok": True, "name": name, "root": manifest["root"],
            "generated": len(generated_files), "inputs": len(input_files),
            "component": component["name"] if component else None}
