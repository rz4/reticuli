"""reticuli.heldout -- which pinned inputs the claim's own gates never
touch.

`gate_deciders` (`spec/verification.md`) names the files a gate actually
runs as a script or module.  A claim's `[claim] inputs` may pin files no
gate ever decides against -- fixtures read only as data, or bytes pinned
for identity but never exercised by a test.  Those inputs are held out
of every gate's verdict: their bytes matter to the root, but no run in
this claim would notice if they were wrong.

Stdlib only.  Never the network.
"""
from . import kernel


def held_out(d: str) -> dict:
    """Pinned inputs partitioned into `exercised` (named as a decider by
    at least one gate) and `held_out` (pinned, but no gate names them)."""
    recipe = kernel.load_recipe(d)
    inputs = list(recipe.get("claim", {}).get("inputs", []))

    deciders = set()
    for step in recipe.get("step", []):
        if step.get("kind") == "gate":
            deciders.update(kernel.gate_deciders(step.get("run", "")))

    exercised = [name for name in inputs if name in deciders]
    unexercised = [name for name in inputs if name not in deciders]
    return {"exercised": exercised, "held_out": unexercised}
