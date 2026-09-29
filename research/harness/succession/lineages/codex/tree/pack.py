"""Pack a project as a claim over its checks and generated implementation."""

from __future__ import annotations

import glob
import os
from pathlib import Path

from . import kernel, render
from ._util import safe_path


def _expand(root, patterns):
    paths = []
    for pattern in patterns:
        safe_path(root, pattern)
        for path in sorted(glob.glob(os.path.join(root, pattern), recursive=True)):
            if os.path.isfile(path):
                name = os.path.relpath(path, root)
                safe_path(root, name)
                if name not in paths:
                    paths.append(name)
    return paths


def pack(root, name, generated, inputs, gate, output):
    products = _expand(root, generated)
    pins = _expand(root, inputs)
    products = [path for path in products if path not in pins and path != output]
    data = {"claim": {"name": name, "inputs": sorted(pins)},
            "step": [{"kind": "produce", "output": path, "class": "generated"} for path in sorted(products)]}
    data["step"].append({"kind": "gate", "output": output, "class": "validated", "run": gate})
    if kernel.vacuous_gates(data):
        raise kernel.ClaimError("vacuous gate: every decider is generated")
    result = kernel.run_gate(gate, root, data)
    if result["status"] != "ok" or not os.path.isfile(safe_path(root, output)):
        raise kernel.ClaimError(f"gate {output} failed: {result['stderr'][-200:]}")
    Path(root, kernel.RECIPE).write_text(render.dump_recipe(data), encoding="utf-8")
    manifest = kernel.seal(root)
    return {"ok": True, "root": manifest["root"], "path": root}
