import os
import tomllib

from reticuli._kernel import core

def recipe_path(room: str) -> str:
    candidates = [core.RECIPE, core.LEGACY_RECIPE]
    for name in candidates:
        path = os.path.join(room, name)
        if os.path.isfile(path):
            return path
    raise core.ClaimError("no recipe (neither reticuli.toml nor claim.toml found)")

def load_recipe(room: str) -> dict:
    path = recipe_path(room)
    with open(path, "rb") as f:
        try:
            parsed = tomllib.load(f)
        except tomllib.TOMLDecodeError:
            raise core.ClaimError("malformed recipe") from None

    claim = parsed.get("claim")
    if not isinstance(claim, dict):
        raise core.ClaimError("missing or invalid [claim] section")
    name = claim.get("name")
    if not isinstance(name, str):
        raise core.ClaimError("[claim] name must be a non-empty string")
    if not name:
        raise core.ClaimError("[claim] name must be a non-empty string")

    _steps(parsed)  # validate all steps

    return parsed

def _steps(parsed: dict) -> list[dict]:
    steps = parsed.get("step", [])
    if not isinstance(steps, list):
        raise core.ClaimError("[step] must be an array of tables")

    validated_steps = []
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            raise core.ClaimError(f"step[{i}] must be a table")

        kind = step.get("kind")
        if not isinstance(kind, str) or kind not in core.KINDS:
            raise core.ClaimError(f"invalid kind in step[{i}]: {kind!r}")

        output = step.get("output")
        if not isinstance(output, str) or not output:
            raise core.ClaimError(f"missing or invalid output in step[{i}]: {output!r}")

        if kind == "gate":
            run_cmd = step.get("run")
            if not isinstance(run_cmd, str):
                raise core.ClaimError(f"gate step[{i}] missing 'run' command")

        validated_steps.append(step)

    return validated_steps

def gates(parsed: dict) -> list[dict]:
    return [step for step in _steps(parsed) if step["kind"] == "gate"]

def produces(parsed: dict) -> list[dict]:
    return [step for step in _steps(parsed) if step["kind"] == "produce"]

def generated_outputs(parsed: dict) -> list[str]:
    return [step["output"] for step in produces(parsed) if step.get("class") == "generated"]

def _inputs(room: str, parsed: dict) -> list[str]:
    claim = parsed.get("claim", {})
    inp_manifest = claim.get("inputs_manifest")
    if inp_manifest:
        if not isinstance(inp_manifest, str):
            raise core.ClaimError("inputs_manifest must be string")
        return _read_input_manifest(room, inp_manifest)
    inputs = claim.get("inputs", [])
    if not isinstance(inputs, list):
        raise core.ClaimError("inputs must be array")
    return [str(inp) for inp in inputs]

def _read_input_manifest(room: str, mani_path: str) -> list[str]:
    path = core._safe(room, mani_path)
    inputs = []
    with open(path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.rstrip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(None, 1)
            ipath = parts[0] if len(parts) == 1 else parts[1]
            inputs.append(ipath)
    return inputs