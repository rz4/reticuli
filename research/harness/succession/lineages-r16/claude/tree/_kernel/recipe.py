"""Recipe parsing: reading a claim's untrusted reticuli.toml / claim.toml.

`load_recipe` locates the recipe under either name (`reticuli.toml`,
preferred, or the legacy `claim.toml`), parses it, and validates its shape:
`[claim] name` is a required string, every step has a `kind` in
`core.KINDS` and a string `output`, and a gate step additionally needs a
string `run`. Malformed TOML and a step that fails validation both refuse
as a `ClaimError` -- the claim's own recipe is untrusted input, so neither
ever surfaces as a raw parse crash.

`_steps`/`gates`/`produces`/`generated_outputs` read the parsed document;
`_inputs`/`_read_input_manifest` resolve the claim's declared pinned inputs,
expanding an `inputs_manifest` file per `spec/claim-format.md`.
"""
import os
import tomllib

from .core import ClaimError, FORMAT, KINDS, LEGACY_RECIPE, RECIPE, _safe


def recipe_path(d: str) -> str:
    """The path to `d`'s recipe file, preferring the canonical name."""
    for name in (RECIPE, LEGACY_RECIPE):
        path = os.path.join(d, name)
        if os.path.isfile(path):
            return path
    raise ClaimError(f"no recipe ({RECIPE} or {LEGACY_RECIPE}) found in {d!r}")


def _validate(doc) -> None:
    if not isinstance(doc, dict):
        raise ClaimError("a recipe must be a table")
    claim = doc.get("claim")
    if not isinstance(claim, dict):
        raise ClaimError("a recipe needs a [claim] table")
    name = claim.get("name")
    if not isinstance(name, str):
        raise ClaimError("[claim] name is required and must be a string")

    fmt = claim.get("format", 1)
    if isinstance(fmt, bool) or not isinstance(fmt, int) or fmt < 1:
        raise ClaimError(f"[claim] format must be a positive integer: {fmt!r}")
    if fmt > FORMAT:
        raise ClaimError(
            f"claim format {fmt} is newer than this kernel understands "
            f"(format {FORMAT}); upgrade reticuli to read it"
        )

    steps = doc.get("step", [])
    if not isinstance(steps, list):
        raise ClaimError("[[step]] must be an array of tables")
    for step in steps:
        if not isinstance(step, dict):
            raise ClaimError("every step must be a table")
        if step.get("kind") not in KINDS:
            raise ClaimError(f"refused step kind: {step.get('kind')!r}")
        output = step.get("output")
        if not isinstance(output, str) or not output:
            raise ClaimError("every step needs a string 'output'")
        if step["kind"] == "gate" and not isinstance(step.get("run"), str):
            raise ClaimError("a gate step needs a string 'run'")


def load_recipe(d: str) -> dict:
    """Parse and validate `d`'s recipe; refusals, never a raw crash."""
    path = recipe_path(d)
    try:
        with open(path, "rb") as f:
            doc = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ClaimError(f"malformed recipe {path!r}: {e}") from e
    except OSError as e:
        raise ClaimError(f"cannot read recipe {path!r}: {e}") from e
    _validate(doc)
    return doc


def _steps(recipe: dict) -> list:
    """Every `[[step]]` entry, in file order."""
    return recipe.get("step", [])


def gates(recipe: dict) -> list:
    """The `kind = "gate"` steps, in file order."""
    return [s for s in _steps(recipe) if s["kind"] == "gate"]


def produces(recipe: dict) -> list:
    """The `kind = "produce"` steps, in file order."""
    return [s for s in _steps(recipe) if s["kind"] == "produce"]


def generated_outputs(recipe: dict) -> list:
    """Outputs of produce steps whose class is `generated` (the default)."""
    return [s["output"] for s in produces(recipe)
            if s.get("class", "generated") == "generated"]


def _read_input_manifest(path: str) -> list:
    """Paths named by a manifest file: one per line, `#` comments and
    blank lines ignored, an optional leading `<sha256>  ` stripped."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError as e:
        raise ClaimError(f"cannot read input manifest {path!r}: {e}") from e
    paths = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        head, _, rest = line.partition(" ")
        if len(head) == 64 and rest.strip() and all(
            c in "0123456789abcdef" for c in head
        ):
            paths.append(rest.strip())
        else:
            paths.append(line)
    return paths


def _inputs(recipe: dict, d: str) -> list:
    """The claim's declared pinned inputs: the explicit list, an expanded
    `inputs_manifest` (itself a pinned input), and the `environment` file,
    where declared."""
    claim = recipe.get("claim", {})
    inputs = list(claim.get("inputs", []))

    manifest_name = claim.get("inputs_manifest")
    if manifest_name:
        inputs.append(manifest_name)
        inputs.extend(_read_input_manifest(_safe(d, manifest_name)))

    environment = claim.get("environment")
    if environment:
        inputs.append(environment)

    return inputs
