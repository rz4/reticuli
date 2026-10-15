"""The kernel's public surface (v2 names) -- see `spec/kernel-api.md`.

A thin aggregator: identity and sealing come straight from `_kernel.seal`/
`_kernel.identity`; the record format comes from `_kernel.attest`; every
verb that needed behavior beyond what those primitives pin -- `rebuild`,
`audit`, `verify`, `phase`, `crosscheck`, mutation scoring, signing, the
record-backed proof -- lives in `_kernel.crosscheck` and is re-exported
here unchanged.
"""
from ._kernel import attest, core, identity, recipe as _recipe_mod, run, seal as _seal_mod
from ._kernel import crosscheck as _xc

# -- the one error vocabulary -------------------------------------------------

ClaimError = core.ClaimError

# -- constants the check pins -------------------------------------------------

RECIPE = core.RECIPE
STORE = core.STORE
MANIFEST = core.MANIFEST
LEDGER = core.LEDGER
NAMESPACE = core.NAMESPACE
SIGN_DIR = core.SIGN_DIR
SIGN_NAMESPACE = core.SIGN_NAMESPACE
_JAILED = core._JAILED

RECORD_NAMESPACE = attest.RECORD_NAMESPACE
RECORD_FORMAT = attest.RECORD_FORMAT

# -- identity and sealing: the primitives, unchanged --------------------------

root = identity.root
build_digest = identity.build_digest
seal = _xc.seal
read_manifest = _xc.read_manifest

# -- the record reader ---------------------------------------------------------

record_canonical = attest.record_canonical
record_digest = attest.record_digest
record_validate = attest.record_validate
record_read = _xc.record_read
record_signer = attest.record_signer

# -- running a gate, its ledger, and the environment contract -----------------

run_gate = _xc.run_gate
ledger = run.ledger
ledger_events = run.ledger_events
cost = run.cost
preflight = run.preflight
furnish = _xc.furnish

# -- the higher verbs: everything crosscheck.py builds on the primitives ------

load_recipe = _xc.load_recipe
verify = _xc.verify
phase = _xc.phase
rebuild = _xc.rebuild
audit = _xc.audit
crosscheck = _xc.crosscheck
sign_node = _xc.sign_node
mutation_score = _xc.mutation_score
vacuous_gates = _xc.vacuous_gates
gate_deciders = _xc.gate_deciders
independence = _xc.independence
record_proof = _xc.record_proof
sandbox = _xc.sandbox

# -- the bytes boundary, exposed because the check probes it directly --------

_hash_file = core._hash_file
