"""The kernel: identity and verification.

A facade over the eight sub-layers in `_kernel/`, each a small claim of its
own. The surface below is what `spec/kernel-api.md` pins; nothing above the
kernel may depend on a name that table does not carry.
"""
from ._kernel.attest import (record_canonical, record_digest, record_read,
                             record_signer, record_validate)
from ._kernel.build import audit, phase, rebuild
from ._kernel.core import (DIGEST, FORMAT, LEDGER, LEGACY_RECIPE, MANIFEST,
                           MUTATION_RESIDUE, NAMESPACE, RECIPE,
                           RECORD_FORMAT, RECORD_NAMESPACE, SEALED, SIGN_DIR,
                           SIGN_NAMESPACE, STORE, USAGE, ClaimError,
                           _JAILED, _KEEP_ENV, _hash_file, _now, _safe)
from ._kernel.crosscheck import (crosscheck, gate_deciders, mutation_score,
                                 record_proof, sign_node, vacuous_gates)
from ._kernel.identity import build_digest, root
from ._kernel.recipe import (gates, generated_outputs, load_recipe,
                             produces, recipe_path, step_class)
from ._kernel.run import (cost, discovery, furnish, gate_timeout,
                          independence, ledger, ledger_events, preflight,
                          run_gate, sandbox, sandbox_backend)
from ._kernel.seal import read_manifest, seal, verify

__all__ = [
    "ClaimError", "DIGEST", "FORMAT", "LEDGER", "LEGACY_RECIPE", "MANIFEST",
    "MUTATION_RESIDUE", "NAMESPACE", "RECIPE", "RECORD_FORMAT",
    "RECORD_NAMESPACE", "SEALED", "SIGN_DIR", "SIGN_NAMESPACE", "STORE",
    "USAGE", "audit", "build_digest", "cost", "crosscheck", "discovery",
    "furnish", "gate_deciders", "gate_timeout", "gates",
    "generated_outputs", "independence", "ledger", "ledger_events",
    "load_recipe", "mutation_score", "phase", "preflight", "produces",
    "read_manifest", "rebuild", "recipe_path", "record_canonical",
    "record_digest", "record_proof", "record_read", "record_signer",
    "record_validate", "root", "run_gate", "sandbox", "sandbox_backend",
    "seal", "sign_node", "step_class", "vacuous_gates", "verify",
]
