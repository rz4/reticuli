"""Recipe parsing: reads a claim's untrusted recipe file into a plain dict.

`load_recipe` finds the recipe under either name (`reticuli.toml`,
preferred, or the legacy `claim.toml`), parses it, and validates it against
the rules of `spec/claim-format.md`. Every refusal -- bad TOML, an unknown
step kind, a path that escapes the claim -- surfaces as a `ClaimError`, never
a raw traceback, because the claim's own recipe is untrusted input.
"""
import os
import tomllib

from reticuli._kernel import core

STEP_CLASSES = frozenset({"generated", "pinned", "validated"})


def recipe_path(d: str) -> str:
    """The on-disk path of `d`'s recipe, preferring the canonical name."""
    for name in (core.RECIPE, core.LEGACY_RECIPE):
        p = os.path.join(d, name)
        if os.path.isfile(p):
            return p
    raise core.ClaimError(
        f"no recipe found in {d!r} ({core.RECIPE} or {core.LEGACY_RECIPE})"
    )


def load_recipe(d: str) -> dict:
    """Parse and validate `d`'s recipe; refusals are `ClaimError`, never crashes."""
    path = recipe_path(d)
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as e:
        raise core.ClaimError(f"cannot read recipe {path!r}: {e}") from e
    try:
        parsed = tomllib.loads(raw.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
        raise core.ClaimError(f"malformed recipe {path!r}: {e}") from e
    _validate(d, parsed)
    return parsed


def _validate(d: str, parsed: dict) -> None:
    if not isinstance(parsed, dict):
        raise core.ClaimError("malformed recipe: not a table")

    claim = parsed.get("claim")
    if not isinstance(claim, dict):
        raise core.ClaimError("malformed recipe: missing [claim] table")
    name = claim.get("name")
    if not isinstance(name, str):
        raise core.ClaimError("malformed recipe: [claim] name is required and must be a string")

    fmt = claim.get("format", 1)
    if not isinstance(fmt, int) or isinstance(fmt, bool) or fmt < 1:
        raise core.ClaimError("malformed recipe: [claim] format must be a positive integer")
    if fmt > core.FORMAT:
        raise core.ClaimError(
            f"claim format {fmt} is newer than this kernel understands "
            f"(format {core.FORMAT}); upgrade reticuli to read it"
        )

    for path in claim.get("inputs", []) or []:
        core._safe(d, path)
    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        core._safe(d, manifest)
    environment = claim.get("environment")
    if environment is not None:
        core._safe(d, environment)

    steps = parsed.get("step", [])
    if not isinstance(steps, list):
        raise core.ClaimError("malformed recipe: [[step]] must be an array of tables")
    for step in steps:
        _validate_step(d, step)


def _validate_step(d: str, step) -> None:
    if not isinstance(step, dict):
        raise core.ClaimError("malformed recipe: a step must be a table")
    kind = step.get("kind")
    if kind not in core.KINDS:
        raise core.ClaimError(f"malformed recipe: unknown step kind {kind!r}")
    output = step.get("output")
    if not isinstance(output, str) or output == "":
        raise core.ClaimError("malformed recipe: a step needs a string output")
    core._safe(d, output)
    cls = step.get("class")
    if cls is not None and cls not in STEP_CLASSES:
        raise core.ClaimError(f"malformed recipe: unknown step class {cls!r}")
    if kind == "gate" and not isinstance(step.get("run"), str):
        raise core.ClaimError("malformed recipe: a gate step needs a string run")


def _steps(parsed: dict) -> list:
    """Every step, in recipe order."""
    return parsed.get("step", [])


def gates(parsed: dict) -> list:
    """The gate steps, in recipe order."""
    return [s for s in _steps(parsed) if s.get("kind") == "gate"]


def produces(parsed: dict) -> list:
    """The produce steps, in recipe order."""
    return [s for s in _steps(parsed) if s.get("kind") == "produce"]


def generated_outputs(parsed: dict) -> list:
    """The outputs of every produce step whose class is `generated` (the default)."""
    return [p["output"] for p in produces(parsed) if p.get("class", "generated") == "generated"]


def _read_input_manifest(path: str) -> list:
    """Parse a format-2 `inputs_manifest` file: one path per line, each
    optionally prefixed `<sha256>  <path>`; blank lines and `#` comments
    are ignored (`spec/claim-format.md`)."""
    paths = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            head, _, tail = line.partition(" ")
            if len(head) == 64 and tail.strip() and all(c in "0123456789abcdef" for c in head):
                paths.append(tail.strip())
            else:
                paths.append(line)
    return paths


def _inputs(d: str, parsed: dict) -> list:
    """Every pinned input path the recipe declares: the `inputs` list, the
    `inputs_manifest` file itself plus the paths it names, and the
    `environment` file -- each is a pinned input (`spec/claim-format.md`)."""
    claim = parsed.get("claim", {})
    paths = list(claim.get("inputs", []) or [])
    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        paths.append(manifest)
        paths.extend(_read_input_manifest(core._safe(d, manifest)))
    environment = claim.get("environment")
    if environment is not None:
        paths.append(environment)
    return paths
