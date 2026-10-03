"""The recipe: parsing a claim's own untrusted `reticuli.toml`.

`load_recipe` finds the recipe under either filename (`reticuli.toml`,
preferred, or the legacy `claim.toml`), parses it, and validates it against
the rules in `spec/claim-format.md`: a `[claim] name`, every step a `kind` in
`core.KINDS` and an `output`, every gate a `run`, and every declared path
confined to the claim directory (`core._safe`). Anything wrong with the
bytes — bad TOML, a missing field, an unknown step kind, an escaping path —
is refused in band as a `ClaimError`, never a raw parse crash: the claim's
own recipe is untrusted input.

`_steps`, `gates`, `produces`, and `generated_outputs` read the parsed
recipe; `_inputs` and `_read_input_manifest` resolve the claim's declared
pinned inputs, expanding a format-2 `inputs_manifest` into its listed paths.
"""
import os
import tomllib

from . import core
from .core import ClaimError


def recipe_path(d: str) -> str:
    """The recipe file under `d`, preferring `core.RECIPE` over the legacy
    name (spec/claim-format.md: a reader accepts either, preferring the
    new one, because the filename is not in the root preimage).
    """
    primary = os.path.join(d, core.RECIPE)
    if os.path.isfile(primary):
        return primary
    legacy = os.path.join(d, core.LEGACY_RECIPE)
    if os.path.isfile(legacy):
        return legacy
    raise ClaimError(
        f"no recipe ({core.RECIPE} or {core.LEGACY_RECIPE}) found in {d!r}"
    )


def _read_input_manifest(d: str, path: str) -> list:
    """Parse a format-2 inputs manifest: one path per line, optionally
    `<sha256>  <path>`; blank lines and `#` comments are ignored
    (spec/claim-format.md, "Large corpora: inputs_manifest").
    """
    full = core._safe(d, path)
    try:
        with open(full, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError as exc:
        raise ClaimError(f"cannot read inputs manifest {path!r}: {exc}") from exc

    names = []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if (
            len(parts) == 2
            and len(parts[0]) == 64
            and all(c in "0123456789abcdef" for c in parts[0])
        ):
            names.append(parts[1].strip())
        else:
            names.append(line)
    return names


def _inputs(parsed: dict) -> list:
    """The claim's declared pinned inputs, in root-preimage order: the
    manifest file itself first (it is a pinned input too), then every path
    it lists — or, with no manifest, the recipe's own `inputs` list.
    """
    claim = parsed.get("claim", {})
    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        return [manifest] + list(parsed.get("_manifest_inputs", []))
    return list(claim.get("inputs", []))


def _steps(parsed: dict) -> list:
    """Every step, in recipe order."""
    return list(parsed.get("step", []))


def gates(parsed: dict) -> list:
    """The `gate` steps, in recipe order."""
    return [s for s in _steps(parsed) if s.get("kind") == "gate"]


def produces(parsed: dict) -> list:
    """The `produce` steps, in recipe order."""
    return [s for s in _steps(parsed) if s.get("kind") == "produce"]


def generated_outputs(parsed: dict) -> list:
    """The names of every `produce` step whose class is `generated` (the
    default for a produce step) — the regrowable, non-identity bytes.
    """
    return [
        s["output"] for s in produces(parsed) if s.get("class", "generated") == "generated"
    ]


def load_recipe(d: str) -> dict:
    """Parse and validate the recipe under `d`. Refuses, with a reason, any
    bytes that are not a well-formed, well-typed claim recipe.
    """
    path = recipe_path(d)
    try:
        with open(path, "rb") as f:
            doc = tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        raise ClaimError(f"malformed recipe {path!r}: {exc}") from exc
    except OSError as exc:
        raise ClaimError(f"cannot read recipe {path!r}: {exc}") from exc

    if not isinstance(doc, dict):
        raise ClaimError(f"malformed recipe {path!r}: not a table")

    claim = doc.get("claim", doc.get("record"))
    if not isinstance(claim, dict):
        raise ClaimError(f"recipe {path!r} needs a [claim] table")
    doc["claim"] = claim

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

    steps = doc.get("step", [])
    if not isinstance(steps, list):
        raise ClaimError(f"recipe {path!r}: [[step]] must be an array of tables")
    for step in steps:
        if not isinstance(step, dict):
            raise ClaimError("each step must be a table")
        kind = step.get("kind")
        if kind not in core.KINDS:
            raise ClaimError(
                f"step kind must be one of {sorted(core.KINDS)}: {kind!r}"
            )
        output = step.get("output")
        if not isinstance(output, str) or output == "":
            raise ClaimError("every step needs a non-empty string output")
        if kind == "gate" and not isinstance(step.get("run"), str):
            raise ClaimError(f"gate step {output!r} needs a run command")
        core._safe(d, output)

    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        if not isinstance(manifest, str):
            raise ClaimError("[claim] inputs_manifest must be a string")
        names = _read_input_manifest(d, manifest)
        for n in names:
            core._safe(d, n)
        doc["_manifest_inputs"] = names
    else:
        inputs = claim.get("inputs", [])
        if not isinstance(inputs, list) or not all(isinstance(i, str) for i in inputs):
            raise ClaimError("[claim] inputs must be a list of strings")
        for n in inputs:
            core._safe(d, n)

    return doc
