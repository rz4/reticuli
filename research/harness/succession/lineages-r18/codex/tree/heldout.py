"""Run a claim's gates against a separately supplied implementation."""

from __future__ import annotations

import os
import tempfile

from . import kernel
from ._util import copy_into, declared_inputs, safe_path


def assess(claim, outputs):
    """Judge generated files from *outputs* with the claim's pinned criteria.

    ``outputs`` may be a directory or a mapping from declared output name to
    source file. The room and its verdicts are discarded after the check.
    """
    document = kernel.load_recipe(claim)
    checked = kernel.verify(claim)
    if not checked["ok"]:
        raise kernel.ClaimError("claim identity mismatch")
    supplied = {step["output"] for step in document.get("step", [])
                if step["kind"] == "produce"
                and step.get("class", "generated") == "generated"
                and "from" not in step}
    source_files = ({name: safe_path(outputs, name) for name in supplied}
                    if isinstance(outputs, (str, os.PathLike)) else dict(outputs))
    if set(source_files) != supplied:
        raise kernel.ClaimError("heldout output set does not match claim")
    with tempfile.TemporaryDirectory(prefix="reticuli-heldout-") as room:
        recipe_name = (kernel.RECIPE if os.path.isfile(os.path.join(claim, kernel.RECIPE))
                       else "claim.toml")
        copy_into(safe_path(claim, recipe_name), safe_path(room, recipe_name))
        for name in declared_inputs(claim):
            copy_into(safe_path(claim, name), safe_path(room, name))
        for step in document.get("step", []):
            if step["kind"] == "produce" and step["output"] not in supplied:
                source = safe_path(claim, step["output"])
                if os.path.isfile(source):
                    copy_into(source, safe_path(room, step["output"]))
        for name, source in source_files.items():
            copy_into(source, safe_path(room, name))
        for step in document.get("step", []):
            if step["kind"] == "gate":
                source = safe_path(claim, step["output"])
                if os.path.isfile(source):
                    copy_into(source, safe_path(room, step["output"]))
        kernel.seal(room)
        return kernel.audit(room)


check = assess
