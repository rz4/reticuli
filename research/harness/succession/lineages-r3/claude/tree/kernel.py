"""The kernel's public surface (spec/kernel-api.md).

`reticuli.kernel` is a thin facade: identity, sealing, and gate execution
are implemented in `_kernel/core.py`, `recipe.py`, `identity.py`, `seal.py`,
and `run.py`; the crosscheck/audit/mutation engine, the stricter `verify`,
`phase`, `rebuild`, and the record reader are implemented in
`_kernel/crosscheck.py`. This module imports and re-exports that surface
under the names the acceptance check pins, adding only `sign_node` (the
signature-chain fold), which needs nothing from either layer.

Nothing above the kernel may import an unpinned name from `_kernel`; this
module is the whole of what is pinned.
"""
import hashlib
import json

from ._kernel import core
from ._kernel import crosscheck as _crosscheck
from ._kernel import identity
from ._kernel import run
from ._kernel import seal as _seal

# -- Errors and protocol constants ------------------------------------------

ClaimError = core.ClaimError

STORE = core.STORE
MANIFEST = core.MANIFEST
RECIPE = core.RECIPE
LEDGER = core.LEDGER
NAMESPACE = core.NAMESPACE
SIGN_DIR = core.SIGN_DIR
SIGN_NAMESPACE = core.SIGN_NAMESPACE
RECORD_NAMESPACE = _crosscheck.RECORD_NAMESPACE
RECORD_FORMAT = _crosscheck.RECORD_FORMAT

_JAILED = core._JAILED

_hash_file = core._hash_file

# -- Recipe ------------------------------------------------------------------

# crosscheck.load_recipe adds the one validation recipe.load_recipe itself
# does not cover: a damaged [claim] envelope.
load_recipe = _crosscheck.load_recipe

# -- Identity ------------------------------------------------------------------

root = identity.root
build_digest = identity.build_digest

# -- Sealing -------------------------------------------------------------------

# `seal` is crosscheck's variant: it tolerates a GENERATED step's output
# being a symlink (never hashed, so never a reason to refuse at seal time;
# audit, which does copy it into a room, refuses it there).
seal = _crosscheck.seal
read_manifest = _seal.read_manifest

# `verify` is crosscheck's stricter variant (raises when the claim's own
# bytes cannot be read for recomputation), not seal.verify directly.
verify = _crosscheck.verify

# -- Phase ---------------------------------------------------------------------

phase = _crosscheck.phase

# -- Gates, sandboxing, environment, cost ---------------------------------------

run_gate = _crosscheck.run_gate
sandbox = _crosscheck.sandbox
preflight = run.preflight
ledger = run.ledger
ledger_events = run.ledger_events
cost = run.cost

# -- Rebuild / audit -------------------------------------------------------------

rebuild = _crosscheck.rebuild
audit = _crosscheck.audit

# -- The claim boundary: vacuous gates, deciders ----------------------------------

vacuous_gates = _crosscheck.vacuous_gates
gate_deciders = _crosscheck.gate_deciders

# -- Mutation score ----------------------------------------------------------------

mutation_score = _crosscheck.mutation_score

# -- Declared independence ------------------------------------------------------

independence = _crosscheck.independence

# -- The three-machine test and the recorded proof -------------------------------

crosscheck = _crosscheck.crosscheck
record_proof = _crosscheck.record_proof

# -- Records (spec/record.md) ----------------------------------------------------

record_canonical = _crosscheck.record_canonical
record_digest = _crosscheck.record_digest
record_validate = _crosscheck.record_validate
record_read = _crosscheck.record_read
record_signer = _crosscheck.record_signer


def sign_node(root: str, digest: str, links) -> str:
    """One node of the bottom-anchored signature chain: a fold of a
    layer's root, its build digest, and the digests of the signatures
    beneath it. Deterministic; binds the SET of links below, not their
    enumeration order.
    """
    payload = {"root": root, "build_digest": digest, "links": sorted(links)}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
