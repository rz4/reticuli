"""reticuli.kernel: the public kernel surface (spec/kernel-api.md).

Every symbol here is a thin, uniform boundary over reticuli._kernel's
internals: a refusal anywhere beneath surfaces as ClaimError, the only
kernel error, never a raw traceback (spec/verification.md: "hostile claim
bytes are refused, never crashed on"). Stdlib only, never the network.
"""
import functools

from reticuli._kernel import attest as _attest
from reticuli._kernel import core as _core
from reticuli._kernel import crosscheck as _crosscheck
from reticuli._kernel import identity as _identity
from reticuli._kernel import recipe as _recipe
from reticuli._kernel import run as _run
from reticuli._kernel import seal as _seal

ClaimError = _core.ClaimError

RECIPE = _core.RECIPE
LEGACY_RECIPE = _core.LEGACY_RECIPE
STORE = _core.STORE
MANIFEST = _core.MANIFEST
LEDGER = _core.LEDGER
NAMESPACE = _core.NAMESPACE
SIGN_DIR = _core.SIGN_DIR
SIGN_NAMESPACE = _core.SIGN_NAMESPACE
RECORD_NAMESPACE = _attest.RECORD_NAMESPACE
RECORD_FORMAT = _attest.RECORD_FORMAT
_JAILED = _core._JAILED


def _public(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ClaimError:
            raise
        except Exception as e:
            raise ClaimError(str(e)) from e
    return wrapper


@_public
def _hash_file(path):
    return _core._hash_file(path)


@_public
def load_recipe(d):
    return _crosscheck.load_recipe(d)


@_public
def root(parsed, d):
    return _identity.root(parsed, d)


@_public
def build_digest(d):
    return _identity.build_digest(d)


@_public
def seal(d, **kwargs):
    return _crosscheck.seal(d, **kwargs)


@_public
def read_manifest(d):
    return _seal.read_manifest(d)


@_public
def verify(d):
    return _crosscheck.verify(d)


@_public
def audit(d, produce_from=None):
    return _crosscheck.audit(d, produce_from=produce_from)


@_public
def rebuild(d, producer, into, produce_from=None, input_from=None,
            guidance=True, producer_env=None):
    return _crosscheck.rebuild(d, producer, into, produce_from=produce_from,
                               input_from=input_from, guidance=guidance,
                               producer_env=producer_env)


@_public
def phase(d):
    return _crosscheck.phase(d)


@_public
def crosscheck(m1, m2, m3, mutants=None):
    return _crosscheck.crosscheck(m1, m2, m3, mutants=mutants)


@_public
def record_proof(m1, m2, m3):
    return _crosscheck.record_proof(m1, m2, m3)


@_public
def sign_node(root, digest, links):
    return _crosscheck.sign_node(root, digest, links)


@_public
def mutation_score(d, max_mutants=20):
    return _crosscheck.mutation_score(d, max_mutants=max_mutants)


@_public
def vacuous_gates(parsed):
    return _crosscheck.vacuous_gates(parsed)


@_public
def gate_deciders(cmd):
    return _crosscheck.gate_deciders(cmd)


@_public
def independence(d):
    return _crosscheck.independence(d)


@_public
def run_gate(cmd, d, recipe=None):
    return _crosscheck.run_gate(cmd, d, recipe)


@_public
def sandbox(cmd=None, d="."):
    return _crosscheck.sandbox(cmd, d)


@_public
def preflight(parsed):
    return _run.preflight(parsed)


@_public
def cost(d):
    return _run.cost(d)


@_public
def ledger(d, entry):
    return _run.ledger(d, entry)


@_public
def ledger_events(d):
    return _run.ledger_events(d)


@_public
def record_canonical(doc):
    return _attest.record_canonical(doc)


@_public
def record_digest(doc):
    return _attest.record_digest(doc)


@_public
def record_validate(doc):
    return _attest.record_validate(doc)


@_public
def record_read(path):
    return _crosscheck.record_read(path)


@_public
def record_signer(path, anchor):
    return _attest.record_signer(path, anchor)
