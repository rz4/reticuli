"""reticuli.kernel -- the public kernel surface (spec/kernel-api.md).

A thin facade: identity and verb primitives (core, recipe, identity, seal,
run, build, attest) do the real work; this module names the pinned public
symbols and adds the few verbs (`crosscheck`, `sign_node`, `mutation_score`,
`phase`, the environment-aware `seal`/`verify`/`audit`/`rebuild`) that live
one layer above them, in `_kernel/crosscheck.py`.
"""
from ._kernel import core as _core
from ._kernel import seal as _seal
from ._kernel import run as _run_mod
from ._kernel import identity as _identity
from ._kernel import attest as _attest
from ._kernel import crosscheck as _crosscheck

# -- constants -------------------------------------------------------------

ClaimError = _core.ClaimError

NAMESPACE = _core.NAMESPACE
SIGN_NAMESPACE = _core.SIGN_NAMESPACE
SIGN_DIR = _core.SIGN_DIR
STORE = _core.STORE
MANIFEST = _core.MANIFEST
RECIPE = _core.RECIPE
LEDGER = _core.LEDGER
_JAILED = _core._JAILED

RECORD_NAMESPACE = _attest.RECORD_NAMESPACE
RECORD_FORMAT = _attest.RECORD_FORMAT

# -- direct pass-throughs ---------------------------------------------------

_hash_file = _core._hash_file
read_manifest = _crosscheck.read_manifest
run_gate = _crosscheck.run_gate
preflight = _run_mod.preflight
ledger = _run_mod.ledger
ledger_events = _run_mod.ledger_events
cost = _run_mod.cost
build_digest = _identity.build_digest

record_canonical = _attest.record_canonical
record_digest = _attest.record_digest
record_validate = _attest.record_validate
record_read = _crosscheck.record_read
record_signer = _attest.record_signer

# -- the verb layer (spec/verification.md) ----------------------------------

load_recipe = _crosscheck.load_recipe
root = _crosscheck.root
seal = _crosscheck.seal
verify = _crosscheck.verify
audit = _crosscheck.audit
rebuild = _crosscheck.rebuild
phase = _crosscheck.phase
independence = _crosscheck.independence
crosscheck = _crosscheck.crosscheck
record_proof = _crosscheck.record_proof
sign_node = _crosscheck.sign_node
mutation_score = _crosscheck.mutation_score
vacuous_gates = _crosscheck.vacuous_gates
gate_deciders = _crosscheck.gate_deciders


def sandbox(command: str, d: str):
    """A functional probe of the host sandbox: run `command` in `d` and
    report `(result, backend)` -- `[1]` names the jail actually applied."""
    res = _crosscheck.run_gate(command, d, None)
    return (res, res["quarantine"])
