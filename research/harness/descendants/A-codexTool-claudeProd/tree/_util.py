"""Small helpers the layers above the kernel share.

This module exists because of a rule and a measurement.  The rule is that
**no layer imports a kernel private**: a dependency's claim promises only
what that claim's gate re-earns, so a layer leaning on `kernel._something`
is leaning on a name nothing pinned — and any legitimate re-derivation of the
kernel may drop it.  The measurement is the 2026-09-21 blind rebuild, which
regrew eighteen layers to their exact roots and could not be stitched
together, because consumers had reached past the facade.

So the helpers live here, beside the kernel rather than inside it, and the
exchange criterion pins this module's whole public surface — not merely the
names today's importers happen to reach, since a regrown consumer may import
any of them directly.

`RECIPE` here is the LEGACY spelling, `claim.toml`.  That is deliberate and
pinned: the constant is what a helper looking for an older claim's recipe
compares against, and the canonical name lives on the kernel facade.
"""
import json
import os

from . import kernel

#: The store directory, and the ledger inside it.
STORE = kernel.STORE
LEDGER = kernel.LEDGER
#: The legacy recipe filename.  The canonical one is `kernel.RECIPE`.
RECIPE = kernel.LEGACY_RECIPE
#: A session's observation trace, before it becomes a claim.
TRACE = ".reticuli/draft.jsonl"


def safe_path(claim: str, name: str) -> str:
    """Resolve a declared path inside a claim, or refuse it."""
    return kernel._safe(claim, name)


def hash_bytes(data: bytes) -> str:
    """The sha256 of bytes in hand."""
    return kernel.hash_bytes(data)


def read_json(path: str, default=None):
    """Read a JSON file, or hand back `default` when there is nothing to read."""
    if not os.path.isfile(path):
        return default
    try:
        return kernel._read_json(path)
    except kernel.ClaimError:
        if default is not None:
            return default
        raise


def write_json(path: str, payload) -> None:
    """Write JSON atomically."""
    kernel._write_json(path, payload)


def copy_into(src: str, dst: str) -> None:
    """Copy one file, creating parents and carrying the mode."""
    kernel._copy_into(src, dst)


def stamp() -> str:
    """The current UTC time, in the one spelling every document uses."""
    return kernel._now()


def step_output(step: dict):
    """The path a step pins or produces."""
    return step.get("output") if isinstance(step, dict) else None


def declared_inputs(parsed: dict, claimdir: str) -> list:
    """Every path this claim's identity covers as an input."""
    return kernel.declared_inputs(parsed, claimdir)


def locked_append(path: str, line: str) -> None:
    """Append one line to a residue file, creating its parent."""
    kernel.locked_append(path, line)


def ledger_add(claimdir: str, event: dict) -> None:
    """Append one accounting event to a claim's ledger."""
    kernel.ledger(claimdir, event)


def trace_append(workspace: str, event: dict) -> None:
    """Append one observation to a session's trace.

    The trace has no authority — it is what was OBSERVED, and a claim's
    boundary is DECLARED — so this records and never decides.
    """
    path = os.path.join(workspace, TRACE)
    locked_append(path, json.dumps(dict(event), sort_keys=True))
