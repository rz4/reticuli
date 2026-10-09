"""The kernel's public surface (`spec/kernel-api.md`).

Everything here is assembled from `reticuli._kernel`'s submodules: `core`
(the path/bytes boundaries and the on-disk/environment contract), `recipe`
(parsing), `identity` (the root and build digest), `seal` (freezing and
verifying identity), `run` (gate execution, the sandbox, the cost ledger),
`attest` (the record format), and `crosscheck` (rebuild, audit, the
three-machine test, mutation testing, and the verbs that compose them).
"""
from ._kernel import attest, core, crosscheck as _crosscheck
from ._kernel import recipe as _recipe
from ._kernel import run as _run
from ._kernel import seal as _seal
from ._kernel.core import ClaimError

# -- the on-disk / environment contract --------------------------------------
NAMESPACE = core.NAMESPACE
DIGEST = core.DIGEST
FORMAT = core.FORMAT
STORE = core.STORE
MANIFEST = core.MANIFEST
RECIPE = core.RECIPE
LEGACY_RECIPE = core.LEGACY_RECIPE
LEDGER = core.LEDGER
USAGE = core.USAGE
MUTATION_RESIDUE = core.MUTATION_RESIDUE
SIGN_DIR = core.SIGN_DIR
SIGN_NAMESPACE = core.SIGN_NAMESPACE
RECORD_NAMESPACE = _crosscheck.RECORD_NAMESPACE
RECORD_FORMAT = _crosscheck.RECORD_FORMAT

_JAILED = core._JAILED

GATE_TIMEOUT = core.GATE_TIMEOUT
TOLERANCE = core.TOLERANCE
COST_KEYS = core.COST_KEYS
COST_LADDER = core.COST_LADDER
KINDS = core.KINDS
GUIDANCE_KEYS = core.GUIDANCE_KEYS

# -- primitives ---------------------------------------------------------------
_hash_file = core._hash_file
load_recipe = _crosscheck.load_recipe
read_manifest = _seal.read_manifest

# -- identity -----------------------------------------------------------------
root = _crosscheck.root
build_digest = _crosscheck.build_digest

# -- freezing and verifying identity ------------------------------------------
seal = _crosscheck.seal
verify = _crosscheck.verify

# -- the signature state machine ----------------------------------------------
phase = _crosscheck.phase
sign_node = _crosscheck.sign_node

# -- gate execution, the sandbox, the cost ledger -----------------------------
run_gate = _crosscheck.run_gate
sandbox = _crosscheck.sandbox
preflight = _run.preflight
cost = _run.cost
ledger = _run.ledger
ledger_events = _run.ledger_events
independence = _crosscheck.independence

# -- rebuild, audit, the three-machine test -----------------------------------
rebuild = _crosscheck.rebuild
audit = _crosscheck.audit
crosscheck = _crosscheck.crosscheck
vacuous_gates = _crosscheck.vacuous_gates
gate_deciders = _crosscheck.gate_deciders
mutation_score = _crosscheck.mutation_score
record_proof = _crosscheck.record_proof

# -- records -------------------------------------------------------------
record_canonical = attest.record_canonical
record_digest = attest.record_digest
record_validate = _crosscheck.record_validate
record_read = _crosscheck.record_read
record_signer = _crosscheck.record_signer
