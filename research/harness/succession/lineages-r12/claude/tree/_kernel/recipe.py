"""Recipe parsing: turning an untrusted `reticuli.toml` into a validated step list.

`load_recipe` reads a claim's recipe under either name (`reticuli.toml`,
preferred, or the legacy `claim.toml`), parses it, and validates it against
the rules in `spec/claim-format.md`: a required `[claim] name`, a confined
path for every declared input and step output, and a `kind`/`output` (and,
for a gate, `run`) on every step. Anything malformed or hostile refuses in
band as a `ClaimError` -- the recipe is untrusted input, so a parse crash is
never acceptable.

`gates`, `produces`, and `generated_outputs` read the parsed recipe; they do
not re-read the filesystem or re-validate.

Stdlib only.
"""
import os
import tomllib

from . import core

GENERATED_CLASSES = frozenset({"generated", "free"})  # v2 / v1


def recipe_path(d: str) -> str:
    """The recipe file under `d`, preferring the canonical name."""
    primary = os.path.join(d, core.RECIPE)
    if os.path.isfile(primary):
        return primary
    legacy = os.path.join(d, core.LEGACY_RECIPE)
    if os.path.isfile(legacy):
        return legacy
    raise core.ClaimError(
        f"refused: no recipe found in {d!r} "
        f"({core.RECIPE!r} or {core.LEGACY_RECIPE!r})"
    )


def _read_input_manifest(path: str) -> list:
    """Parse an `inputs_manifest` file: one path per line.

    Each line is either a bare path or `<sha256>  <path>`; blank lines and
    `#` comments are ignored.
    """
    entries = []
    with open(path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            head, _, tail = line.partition(" ")
            if len(head) == 64 and tail.strip() and all(
                c in "0123456789abcdef" for c in head
            ):
                entries.append(tail.strip())
            else:
                entries.append(line)
    return entries


def _inputs(d: str, raw: dict) -> list:
    """The declared pinned inputs: an explicit list, or an `inputs_manifest`.

    When a manifest is declared, the manifest file itself is a pinned input
    too, alongside every path it names.
    """
    claim = raw.get("claim", {})
    manifest_name = claim.get("inputs_manifest")
    if manifest_name is not None:
        if not isinstance(manifest_name, str):
            raise core.ClaimError("refused: [claim] inputs_manifest must be a string")
        manifest_path = core._safe(d, manifest_name)
        paths = [manifest_name]
        if os.path.isfile(manifest_path):
            paths.extend(_read_input_manifest(manifest_path))
        return paths

    inputs = claim.get("inputs", [])
    if not isinstance(inputs, list) or not all(isinstance(p, str) for p in inputs):
        raise core.ClaimError("refused: [claim] inputs must be a list of strings")
    return list(inputs)


def _steps(parsed: dict) -> list:
    """Every step, in the order the recipe declared them."""
    return parsed.get("step", [])


def gates(parsed: dict) -> list:
    """The gate steps."""
    return [s for s in _steps(parsed) if s.get("kind") == "gate"]


def produces(parsed: dict) -> list:
    """The produce steps."""
    return [s for s in _steps(parsed) if s.get("kind") == "produce"]


def generated_outputs(parsed: dict) -> list:
    """Outputs of produce steps whose class is generated (v1: free) -- the
    regrowable implementation, outside the root."""
    return [
        s["output"] for s in produces(parsed)
        if s.get("class", "generated") in GENERATED_CLASSES
    ]


def load_recipe(d: str) -> dict:
    """Parse and validate the recipe under claim directory `d`.

    Refuses, as a `ClaimError`, anything malformed: unparsable TOML, a
    missing or non-string `[claim] name`, a step missing `kind`/`output`
    (or `run` on a gate), an unrecognized step `kind`, or any declared path
    that escapes the claim directory.
    """
    path = recipe_path(d)
    try:
        with open(path, "rb") as f:
            raw = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise core.ClaimError(f"refused: malformed recipe {path!r}: {e}") from e
    except OSError as e:
        raise core.ClaimError(f"refused: cannot read recipe {path!r}: {e}") from e

    claim = raw.get("claim")
    if claim is None:
        claim = raw.get("record")  # v1 table name
    if not isinstance(claim, dict):
        raise core.ClaimError("refused: recipe is missing its [claim] table")
    raw = dict(raw)
    raw["claim"] = claim

    name = claim.get("name")
    if not isinstance(name, str):
        raise core.ClaimError("refused: [claim] name is required and must be a string")

    fmt = claim.get("format", 1)
    if not isinstance(fmt, int) or isinstance(fmt, bool) or fmt < 1:
        raise core.ClaimError("refused: [claim] format must be a positive integer")
    if fmt > core.FORMAT:
        raise core.ClaimError(
            f"claim format {fmt} is newer than this kernel understands "
            f"(format {core.FORMAT}); upgrade reticuli to read it"
        )

    steps = raw.get("step", [])
    if not isinstance(steps, list):
        raise core.ClaimError("refused: [[step]] must be an array of tables")
    for step in steps:
        if not isinstance(step, dict):
            raise core.ClaimError("refused: each step must be a table")
        kind = step.get("kind")
        if kind not in core.KINDS:
            raise core.ClaimError(
                f"refused: step kind must be one of {sorted(core.KINDS)}: {kind!r}"
            )
        output = step.get("output")
        if not isinstance(output, str) or not output:
            raise core.ClaimError("refused: every step needs a string output")
        core._safe(d, output)
        if kind == "gate" and not isinstance(step.get("run"), str):
            raise core.ClaimError("refused: a gate step needs a string 'run'")

    for input_path in _inputs(d, raw):
        core._safe(d, input_path)

    environment = claim.get("environment")
    if environment is not None:
        if not isinstance(environment, str):
            raise core.ClaimError("refused: [claim] environment must be a string path")
        core._safe(d, environment)

    return raw
