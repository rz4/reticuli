"""The kernel: identity and verification, as one surface.

A pure facade over the eight sub-claims in `_kernel/`. Everything above the
kernel reaches it through this module and through nothing else -- the
sub-layer decomposition exists for construction and audit, not for mixing
implementations.

    root(recipe, d)           the identity hash (spec/identity.md)
    seal(d)                   compute the root, write the manifest
    verify(d)                 identity ONLY -- no gate is executed
    audit(d)                  deep re-earning; earned vs carried
    rebuild(d, producer, into) regrow until the gates pass
    crosscheck(m1, m2, m3)    the three-machine test
    phase(d)                  draft / sealed / signed
"""
from ._kernel import attest as _attest
from ._kernel import build as _build
from ._kernel import core as _core
from ._kernel import crosscheck as _crosscheck
from ._kernel import identity as _identity
from ._kernel import recipe as _recipe
from ._kernel import run as _run
from ._kernel import seal as _seal

# -- the refusal -----------------------------------------------------------
ClaimError = _core.ClaimError

# -- protocol constants ----------------------------------------------------
NAMESPACE = _core.NAMESPACE
DIGEST = _core.DIGEST
FORMAT = _core.FORMAT
STORE = _core.STORE
MANIFEST = _core.MANIFEST
RECIPE = _core.RECIPE
LEGACY_RECIPE = _core.LEGACY_RECIPE
LEDGER = _core.LEDGER
USAGE = _core.USAGE
MUTATION_RESIDUE = _core.MUTATION_RESIDUE
PARTS = _core.PARTS
RECEIPT = _core.RECEIPT
MEASURED = _core.MEASURED
SIGN_DIR = _core.SIGN_DIR
SIGN_NAMESPACE = _core.SIGN_NAMESPACE
RECORD_NAMESPACE = _attest.RECORD_NAMESPACE
RECORD_FORMAT = _attest.RECORD_FORMAT
KINDS = _core.KINDS
CLASSES = _core.CLASSES
COST_KEYS = _core.COST_KEYS
COST_LADDER = _core.COST_LADDER
COST_UNITS = _core.COST_UNITS
GUIDANCE_KEYS = _core.GUIDANCE_KEYS
STATUSES = _core.STATUSES
SANDBOXES = _core.SANDBOXES
GATE_TIMEOUT = _core.GATE_TIMEOUT
TOLERANCE = _core.TOLERANCE
_JAILED = _core._JAILED
_KEEP_ENV = _core._KEEP_ENV

# -- the primitives --------------------------------------------------------
_hash_file = _core._hash_file
_safe = _core._safe
_write_json = _core._write_json
_now = _core._now

# -- recipe ----------------------------------------------------------------
load_recipe = _recipe.load_recipe
recipe_path = _recipe.recipe_path
gates = _recipe.gates
produces = _recipe.produces
generated_outputs = _recipe.generated_outputs
step_class = _recipe.step_class
step_guidance = _recipe.step_guidance

# -- identity --------------------------------------------------------------
root = _identity.root
build_digest = _identity.build_digest

# -- seal ------------------------------------------------------------------
seal = _seal.seal
verify = _seal.verify
read_manifest = _seal.read_manifest

# -- execution -------------------------------------------------------------
run_gate = _run.run_gate
sandbox = _run.sandbox
sandbox_backend = _run.sandbox_backend
gate_timeout = _run.gate_timeout
preflight = _run.preflight
furnish = _run.furnish
ledger = _run.ledger
ledger_events = _run.ledger_events
cost = _run.cost
independence = _run.independence

# -- build -----------------------------------------------------------------
audit = _build.audit
rebuild = _build.rebuild
phase = _build.phase
authorizations = _build._authorized

# -- records ---------------------------------------------------------------
record_validate = _attest.record_validate
record_canonical = _attest.record_canonical
record_digest = _attest.record_digest
record_read = _attest.record_read
record_signer = _attest.record_signer

# -- the three machines ----------------------------------------------------
crosscheck = _crosscheck.crosscheck
record_proof = _crosscheck.record_proof
mutation_score = _crosscheck.mutation_score
vacuous_gates = _crosscheck.vacuous_gates
gate_deciders = _crosscheck.gate_deciders
sign_node = _crosscheck.sign_node
