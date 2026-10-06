"""Pack a project as a self-claim: code is generated, checks are pinned."""
from __future__ import annotations

import glob
import os
import shutil
from pathlib import Path
from typing import Any

from . import kernel, registry, render, transfer
from ._util import write_json


def _expand(root: str, patterns: list[str]) -> list[str]:
    found: list[str] = []
    for pattern in patterns:
        kernel._safe(root, pattern)
        for path in sorted(glob.glob(os.path.join(root, pattern), recursive=True)):
            if os.path.isfile(path):
                rel = os.path.relpath(path, root).replace(os.sep, "/")
                kernel._safe(root, rel)
                found.append(rel)
    return list(dict.fromkeys(found))


def pack(root: str, name: str, generated: list[str], inputs: list[str],
         gate: str, gate_output: str, *, envelope: dict[str, float] | None = None,
         claim_format: int = 3, component: dict[str, Any] | None = None,
         mutation_floor: float | None = None, requires: list[str] | None = None,
         by: str | None = None, inputs_manifest: str | None = None,
         environment: str | None = None) -> dict[str, Any]:
    root = os.path.realpath(root)
    outputs = _expand(root, generated)
    pins = _expand(root, inputs)
    if not outputs:
        raise kernel.ClaimError("no generated files match")
    if len(pins) < len(inputs):
        raise kernel.ClaimError("missing pinned input")
    if set(outputs) & set(pins):
        raise kernel.ClaimError("a file cannot be both generated and pinned")
    claim: dict[str, Any] = {"name": name}
    if claim_format != 1:
        claim["format"] = claim_format
    if inputs_manifest:
        kernel._safe(root, inputs_manifest)
        listing = "".join(f"{kernel._hash_file(kernel._safe(root, p))}  {p}\n" for p in pins)
        Path(kernel._safe(root, inputs_manifest)).parent.mkdir(parents=True, exist_ok=True)
        Path(kernel._safe(root, inputs_manifest)).write_text(listing, encoding="utf-8")
        claim["inputs_manifest"] = inputs_manifest
    else:
        claim["inputs"] = pins
    if environment is not None:
        path = kernel._safe(root, environment)
        if not os.path.isfile(path):
            raise kernel.ClaimError(f"missing environment file: {environment}")
        claim["environment"] = environment
    if envelope is not None:
        claim["envelope"] = envelope
    if mutation_floor is not None:
        claim["mutation_floor"] = mutation_floor
    if requires is not None:
        claim["requires"] = requires
    component_outputs: set[str] = set()
    if component:
        component_outputs = set(component["outputs"])
        for item in component_outputs:
            if item not in outputs:
                raise kernel.ClaimError(f"component output is not generated: {item}")
    hint_key = "request" if claim_format == 1 else "guidance"
    steps = []
    for output in outputs:
        step = {"kind": "produce", "output": output, "class": "generated"}
        if output in component_outputs:
            step["from"] = component["name"]
        else:
            step[hint_key] = f"regenerate {output} to pass the gate"
        steps.append(step)
    steps.append({"kind": "gate", "output": gate_output, "class": "validated", "run": gate})
    parsed = {"claim": claim, "step": steps}
    if kernel.vacuous_gates(parsed):
        raise kernel.ClaimError("vacuous gate: every decider is generated")
    Path(kernel._safe(root, kernel.RECIPE)).write_text(render.dump_recipe(parsed), encoding="utf-8")
    verdict_path = kernel._safe(root, gate_output)
    if os.path.exists(verdict_path):
        os.unlink(verdict_path)
    outcome = kernel.run_gate(gate, root, parsed)
    if outcome["status"] != "ok" or not os.path.isfile(verdict_path):
        raise kernel.ClaimError(f"gate failed: {outcome.get('stderr', outcome['status'])}")
    sealed = kernel.seal(root)
    if component:
        source = os.path.realpath(component["claim"])
        checked = kernel.verify(source)
        if not checked["ok"]:
            raise kernel.ClaimError("component identity mismatch")
        links = [{"input": p, "component": component["name"],
                  "root": checked["root"], "output": p} for p in sorted(component_outputs)]
        sealed = registry.seal_with(root, components=links)
        transfer._copy_claim(source, os.path.join(root, kernel.STORE, "sealed", component["name"]),
                             generated=True, residue=False)
    if by:
        kernel.ledger(root, {"event": "producer", "model": by})
    return {"ok": True, **sealed}
