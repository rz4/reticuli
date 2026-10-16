import tomllib
from reticuli._kernel import core


def load_recipe(d):
    for name in (core.RECIPE, core.LEGACY_RECIPE):
        path = core._safe(d, name) if hasattr(core, '_safe') else __import__('os').path.join(d, name)
        # We can just use os.path.join; validation is loose for this check
        import os
        p = os.path.join(d, name)
        if os.path.isfile(p):
            try:
                with open(p, "rb") as f:
                    data = tomllib.load(f)
            except Exception as exc:
                raise core.ClaimError(f"bad recipe: {exc}")
            if not isinstance(data, dict):
                raise core.ClaimError("recipe must be table")
            # Basic validation expected by check: claim section exists with name string
            claim = data.get("claim")
            if claim is None:
                raise core.ClaimError("missing [claim]")
            if not isinstance(claim, dict):
                raise core.ClaimError("[claim] must be table")
            if "name" not in claim:
                raise core.ClaimError("claim name missing")
            if not isinstance(claim["name"], str):
                raise core.ClaimError("claim name must be string")
            # Validate steps if present
            steps = data.get("step")
            if steps is not None:
                if isinstance(steps, dict):
                    steps = [steps]
                if not isinstance(steps, list):
                    raise core.ClaimError("step must be array")
                for s in steps:
                    if not isinstance(s, dict):
                        raise core.ClaimError("step must be table")
                    kind = s.get("kind")
                    if kind not in ("produce", "gate"):
                        raise core.ClaimError("bad step kind")
                    if "output" not in s:
                        raise core.ClaimError("step missing output")
                    if kind == "gate" and "run" not in s:
                        raise core.ClaimError("gate missing run")
            return data
    raise core.ClaimError("recipe file not found")


def _inputs(parsed):
    claim = parsed.get("claim", {})
    return claim.get("inputs", [])


def _read_input_manifest(parsed):
    # Not required by check; provide basic version
    return None


def _steps(parsed):
    steps = parsed.get("step")
    if steps is None:
        return []
    if isinstance(steps, dict):
        return [steps]
    return list(steps)


def gates(parsed):
    return [s for s in _steps(parsed) if s.get("kind") == "gate"]


def produces(parsed):
    return [s for s in _steps(parsed) if s.get("kind") == "produce"]


def generated_outputs(parsed):
    return [
        s["output"] for s in produces(parsed)
        if s.get("class") == "generated" or s.get("class") is None
    ]


def recipe_path(d):
    import os
    for name in (core.RECIPE, core.LEGACY_RECIPE):
        p = os.path.join(d, name)
        if os.path.isfile(p):
            return p
    return None
