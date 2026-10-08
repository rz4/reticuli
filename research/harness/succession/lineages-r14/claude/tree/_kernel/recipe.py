"""Parsing a claim's recipe (`spec/claim-format.md`).

`load_recipe` reads `reticuli.toml` (or the legacy `claim.toml`), parses it
as TOML, and validates it against the v1-carried rules: a string `name`, a
known `kind` and an `output` on every step, a `run` on every gate, every
declared path confined to the claim directory, and a `format` this kernel
understands. Anything else -- bad syntax, a hostile path, an unreadable
format -- refuses in band as a `ClaimError`, never a raw traceback, because
the recipe is untrusted input.
"""
import os
import tomllib

from . import core
from .core import ClaimError

_HEXDIGITS = frozenset("0123456789abcdef")


def recipe_path(d: str) -> str:
    """The path to `d`'s recipe file, preferring the canonical name."""
    primary = os.path.join(d, core.RECIPE)
    if os.path.isfile(primary):
        return primary
    legacy = os.path.join(d, core.LEGACY_RECIPE)
    if os.path.isfile(legacy):
        return legacy
    raise ClaimError(
        f"no recipe found in {d!r} (expected {core.RECIPE} or {core.LEGACY_RECIPE})"
    )


def load_recipe(d: str) -> dict:
    """Parse and validate `d`'s recipe; raise ClaimError on anything wrong."""
    path = recipe_path(d)
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as e:
        raise ClaimError(f"cannot read recipe {path!r}: {e}") from e

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ClaimError(f"recipe {path!r} is not valid UTF-8: {e}") from e

    try:
        doc = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise ClaimError(f"malformed recipe {path!r}: {e}") from e

    claim = doc.get("claim")
    if not isinstance(claim, dict):
        raise ClaimError(f"recipe {path!r} is missing a [claim] table")

    name = claim.get("name")
    if not isinstance(name, str):
        raise ClaimError("[claim] name is required and must be a string")

    fmt = claim.get("format", 1)
    if isinstance(fmt, bool) or not isinstance(fmt, int) or fmt < 1:
        raise ClaimError("[claim] format must be a positive integer")
    if fmt > core.FORMAT:
        raise ClaimError(
            f"claim format {fmt} is newer than this kernel understands "
            f"(format {core.FORMAT}); upgrade reticuli to read it"
        )

    inputs = claim.get("inputs")
    if inputs is not None:
        if not isinstance(inputs, list) or not all(isinstance(p, str) for p in inputs):
            raise ClaimError("[claim] inputs must be a list of strings")
        for p in inputs:
            core._safe(d, p)

    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        if not isinstance(manifest, str):
            raise ClaimError("[claim] inputs_manifest must be a string")
        core._safe(d, manifest)

    steps = doc.get("step", [])
    if not isinstance(steps, list):
        raise ClaimError(f"recipe {path!r}: [[step]] must be an array of tables")

    for step in steps:
        if not isinstance(step, dict):
            raise ClaimError(f"recipe {path!r}: each step must be a table")

        kind = step.get("kind")
        if kind not in core.KINDS:
            raise ClaimError(
                f"recipe {path!r}: step kind must be one of "
                f"{sorted(core.KINDS)}, got {kind!r}"
            )

        output = step.get("output")
        if not isinstance(output, str) or not output:
            raise ClaimError(f"recipe {path!r}: every step needs an 'output'")
        core._safe(d, output)

        if kind == "gate":
            run = step.get("run")
            if not isinstance(run, str) or not run:
                raise ClaimError(f"recipe {path!r}: a gate step needs a 'run' command")

        source = step.get("from")
        if source is not None:
            if not isinstance(source, str) or not source:
                raise ClaimError(f"recipe {path!r}: a step's 'from' must be a string")
            core._safe(d, source)

    return doc


def _steps(parsed: dict) -> list:
    """Every step, in the order the recipe file lists them."""
    return parsed.get("step", [])


def gates(parsed: dict) -> list:
    """The `gate` steps, in recipe order."""
    return [s for s in _steps(parsed) if s.get("kind") == "gate"]


def produces(parsed: dict) -> list:
    """The `produce` steps, in recipe order."""
    return [s for s in _steps(parsed) if s.get("kind") == "produce"]


def generated_outputs(parsed: dict) -> list:
    """Outputs of `produce` steps whose class is (or defaults to) `generated`."""
    return [s["output"] for s in produces(parsed) if s.get("class", "generated") == "generated"]


def _read_input_manifest(d: str, manifest_name: str) -> list:
    """Parse an `inputs_manifest` file: one path per line, optionally
    `<sha256>  <path>`; blank lines and `#` comments are ignored."""
    path = core._safe(d, manifest_name)
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError as e:
        raise ClaimError(f"cannot read inputs manifest {manifest_name!r}: {e}") from e

    paths = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        head, _, rest = line.partition(" ")
        if len(head) == 64 and rest.strip() and all(c in _HEXDIGITS for c in head.lower()):
            entry = rest.strip()
        else:
            entry = line
        paths.append(entry)
    return paths


def _inputs(d: str, parsed: dict) -> list:
    """Every pinned input path the recipe declares, `inputs` and
    `inputs_manifest` combined."""
    claim = parsed.get("claim", {})
    result = list(claim.get("inputs") or [])

    manifest = claim.get("inputs_manifest")
    if manifest:
        result.extend(_read_input_manifest(d, manifest))

    for p in result:
        core._safe(d, p)
    return result
