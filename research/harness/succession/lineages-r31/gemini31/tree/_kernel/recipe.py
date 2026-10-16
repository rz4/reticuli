import tomllib
from typing import Any, Dict, List
import os
from . import core

def load_recipe(path: str) -> Dict[str, Any]:
    for name in [core.RECIPE, core.LEGACY_RECIPE]:
        p = os.path.join(path, name)
        if os.path.exists(p):
            try:
                with open(p, "rb") as f:
                    data = tomllib.load(f)
            except Exception as e:
                raise core.ClaimError(f"malformed recipe: {e}")
            
            # validation
            if not isinstance(data.get("claim", {}).get("name"), str):
                raise core.ClaimError("name must be string")
            
            for step in data.get("step", []):
                if step.get("kind") not in core.KINDS:
                    raise core.ClaimError(f"invalid kind: {step.get('kind')}")
                if not step.get("output"):
                    raise core.ClaimError("missing output")
                if step.get("kind") == "gate" and not step.get("run"):
                    raise core.ClaimError("gate needs run")
            return data
    raise core.ClaimError("no recipe found")

def recipe_path(path: str) -> str:
    for name in [core.RECIPE, core.LEGACY_RECIPE]:
        p = os.path.join(path, name)
        if os.path.exists(p):
            return p
    raise core.ClaimError("no recipe found")

def _steps(parsed: Dict[str, Any]) -> List[Dict[str, Any]]:
    return parsed.get("step", [])

def gates(parsed: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [s for s in _steps(parsed) if s.get("kind") == "gate"]

def produces(parsed: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [s for s in _steps(parsed) if s.get("kind") == "produce"]

def generated_outputs(parsed: Dict[str, Any]) -> List[str]:
    # v2 step classes: 'generated' means implementation. 
    # v1 'free' means the same.
    # The default for produce is 'generated' (or 'free' in v1).
    outs = []
    for s in _steps(parsed):
        cls = s.get("class", "")
        # The spec says: "A produce step defaults to `class = "generated"`; any other step output defaults to `class = "pinned"`."
        if cls in ("generated", "free"):
            outs.append(s["output"])
        elif not cls and s.get("kind") == "produce":
            outs.append(s["output"])
    return outs

def _read_input_manifest(base: str, path: str) -> List[str]:
    p = core._safe(base, path)
    if not os.path.exists(p):
        raise core.ClaimError(f"missing input manifest {path}")
    inputs = []
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) == 2:
                inputs.append(parts[1])
            else:
                inputs.append(line)
    return inputs

def _inputs(base: str, parsed: Dict[str, Any]) -> List[str]:
    claim = parsed.get("claim", {})
    manifest = claim.get("inputs_manifest")
    if manifest:
        return _read_input_manifest(base, manifest)
    return claim.get("inputs", [])
