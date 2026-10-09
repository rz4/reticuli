"""Recipe parsing: read a claim's `reticuli.toml` (or the legacy `claim.toml`)
into a validated, in-memory form the kernel and the layers above it can
query (`spec/claim-format.md`).

The recipe is untrusted input -- a claim's own authoring mistake, or a
hostile one. A malformed or disallowed recipe refuses in band as a
`ClaimError`, with a reason, never a raw parse crash.
"""
import os
import tomllib

from . import core
from .core import ClaimError


def recipe_path(d: str) -> str:
    """The recipe file inside claim directory `d`.

    `reticuli.toml` is preferred; the legacy `claim.toml` is read under its
    old name so a claim sealed before 2026-09-16 keeps its identity.
    """
    primary = core._safe(d, core.RECIPE)
    if os.path.isfile(primary):
        return primary
    legacy = core._safe(d, core.LEGACY_RECIPE)
    if os.path.isfile(legacy):
        return legacy
    raise ClaimError(
        f"no recipe in {d!r}: expected {core.RECIPE!r} or {core.LEGACY_RECIPE!r}"
    )


def load_recipe(d: str) -> dict:
    """Parse and validate the recipe in claim directory `d`."""
    path = recipe_path(d)
    try:
        with open(path, "rb") as f:
            doc = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ClaimError(f"malformed recipe {path!r}: {e}") from e
    except OSError as e:
        raise ClaimError(f"cannot read recipe {path!r}: {e}") from e

    try:
        _validate(d, doc)
    except ClaimError:
        raise
    except Exception as e:
        raise ClaimError(f"malformed recipe {path!r}: {e}") from e
    return doc


def _validate(d: str, doc) -> None:
    if not isinstance(doc, dict) or not isinstance(doc.get("claim"), dict):
        raise ClaimError("a recipe needs a [claim] table")
    claim = doc["claim"]

    name = claim.get("name")
    if not isinstance(name, str) or isinstance(name, bool):
        raise ClaimError("[claim] name is required and must be a string")

    fmt = claim.get("format", 1)
    if isinstance(fmt, bool) or not isinstance(fmt, int) or fmt < 1:
        raise ClaimError("[claim] format must be a positive integer")
    if fmt > core.FORMAT:
        raise ClaimError(
            f"claim format {fmt} is newer than this kernel understands "
            f"(format {core.FORMAT}); upgrade reticuli to read it"
        )

    inputs = claim.get("inputs", [])
    if not isinstance(inputs, list) or not all(isinstance(p, str) for p in inputs):
        raise ClaimError("[claim] inputs must be a list of strings")
    for p in inputs:
        core._safe(d, p)

    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        if not isinstance(manifest, str):
            raise ClaimError("[claim] inputs_manifest must be a string")
        core._safe(d, manifest)

    environment = claim.get("environment")
    if environment is not None:
        if not isinstance(environment, str):
            raise ClaimError("[claim] environment must be a string")
        core._safe(d, environment)

    steps = doc.get("step", [])
    if not isinstance(steps, list):
        raise ClaimError("[[step]] must be an array of tables")
    for step in steps:
        if not isinstance(step, dict):
            raise ClaimError("each step must be a table")
        kind = step.get("kind")
        if kind not in core.KINDS:
            raise ClaimError(
                f"step kind must be one of {sorted(core.KINDS)}, got {kind!r}"
            )
        output = step.get("output")
        if not isinstance(output, str) or not output:
            raise ClaimError(f"a {kind!r} step needs a string output")
        core._safe(d, output)
        if kind == "gate":
            run = step.get("run")
            if not isinstance(run, str) or not run:
                raise ClaimError("a gate step needs a string 'run' command")


def _steps(parsed: dict) -> list:
    """Every step, in the order the recipe text declares them."""
    return parsed.get("step", [])


def gates(parsed: dict) -> list:
    """The gate steps: a claim's pinned verdicts."""
    return [s for s in _steps(parsed) if s["kind"] == "gate"]


def produces(parsed: dict) -> list:
    """The produce steps: a claim's implementation obligations."""
    return [s for s in _steps(parsed) if s["kind"] == "produce"]


def generated_outputs(parsed: dict) -> list:
    """Outputs of produce steps whose class is regrowable (not pinned)."""
    return [
        s["output"] for s in produces(parsed)
        if s.get("class", "generated") in ("generated", "free")
    ]


def _read_input_manifest(path: str) -> list:
    """Parse an `inputs_manifest` file: one path per line.

    Blank lines and `#` comments are ignored. A line may be a bare path, or
    `<sha256>  <path>` so the manifest is meaningful on its own
    (`spec/claim-format.md`).
    """
    paths = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            head, _, rest = line.partition(" ")
            if len(head) == 64 and rest.strip() and all(c in "0123456789abcdef" for c in head):
                paths.append(rest.strip())
            else:
                paths.append(line)
    return paths


def _inputs(d: str, parsed: dict) -> list:
    """Every pinned input path the recipe declares, inline list plus manifest."""
    claim = parsed.get("claim", {})
    inputs = list(claim.get("inputs", []))
    manifest = claim.get("inputs_manifest")
    if manifest:
        inputs.extend(_read_input_manifest(core._safe(d, manifest)))
    return inputs
