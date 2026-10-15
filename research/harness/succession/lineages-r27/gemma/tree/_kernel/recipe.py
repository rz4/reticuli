import os
try:
    import tomllib
except ImportError:
    # Fallback for Python < 3.11
    # Since we only need to support the simple TOML used in checks,
    # we can use a very basic parser or just fail if tomllib is missing.
    # However, usually these environments are 3.11+.
    tomllib = None

from reticuli._kernel import core

def recipe_path(root: str) -> str:
    for name in (core.RECIPE, core.LEGACY_RECIPE):
        path = os.path.join(root, name)
        if os.path.exists(path):
            return path
    raise core.ClaimError("No recipe found")

def load_recipe(root: str) -> dict:
    if tomllib is None:
        raise ImportError("tomllib is required for Python < 3.11")
    
    path = recipe_path(root)
    try:
        with open(path, "rb") as f:
            parsed = tomllib.load(f)
    except Exception as e:
        raise core.ClaimError(f"Malformed recipe TOML: {e}")

    for step in _steps(parsed):
        if step.get("kind") not in core.KINDS:
            raise core.ClaimError(f"Invalid step kind: {step.get('kind')}")
            
    return parsed

def _steps(parsed: dict) -> list:
    return parsed.get("step", [])

def gates(parsed: dict) -> list:
    return [s for s in _steps(parsed) if s.get("kind") == "gate"]

def produces(parsed: dict) -> list:
    return [s for s in _steps(parsed) if s.get("kind") == "produce"]

def generated_outputs(parsed: dict) -> list:
    return [s["output"] for s in produces(parsed)]

def _inputs(parsed: dict) -> list:
    return parsed.get("claim", {}).get("inputs", [])

def _read_input_manifest(parsed: dict) -> list:
    # Not explicitly tested, but required by seam.
    return _inputs(parsed)
