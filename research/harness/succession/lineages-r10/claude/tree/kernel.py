"""reticuli.kernel: the public kernel surface (`spec/kernel-api.md`).

Identity, verification, rebuild, audit, the three-machine test, and the
record transport. Most verbs are implemented in `_kernel/crosscheck.py`
-- the one private submodule allowed to depend on every other one, and
where the mutation-testing engine lives -- so this module is a plain
re-export of the pinned names.
"""
from ._kernel.core import (
    ClaimError,
    DIGEST,
    FORMAT,
    LEDGER,
    MANIFEST,
    NAMESPACE,
    RECIPE,
    LEGACY_RECIPE,
    SIGN_DIR,
    SIGN_NAMESPACE,
    STORE,
    _JAILED,
    _hash_file,
)
from ._kernel.attest import RECORD_FORMAT, RECORD_NAMESPACE
from ._kernel.seal import read_manifest
from ._kernel.run import ledger, ledger_events, cost, preflight

from ._kernel.crosscheck import (
    load_recipe,
    root,
    seal,
    verify,
    phase,
    rebuild,
    audit,
    crosscheck,
    record_proof,
    sign_node,
    build_digest,
    mutation_score,
    vacuous_gates,
    gate_deciders,
    independence,
    sandbox,
    run_gate,
    record_read,
    record_digest,
    record_validate,
    record_signer,
)
