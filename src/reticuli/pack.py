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


def _produce_step(f: str, component: dict | None) -> dict:
    step = {"kind": "produce", "output": f, "request": f"regenerate {f} to pass the gate",
            "class": "generated"}
    if component and f in component["outputs"]:
        step["from"] = component["name"]           # supplied by a component, still generated
        step["request"] = f"supplied by the {component['name']} component"
    return step


def pack(root: str, name: str, generated: list[str], inputs: list[str],
         gate: str, gate_output: str, component: dict | None = None,
         mutation_floor: float | None = None, requires: list[str] | None = None,
         by: str | None = None, inputs_manifest: str | None = None) -> dict:
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
    recipe = {
        "claim": claim,
        "step": [_produce_step(f, component) for f in generated_files]
                + [{"kind": "gate", "output": gate_output, "run": gate, "class": "validated"}],
    }
    if kernel.vacuous_gates(recipe):
        raise kernel.ClaimError(
            "pack: vacuous gate — every script the gate executes is a generated produce file, so "
            "the verdict would depend on no claim. Declare the check with --input.")
    with open(os.path.join(root, kernel.RECIPE), "w", encoding="utf-8") as f:
        f.write(render.dump_recipe(recipe))

    r = kernel.run_gate(gate, root, recipe)   # scrubbed + bounded, via the one gate entry point
    # The gate's own voice, in full, on STDERR. Two things were wrong with
    # relaying it before: it went to stdout, where the JSON report lives, so
    # `ret pack --json | jq` failed for every claim whose gate prints anything
    # -- which is all of them, since a check that passes silently is a check
    # nobody trusts; and only stdout was relayed, so a gate that PASSED while
    # warning on stderr passed in silence, which is precisely the run whose
    # warning a reader needs.
    for stream in ("stdout", "stderr"):
        if r[stream]:
            print(r[stream], end="", file=sys.stderr)
    if r["returncode"] != 0 or not os.path.isfile(os.path.join(root, gate_output)):
        # The TAIL of stderr, never the head: a traceback's first 200 characters
        # are boilerplate, and the line that says what actually went wrong is
        # the last one. Truncating from the front hides every gate failure
        # behind "Traceback (most recent call last):".
        detail = (r["stderr"] or r["stdout"] or "").strip()
        if len(detail) > 1500:
            detail = "…" + detail[-1500:]
        raise kernel.ClaimError(f"pack: the gate did not pass warm ({gate}): {detail}")

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
