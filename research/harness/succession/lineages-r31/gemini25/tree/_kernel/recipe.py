\
import os
try:
    import tomllib
except ImportError:
    import tomli as tomllib


from reticuli._kernel import core

def recipe_path(claim_dir):
    """Returns the path to the recipe file, preferring reticuli.toml."""
    for name in (core.RECIPE, core.LEGACY_RECIPE):
        p = os.path.join(claim_dir, name)
        if os.path.isfile(p):
            return p
    raise core.ClaimError(f"no recipe file found in {claim_dir}")


def load_recipe(claim_dir):
    """Loads and validates the recipe from the claim directory."""
    path = recipe_path(claim_dir)
    try:
        with open(path, "rb") as f:
            doc = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise core.ClaimError(f"malformed recipe: {e}")
    except FileNotFoundError:
        raise core.ClaimError(f"recipe file not found: {path}")

    # Handle legacy record section name
    if "record" in doc and "claim" not in doc:
        doc["claim"] = doc.pop("record")

    if "claim" not in doc:
        raise core.ClaimError("recipe is missing [claim] section")
    
    claim = doc["claim"]
    if "name" not in claim:
        raise core.ClaimError("[claim] is missing 'name'")

    for step in doc.get("step", []):
        if "kind" not in step or step["kind"] not in core.KINDS:
            raise core.ClaimError(f"invalid step kind: {step.get('kind')}")
        if "output" not in step:
            raise core.ClaimError("step is missing 'output'")
        if step["kind"] == "gate" and "run" not in step:
            raise core.ClaimError("gate step is missing 'run'")

        # Validate paths. This will raise ClaimError on invalid paths.
        core._safe(claim_dir, step["output"])

    if "inputs" in claim:
        if not isinstance(claim["inputs"], list):
            raise core.ClaimError("'inputs' must be a list")
        for p in claim["inputs"]:
            if not isinstance(p, str):
                raise core.ClaimError("input path must be a string")
            core._safe(claim_dir, p)
            
    return doc


def _steps(parsed):
    """Returns the steps from a parsed recipe."""
    return parsed.get("step", [])


def gates(parsed):
    """Returns the gate steps from a parsed recipe."""
    return [s for s in _steps(parsed) if s["kind"] == "gate"]


def produces(parsed):
    """Returns the produce steps from a parsed recipe."""
    return [s for s in _steps(parsed) if s["kind"] == "produce"]


def generated_outputs(parsed):
    """Returns the outputs of generated files."""
    return [
        s["output"]
        for s in produces(parsed)
        if s.get("class") in ("generated", "free", None)
    ]

def _inputs(parsed):
    """Returns the inputs from a parsed recipe."""
    return parsed.get("claim", {}).get("inputs", [])


def _read_input_manifest(parsed, claim_dir):
    """Reads the input manifest file."""
    # Not required for this check.
    return []
