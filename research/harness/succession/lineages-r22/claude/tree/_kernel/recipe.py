"""Parsing and validating a claim's recipe: reticuli.toml (or claim.toml).

`load_recipe` reads the recipe under either name, preferring `reticuli.toml`,
and returns the parsed TOML as-is after validating it: a required string
`[claim] name`, a `format` this kernel understands, and a `[[step]]` array
where every step names a `kind` in {produce, gate} and an `output`, a gate
additionally a `run`, and no declared path escapes the claim
(spec/claim-format.md). A malformed or hostile recipe is refused in band as
a `ClaimError`, never a raw parser traceback -- the claim's own recipe is
untrusted input.

`gates`, `produces`, and `generated_outputs` read the parsed steps back out
in the file's own order; canonicalizing that order for identity is the
kernel's job, not this module's. `_inputs` resolves the full set of pinned
input paths a claim declares -- the `inputs` list, a format-2
`inputs_manifest`'s entries plus the manifest file itself, and the
`environment` file -- without mutating the parsed recipe, since the recipe
hashed into the root is exactly what was written, manifest unexpanded.
"""
import os
import tomllib

from . import core
from .core import ClaimError


def recipe_path(d: str) -> str:
    """The recipe file's path under `d`, preferring `reticuli.toml`."""
    primary = os.path.join(d, core.RECIPE)
    if os.path.isfile(primary):
        return primary
    legacy = os.path.join(d, core.LEGACY_RECIPE)
    if os.path.isfile(legacy):
        return legacy
    raise ClaimError(
        f"no recipe found in {d!r}: expected {core.RECIPE} or {core.LEGACY_RECIPE}"
    )


def load_recipe(d: str) -> dict:
    """Parse and validate the claim's recipe; refusals carry a reason."""
    path = recipe_path(d)
    try:
        with open(path, "rb") as f:
            parsed = tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        raise ClaimError(f"malformed recipe {path!r}: {exc}") from exc
    except OSError as exc:
        raise ClaimError(f"cannot read recipe {path!r}: {exc}") from exc

    claim = parsed.get("claim")
    if not isinstance(claim, dict):
        raise ClaimError(f"recipe {path!r} is missing a [claim] table")

    name = claim.get("name")
    if not isinstance(name, str) or not name:
        raise ClaimError(f"recipe {path!r}: [claim] name is required and must be a string")

    fmt = claim.get("format", 1)
    if isinstance(fmt, bool) or not isinstance(fmt, int) or fmt < 1:
        raise ClaimError(f"recipe {path!r}: [claim] format must be a positive integer")
    if fmt > core.FORMAT:
        raise ClaimError(
            f"claim format {fmt} is newer than this kernel understands "
            f"(format {core.FORMAT}); upgrade reticuli to read it"
        )

    inputs = claim.get("inputs", [])
    if not isinstance(inputs, list) or not all(isinstance(p, str) for p in inputs):
        raise ClaimError(f"recipe {path!r}: [claim] inputs must be a list of strings")
    for p in inputs:
        core._safe(d, p)

    manifest_name = claim.get("inputs_manifest")
    if manifest_name is not None:
        if not isinstance(manifest_name, str) or not manifest_name:
            raise ClaimError(f"recipe {path!r}: inputs_manifest must be a string")
        core._safe(d, manifest_name)

    environment = claim.get("environment")
    if environment is not None:
        if not isinstance(environment, str) or not environment:
            raise ClaimError(f"recipe {path!r}: environment must be a string")
        core._safe(d, environment)

    steps = parsed.get("step", [])
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
            raise ClaimError(f"recipe {path!r}: every step needs a string output")
        core._safe(d, output)
        if kind == "gate" and not step.get("run"):
            raise ClaimError(f"recipe {path!r}: a gate step needs a run command")
        if "class" not in step:
            step["class"] = "generated" if kind == "produce" else "pinned"

    return parsed


def _steps(parsed: dict) -> list:
    """Every step, in the recipe's own file order."""
    return list(parsed.get("step", []))


def gates(parsed: dict) -> list:
    """The gate steps, in file order."""
    return [s for s in _steps(parsed) if s.get("kind") == "gate"]


def produces(parsed: dict) -> list:
    """The produce steps, in file order."""
    return [s for s in _steps(parsed) if s.get("kind") == "produce"]


def generated_outputs(parsed: dict) -> list:
    """The outputs of produce steps whose class is `generated` (the default)."""
    return [s["output"] for s in produces(parsed) if s.get("class", "generated") == "generated"]


def _read_input_manifest(path: str) -> list:
    """Read a format-2 inputs manifest: one path per line, an optional
    `<sha256>  <path>` prefix, blank lines and `#` comments ignored."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError as exc:
        raise ClaimError(f"cannot read inputs manifest {path!r}: {exc}") from exc

    hexdigits = frozenset("0123456789abcdef")
    entries = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        head, _, rest = line.partition(" ")
        rest = rest.strip()
        if rest and len(head) == 64 and all(c in hexdigits for c in head):
            entries.append(rest)
        else:
            entries.append(line)
    return entries


def _inputs(parsed: dict, d: str) -> list:
    """The full set of pinned-input paths: declared `inputs`, a format-2
    manifest's entries plus the manifest file itself, and the `environment`
    file -- every path a root hashes as `input:path` (spec/claim-format.md).
    The parsed recipe itself is left unmodified; only this accessor expands
    the manifest.
    """
    claim = parsed.get("claim", {})
    inputs = list(claim.get("inputs", []))

    manifest_name = claim.get("inputs_manifest")
    if manifest_name is not None:
        core._safe(d, manifest_name)
        manifest_path = os.path.join(d, manifest_name)
        if not os.path.isfile(manifest_path):
            raise ClaimError(f"inputs_manifest names a file that is gone: {manifest_name!r}")
        inputs.append(manifest_name)
        for entry in _read_input_manifest(manifest_path):
            core._safe(d, entry)
            if not os.path.isfile(os.path.join(d, entry)):
                raise ClaimError(f"inputs_manifest names a file that is gone: {entry!r}")
            inputs.append(entry)

    environment = claim.get("environment")
    if environment is not None:
        inputs.append(environment)

    return inputs
