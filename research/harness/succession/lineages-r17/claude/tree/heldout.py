"""Measuring a claim's strength by holding back producer guidance.

`spec/claim-format.md`: a produce step's `guidance` is a hint for a
rebuilder, never a condition on acceptance -- only the gate decides that.
`held_out` rebuilds a claim with every hint withheld from the producer
(`kernel.rebuild(..., guidance=False)`), so a pass measures what the pinned
criteria alone carry, with nothing supplied by a human's wording.

Only the public kernel surface (`reticuli.kernel`) is used, per
`spec/layers.md`. Stdlib only.
"""
from reticuli import kernel


def held_out(d: str, producer: str, into: str, **kwargs) -> dict:
    """Blind-rebuild `d` into `into` via `producer`; guidance withheld.

    Returns `kernel.rebuild`'s own result with `"blind": True` added, so a
    caller can tell this measurement apart from an ordinary, guided rebuild.
    """
    kwargs.pop("guidance", None)
    result = kernel.rebuild(d, producer, into, guidance=False, **kwargs)
    result = dict(result)
    result["blind"] = True
    return result
