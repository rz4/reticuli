"""Run a claim's checks against a separately supplied realization."""

from __future__ import annotations

import os

from . import kernel
from ._kernel import recipe


def assess(directory, outputs):
    """Audit generated outputs supplied as a mapping of claim names to paths."""
    parsed = kernel.load_recipe(directory)
    expected = set(recipe.generated_outputs(parsed))
    if set(outputs) != expected:
        raise kernel.ClaimError(
            "heldout outputs must match generated outputs: " + repr(sorted(expected)))
    replacements = {name: os.fspath(path) for name, path in outputs.items()}
    return kernel.audit(directory, produce_from=replacements)


def heldout(directory, outputs):
    """Alias for :func:`assess`."""
    return assess(directory, outputs)
