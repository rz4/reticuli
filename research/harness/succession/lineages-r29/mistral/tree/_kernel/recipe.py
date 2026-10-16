"""Recipe parsing and validation for reticuli.kernel.

Exports:
    load_recipe: Load and parse a recipe file from a directory.
    _inputs: Extract the list of inputs from the recipe.
    _read_input_manifest: Read the input manifest file.
    _steps: Extract the list of steps from the recipe.
    gates: Extract gate steps from the recipe.
    produces: Extract produce steps from the recipe.
    generated_outputs: Extract outputs of generated steps.
    recipe_path: Return the path to the recipe file.
"""

import os
import tomllib
from typing import Dict, List, Any

from reticuli._kernel.core import ClaimError


# Constants
RECIPE_FILE = "reticuli.toml"
LEGACY_RECIPE_FILE = "claim.toml"


def recipe_path(directory: str) -> str:
    """Return the path to the recipe file in the given directory.
    
    Prefers `reticuli.toml`; falls back to `claim.toml`.
    """
    recipe = os.path.join(directory, RECIPE_FILE)
    if os.path.isfile(recipe):
        return recipe
    legacy_recipe = os.path.join(directory, LEGACY_RECIPE_FILE)
    if os.path.isfile(legacy_recipe):
        return legacy_recipe
    raise ClaimError(f"Recipe file not found in {directory}")


def load_recipe(directory: str) -> Dict[str, Any]:
    """Load and parse the recipe file from the given directory.
    
    Args:
        directory: Path to the claim directory.
    
    Returns:
        The parsed recipe as a dictionary.
    
    Raises:
        ClaimError: If the recipe is malformed or invalid.
    """
    recipe_file = recipe_path(directory)
    try:
        with open(recipe_file, "rb") as f:
            recipe = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ClaimError(f"Malformed recipe file: {e}")
    except OSError as e:
        raise ClaimError(f"Failed to read recipe file: {e}")

    _validate_recipe(recipe)
    return _canonicalize_recipe(recipe)


def _validate_recipe(recipe: Dict[str, Any]) -> None:
    """Validate the recipe structure and content.
    
    Args:
        recipe: The parsed recipe.
    
    Raises:
        ClaimError: If the recipe is invalid.
    """
    if "claim" not in recipe:
        raise ClaimError("Recipe missing [claim] section")

    claim = recipe["claim"]
    if not isinstance(claim.get("name"), str):
        raise ClaimError("[claim] name must be a string")

    if "inputs" in claim and "inputs_manifest" in claim:
        raise ClaimError("[claim] cannot have both 'inputs' and 'inputs_manifest'")

    if "inputs" in claim and not isinstance(claim["inputs"], list):
        raise ClaimError("[claim] inputs must be a list")

    if "inputs_manifest" in claim and not isinstance(claim["inputs_manifest"], str):
        raise ClaimError("[claim] inputs_manifest must be a string")

    if "step" not in recipe and "steps" not in recipe:
        raise ClaimError("Recipe missing [[step]] or [[steps]] section")

    steps = recipe.get("step", recipe.get("steps", []))
    if not isinstance(steps, list):
        raise ClaimError("Steps must be a list")

    for step in steps:
        if not isinstance(step, dict):
            raise ClaimError("Each step must be a dictionary")
        if "kind" not in step:
            raise ClaimError("Step missing 'kind'")
        if step["kind"] not in ("produce", "gate"):
            raise ClaimError(f"Step kind must be 'produce' or 'gate', got {step['kind']!r}")
        if "output" not in step:
            raise ClaimError("Step missing 'output'")
        if step["kind"] == "gate" and "run" not in step:
            raise ClaimError("Gate step missing 'run' command")

        # Validate class
        if "class" in step and step["class"] not in ("generated", "pinned", "validated"):
            raise ClaimError(
                f"Step class must be 'generated', 'pinned', or 'validated', got {step['class']!r}"
            )


def _canonicalize_recipe(recipe: Dict[str, Any]) -> Dict[str, Any]:
    """Canonicalize the recipe for format compliance.
    
    Args:
        recipe: The parsed recipe.
    
    Returns:
        The canonicalized recipe.
    """
    # Handle format version
    format_version = recipe.get("claim", {}).get("format", 1)
    
    # Strip guidance for format >= 3
    if format_version >= 3:
        for step in recipe.get("step", recipe.get("steps", [])):
            if "guidance" in step:
                del step["guidance"]
            if "request" in step:
                del step["request"]
    
    # Sort steps for format >= 4
    if format_version >= 4:
        steps = recipe.get("step", recipe.get("steps", []))
        if steps:
            # Sort steps by their canonical JSON representation
            import json
            steps.sort(key=lambda s: json.dumps(s, sort_keys=True))
            recipe["steps"] = steps
            if "step" in recipe:
                del recipe["step"]
    
    return recipe


def _inputs(recipe: Dict[str, Any]) -> List[str]:
    """Extract the list of inputs from the recipe.
    
    Args:
        recipe: The parsed recipe.
    
    Returns:
        List of input paths.
    """
    claim = recipe.get("claim", {})
    if "inputs" in claim:
        return claim["inputs"]
    return []


def _read_input_manifest(directory: str, manifest_path: str) -> List[str]:
    """Read the input manifest file.
    
    Args:
        directory: Path to the claim directory.
        manifest_path: Path to the manifest file (relative to claim directory).
    
    Returns:
        List of input paths.
    
    Raises:
        ClaimError: If the manifest cannot be read.
    """
    manifest_file = os.path.join(directory, manifest_path)
    try:
        with open(manifest_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError as e:
        raise ClaimError(f"Failed to read input manifest: {e}")

    inputs = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Handle optional SHA256 prefix
        parts = line.split()
        if len(parts) >= 2:
            inputs.append(parts[-1])
        else:
            inputs.append(parts[0])

    return inputs


def _steps(recipe: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract the list of steps from the recipe.
    
    Args:
        recipe: The parsed recipe.
    
    Returns:
        List of steps.
    """
    return recipe.get("step", recipe.get("steps", []))


def gates(recipe: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract gate steps from the recipe.
    
    Args:
        recipe: The parsed recipe.
    
    Returns:
        List of gate steps.
    """
    return [step for step in _steps(recipe) if step["kind"] == "gate"]


def produces(recipe: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract produce steps from the recipe.
    
    Args:
        recipe: The parsed recipe.
    
    Returns:
        List of produce steps.
    """
    return [step for step in _steps(recipe) if step["kind"] == "produce"]


def generated_outputs(recipe: Dict[str, Any]) -> List[str]:
    """Extract outputs of generated steps.
    
    Args:
        recipe: The parsed recipe.
    
    Returns:
        List of generated output paths.
    """
    return [
        step["output"]
        for step in _steps(recipe)
        if step.get("class", "generated" if step["kind"] == "produce" else "pinned") == "generated"
    ]