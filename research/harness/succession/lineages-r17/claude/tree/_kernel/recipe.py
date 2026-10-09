"""The recipe: parsing a claim's untrusted `reticuli.toml` (or `claim.toml`).

`load_recipe` finds the recipe file under either name, parses it, and
validates it against `spec/claim-format.md`'s rules -- a malformed or
hostile recipe refuses in band (`core.ClaimError`), never a raw traceback.
The parsed form is the dict the identity computation hashes (see
`spec/identity.md`): this module does not fill in class defaults on it,
so callers that read a step's effective class (`generated_outputs`) apply
the default themselves rather than mutate what gets serialized.

Stdlib only.
"""
import os
import re
import tomllib

from . import core
from .core import ClaimError

_HEXLINE = re.compile(r"^[0-9a-f]{64}\s+(\S.*)$")


def recipe_path(d: str) -> str:
    """The on-disk path of `d`'s recipe, preferring the canonical name."""
    for name in (core.RECIPE, core.LEGACY_RECIPE):
        path = os.path.join(d, name)
        if os.path.isfile(path):
            return path
    raise ClaimError(
        f"no recipe found: expected {core.RECIPE} (or legacy "
        f"{core.LEGACY_RECIPE}) in {d!r}")


def _default_class(step: dict) -> str:
    """A `produce` step defaults to `generated`; anything else to `pinned`."""
    return "generated" if step.get("kind") == "produce" else "pinned"


def _validate_step(d: str, step) -> None:
    if not isinstance(step, dict):
        raise ClaimError(f"a step must be a table, got {step!r}")
    kind = step.get("kind")
    if kind not in core.KINDS:
        raise ClaimError(f"step kind must be one of {sorted(core.KINDS)}, "
                          f"got {kind!r}")
    output = step.get("output")
    if not isinstance(output, str) or not output:
        raise ClaimError(f"step output must be a non-empty string, "
                          f"got {output!r}")
    core._safe(d, output)
    if kind == "gate":
        run = step.get("run")
        if not isinstance(run, str) or not run:
            raise ClaimError(f"gate step {output!r} needs a run command")
    cls = step.get("class")
    if cls is not None and not isinstance(cls, str):
        raise ClaimError(f"step {output!r} class must be a string, "
                          f"got {cls!r}")
    for key in ("guidance", "request", "from"):
        value = step.get(key)
        if value is not None and not isinstance(value, str):
            raise ClaimError(f"step {output!r} {key!r} must be a string")


def load_recipe(d: str) -> dict:
    """Parse and validate `d`'s recipe; refusals, not crashes."""
    path = recipe_path(d)
    try:
        with open(path, "rb") as f:
            doc = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ClaimError(f"malformed recipe {path!r}: {e}") from e

    claim = doc.get("claim")
    if not isinstance(claim, dict):
        raise ClaimError(f"recipe {path!r} needs a [claim] table")
    name = claim.get("name")
    if not isinstance(name, str):
        raise ClaimError(f"[claim] name must be a string, got {name!r}")

    fmt = claim.get("format", 1)
    if not isinstance(fmt, int) or isinstance(fmt, bool) or fmt < 1:
        raise ClaimError(f"[claim] format must be a positive integer, "
                          f"got {fmt!r}")
    if fmt > core.FORMAT:
        raise ClaimError(
            f"claim format {fmt} is newer than this kernel understands "
            f"(format {core.FORMAT}); upgrade reticuli to read it")

    inputs = claim.get("inputs")
    if inputs is not None:
        if not isinstance(inputs, list) or not all(
                isinstance(p, str) for p in inputs):
            raise ClaimError("[claim] inputs must be a list of strings")
        for p in inputs:
            core._safe(d, p)

    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        if not isinstance(manifest, str) or not manifest:
            raise ClaimError("[claim] inputs_manifest must be a string")
        core._safe(d, manifest)

    steps = doc.get("step", [])
    if not isinstance(steps, list):
        raise ClaimError("[[step]] must be an array of tables")
    for step in steps:
        _validate_step(d, step)

    return doc


def _steps(parsed: dict) -> list:
    """Every step, in the order they appear in the recipe."""
    return list(parsed.get("step", []))


def gates(parsed: dict) -> list:
    """The `gate` steps, in recipe order."""
    return [s for s in _steps(parsed) if s.get("kind") == "gate"]


def produces(parsed: dict) -> list:
    """The `produce` steps, in recipe order."""
    return [s for s in _steps(parsed) if s.get("kind") == "produce"]


def generated_outputs(parsed: dict) -> list:
    """Outputs of `produce` steps whose (possibly defaulted) class is generated."""
    return [s["output"] for s in produces(parsed)
            if s.get("class", _default_class(s)) == "generated"]


def _read_input_manifest(path: str) -> list:
    """Parse an `INPUTS` manifest: one path per line, blank/`#` lines ignored.

    A line may be bare (`<path>`) or carry its hash (`<sha256>  <path>`);
    either way, only the path is returned.
    """
    paths = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = _HEXLINE.match(line)
            paths.append(m.group(1) if m else line)
    return paths


def _inputs(d: str, parsed: dict) -> list:
    """The claim's pinned input paths, from `inputs` or `inputs_manifest`.

    When the inputs are named by a manifest, the manifest file itself is
    also a pinned input (`spec/claim-format.md`), so it is returned ahead
    of the paths it names.
    """
    claim = parsed.get("claim", {})
    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        return [manifest] + _read_input_manifest(core._safe(d, manifest))
    return list(claim.get("inputs", []))
