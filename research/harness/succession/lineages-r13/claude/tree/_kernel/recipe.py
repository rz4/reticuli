"""Reading a claim's recipe: the untrusted boundary.

`load_recipe` finds the recipe under either filename (`reticuli.toml`,
preferred, or the legacy `claim.toml`), parses it, and validates it against
`spec/claim-format.md`'s rules -- refusing in band with a `ClaimError`,
never a raw parser traceback. The accessors below (`_steps`, `gates`,
`produces`, `generated_outputs`, `_inputs`) read the parsed structure that
`load_recipe` returns; none of them touch the filesystem.
"""
import tomllib

from . import core

_HEXDIGITS = frozenset("0123456789abcdef")


def recipe_path(d: str) -> str:
    """The on-disk recipe path: `reticuli.toml`, else the legacy `claim.toml`."""
    import os

    primary = os.path.join(d, core.RECIPE)
    if os.path.isfile(primary):
        return primary
    legacy = os.path.join(d, core.LEGACY_RECIPE)
    if os.path.isfile(legacy):
        return legacy
    raise core.ClaimError(
        f"no recipe in {d!r}: expected {core.RECIPE} or {core.LEGACY_RECIPE}"
    )


def load_recipe(d: str) -> dict:
    """Parse and validate the recipe at `d`. Refusals are `ClaimError`."""
    path = recipe_path(d)
    try:
        with open(path, "rb") as f:
            parsed = tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        raise core.ClaimError(f"malformed recipe {path!r}: {exc}") from exc
    except OSError as exc:
        raise core.ClaimError(f"cannot read recipe {path!r}: {exc}") from exc

    claim = parsed.get("claim")
    if not isinstance(claim, dict):
        raise core.ClaimError(f"recipe {path!r} needs a [claim] table")

    name = claim.get("name")
    if not isinstance(name, str) or not name:
        raise core.ClaimError(
            f"recipe {path!r}: [claim] name is required and must be a string"
        )

    fmt = claim.get("format", 1)
    if isinstance(fmt, bool) or not isinstance(fmt, int) or fmt < 1:
        raise core.ClaimError(f"recipe {path!r}: [claim] format must be a positive integer")
    if fmt > core.FORMAT:
        raise core.ClaimError(
            f"claim format {fmt} is newer than this kernel understands "
            f"(format {core.FORMAT}); upgrade reticuli to read it"
        )

    steps = parsed.get("step", [])
    if not isinstance(steps, list):
        raise core.ClaimError(f"recipe {path!r}: [[step]] must be an array of tables")
    for step in steps:
        if not isinstance(step, dict):
            raise core.ClaimError(f"recipe {path!r}: every step must be a table")
        kind = step.get("kind")
        if kind not in core.KINDS:
            raise core.ClaimError(
                f"recipe {path!r}: step kind must be one of {sorted(core.KINDS)}, got {kind!r}"
            )
        output = step.get("output")
        if not isinstance(output, str) or not output:
            raise core.ClaimError(f"recipe {path!r}: every step needs an output")
        core._safe(d, output)
        if kind == "gate":
            run = step.get("run")
            if not isinstance(run, str) or not run:
                raise core.ClaimError(f"recipe {path!r}: a gate step needs a run command")

    _inputs(parsed, d)
    return parsed


def _steps(parsed: dict) -> list:
    """Every step, in recipe (file) order."""
    return list(parsed.get("step", []))


def gates(parsed: dict) -> list:
    """The gate steps, in recipe order."""
    return [s for s in _steps(parsed) if s.get("kind") == "gate"]


def produces(parsed: dict) -> list:
    """The produce steps, in recipe order."""
    return [s for s in _steps(parsed) if s.get("kind") == "produce"]


def generated_outputs(parsed: dict) -> list:
    """Outputs this claim is responsible for generating: produce steps whose
    class is `generated` (the default) and that carry no `from` source."""
    result = []
    for step in produces(parsed):
        cls = step.get("class", "generated")
        if cls == "generated" and "from" not in step:
            result.append(step["output"])
    return result


def _inputs(parsed: dict, d: str = None) -> list:
    """The pinned input paths: an explicit `inputs` list, or everything named
    by `inputs_manifest` (the manifest file itself, plus its entries)."""
    claim = parsed.get("claim", {})
    manifest_name = claim.get("inputs_manifest")
    if manifest_name is not None:
        if not isinstance(manifest_name, str) or not manifest_name:
            raise core.ClaimError("[claim] inputs_manifest must be a string")
        if d is None:
            return [manifest_name]
        manifest_path = core._safe(d, manifest_name)
        entries = _read_input_manifest(manifest_path)
        for entry in entries:
            core._safe(d, entry)
        return [manifest_name] + entries

    inputs = claim.get("inputs", [])
    if not isinstance(inputs, list) or not all(isinstance(p, str) and p for p in inputs):
        raise core.ClaimError("[claim] inputs must be a list of non-empty strings")
    if d is not None:
        for p in inputs:
            core._safe(d, p)
    return list(inputs)


def _read_input_manifest(path: str) -> list:
    """Parse an `inputs_manifest` file: one path per line, blank lines and
    `#` comments ignored, an optional leading `<sha256>  <path>` pair."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError as exc:
        raise core.ClaimError(f"cannot read input manifest {path!r}: {exc}") from exc

    paths = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        head, _, rest = line.partition(" ")
        rest = rest.strip()
        if rest and len(head) == 64 and set(head) <= _HEXDIGITS:
            paths.append(rest)
        else:
            paths.append(line)
    return paths
