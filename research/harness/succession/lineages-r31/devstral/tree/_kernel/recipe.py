"""Kernel recipe module for parsing and validating claim recipes."""
import os
from typing import Dict, Any, List

from reticuli._kernel import core


def _recipe_path(directory: str) -> str:
    """Determine the path to the recipe file in the given directory."""
    for name in (core.RECIPE, core.LEGACY_RECIPE):
        path = os.path.join(directory, name)
        if os.path.isfile(path):
            return path
    raise core.ClaimError("No recipe file found (reticuli.toml or claim.toml)")


def recipe_path(directory: str) -> str:
    """Public API: Determine the path to the recipe file in the given directory."""
    return _recipe_path(directory)


def _inputs(recipe: Dict[str, Any]) -> List[str]:
    """Extract the list of input files from the recipe."""
    return recipe.get("claim", {}).get("inputs", [])


def _read_input_manifest(manifest_path: str) -> List[str]:
    """Read the input manifest file and return the list of input files."""
    with open(manifest_path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip() and not line.startswith("#")]


def _steps(recipe: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract the list of steps from the recipe."""
    return recipe.get("step", [])


def gates(recipe: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract the gate steps from the recipe."""
    return [step for step in _steps(recipe) if step.get("kind") == "gate"]


def produces(recipe: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract the produce steps from the recipe."""
    return [step for step in _steps(recipe) if step.get("kind") == "produce"]


def generated_outputs(recipe: Dict[str, Any]) -> List[str]:
    """Extract the list of generated output files from the recipe."""
    return [
        step.get("output")
        for step in _steps(recipe)
        if step.get("class") == "generated"
    ]


def load_recipe(directory: str) -> Dict[str, Any]:
    """Load and parse the recipe file in the given directory."""
    recipe_path = _recipe_path(directory)
    
    # Read the recipe file directly and parse it
    with open(recipe_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    recipe = {"step": []}
    current_section = None
    current_step = None
    
    for line in content.split('\n'):
        line = line.strip()
        
        # Skip empty lines and comments
        if not line or line.startswith('#'):
            continue
            
        # Handle sections
        if line.startswith('[') and line.endswith(']'):
            # Check if it's an array-style section like [[step]]
            if line.startswith('[[') and line.endswith(']]'):
                section_name = line[2:-2]
                if section_name == "step":
                    current_step = {}
                    recipe["step"].append(current_step)
                current_section = None
            else:
                # Regular sections like [claim]
                section_name = line[1:-1]
                current_section = section_name
                if current_section not in recipe:
                    recipe[current_section] = {}
                current_step = None
            continue
        
        # Parse key-value pairs
        if '=' in line:
            key, value = line.split('=', 1)
            key = key.strip()
            value = value.strip()
            
            # Remove quotes if present
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1]
            
            # Parse arrays
            if value.startswith('[') and value.endswith(']'):
                value = [v.strip().strip('"') for v in value[1:-1].split(',') if v.strip()]
            
            # Parse numbers only if the value is not a list
            if not isinstance(value, list):
                if value.replace('.', '').isdigit():
                    if '.' in value:
                        value = float(value)
                    else:
                        value = int(value)
            
            if current_step is not None:
                current_step[key] = value
            elif current_section:
                recipe[current_section][key] = value
            else:
                recipe[key] = value
    
    # Validate the recipe
    if "claim" not in recipe or "name" not in recipe["claim"]:
        raise core.ClaimError("Recipe must have a [claim] section with a 'name' field")

    steps = _steps(recipe)
    for step in steps:
        if "kind" not in step:
            raise core.ClaimError("Each step must have a 'kind' field")
        if step["kind"] not in {"produce", "gate"}:
            raise core.ClaimError(f"Step kind must be 'produce' or 'gate', got '{step['kind']}'")
        if "output" not in step:
            raise core.ClaimError("Each step must have an 'output' field")
        if step["kind"] == "gate" and "run" not in step:
            raise core.ClaimError("Gate steps must have a 'run' field")

    return recipe
