"""Canonical claim identity and generated-build digests.

The root commits to a canonical JSON rendering of the parsed recipe and to
hashes of its pinned files.  Generated outputs are deliberately omitted from
the root; :func:`build_digest` gives the concrete generated realization its
own digest.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from typing import Any

from . import core, recipe as recipe_api


def _canonical_json(value: Any) -> str:
    """Serialize a JSON value using the identity format's exact defaults."""
    try:
        # These are intentionally json.dumps' defaults apart from sorting keys:
        # default separators, ASCII escaping, and CPython's numeric spelling.
        return json.dumps(value, sort_keys=True)
    except (TypeError, ValueError, OverflowError) as exc:
        raise core.ClaimError(f"value is not canonically JSON serializable: {exc}") from exc


def _claim_format(recipe: Any) -> int:
    """Return the declared claim format, with the historical default of 1."""
    claim = recipe_api._claim_table(recipe)
    version = claim.get("format", 1)
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise core.ClaimError("claim 'format' must be a positive integer")
    understood = getattr(core, "FORMAT", 1)
    if version > understood:
        raise core.ClaimError(
            f"claim format {version} is newer than this kernel understands "
            f"(format {understood}); upgrade reticuli to read it"
        )
    return version


def _preimage_recipe(recipe: Any) -> dict[str, Any]:
    """Return the recipe object as represented in the identity preimage.

    Format 3 removes producer-only hints.  Format 4 additionally treats the
    step array as a set, ordering steps by their own canonical JSON encodings.
    Older formats retain the authored step order and all hint fields.
    """
    if not isinstance(recipe, dict):
        raise core.ClaimError("recipe must be a TOML table")
    version = _claim_format(recipe)
    result = copy.deepcopy(recipe)

    steps = result.get("step", [])
    if not isinstance(steps, list) or any(not isinstance(step, dict) for step in steps):
        raise core.ClaimError("recipe 'step' must be an array of tables")

    if version >= 3:
        for step in steps:
            step.pop("guidance", None)
            step.pop("request", None)
    if version >= 4:
        steps.sort(key=_canonical_json)

    # The deepcopy and in-place adjustments above leave the caller's parsed
    # recipe untouched; return an independent JSON-compatible object.
    return result


def _generated_step(step: dict[str, Any]) -> bool:
    """Whether this step contributes a regrowable output rather than a pin."""
    if step.get("kind") != "produce":
        return False
    return step.get("class", "generated") in ("generated", "free")


def _parts(recipe: Any, directory: os.PathLike[str] | str) -> dict[str, str]:
    """Build the string-to-string root preimage parts for a loaded recipe."""
    preimage_recipe = _preimage_recipe(recipe)
    parts: dict[str, str] = {
        "digest": "sha256",
        "recipe": _canonical_json(preimage_recipe),
    }

    for name in recipe_api._inputs(recipe, directory):
        filename = recipe_api._path_in_claim(directory, name, "claim input")
        parts["input:" + name] = core._hash_file(filename)

    for step in recipe_api._steps(recipe):
        if _generated_step(step):
            continue
        name = step.get("output")
        if not isinstance(name, str):
            raise core.ClaimError("step output must be a string path")
        filename = recipe_api._path_in_claim(directory, name, "step output")
        parts["pinned:" + name] = core._hash_file(filename)

    return parts


def root(recipe: Any, directory: os.PathLike[str] | str) -> str:
    """Compute the lowercase SHA-256 identity root of a claim."""
    encoded = _canonical_json(_parts(recipe, directory)).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_digest(directory: os.PathLike[str] | str) -> str:
    """Digest the present, local generated outputs of a claim.

    Missing generated outputs are omitted: this function can describe a
    partial or empty realization.  Outputs inherited ``from`` another claim
    are likewise omitted.  Each remaining entry is the output name paired
    with the SHA-256 of its bytes, and the entries are sorted so the digest is
    independent of recipe step order.
    """
    parsed = recipe_api.load_recipe(directory)
    entries: list[tuple[str, str]] = []

    for step in recipe_api._steps(parsed):
        if not _generated_step(step) or "from" in step:
            continue
        name = step.get("output")
        if not isinstance(name, str):
            raise core.ClaimError("step output must be a string path")
        filename = recipe_api._path_in_claim(directory, name, "generated output")
        try:
            os.lstat(filename)
        except FileNotFoundError:
            # A generated output need not exist yet (or at all).
            continue
        except OSError as exc:
            raise core.ClaimError(f"cannot inspect generated output {name!r}: {exc}") from exc
        entries.append((name, core._hash_file(filename)))

    entries.sort()
    encoded = _canonical_json(entries).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
