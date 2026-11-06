"""The kernel's public surface — a facade over the eight sub-layers.

Everything above the kernel reaches it through this module and nothing else,
so **no layer imports a kernel private**.  That rule is not tidiness: the
blind rebuild of 2026-09-21 regrew eighteen layers to their exact roots and
the stitched tool would not import, because consumers had been reaching for
names the kernel never promised.  What a layer depends on, the kernel's own
check must pin — and the pinned surface is exactly the table in
`spec/kernel-api.md`.

The split beneath this file is for construction and audit; a caller sees one
kernel.  Re-exporting rather than re-implementing is deliberate: a lawful
reimplementation of `rebuild` at this layer once dropped the sandbox key its
sub-layer had pinned, so the pin held where pinned and evaporated at the
surface callers actually reach.
"""
from ._kernel.core import (CLASSES, COST_KEYS, COST_LADDER, COST_UNITS,
                           DECIDING, DIGEST, FORMAT, GATE_TIMEOUT,
                           GUIDANCE_KEYS, KINDS, LEDGER, LEGACY_RECIPE,
                           MANIFEST, MUTATION_RESIDUE, NAMESPACE, PARTS,
                           RECEIPT, RECIPE, RECORD_FORMAT, RECORD_NAMESPACE,
                           SCRATCH, SEALED, SIGN_DIR, SIGN_NAMESPACE, STORE,
                           TOLERANCE, USAGE, ClaimError, _ENV_CACHE,
                           _ENV_CACHE_DIR,
                           _ENV_CLAIM, _ENV_COLOR, _ENV_KEY, _ENV_MODEL,
                           _ENV_OUTPUT, _ENV_OUTPUTS, _ENV_PRICE,
                           _ENV_PRODUCER, _ENV_REQUEST, _ENV_SIGNERS,
                           _ENV_TIMEOUT, _ENV_TOLERANCE, _ENV_USAGE,
                           _ENV_VENDOR, _JAILED, _KEEP_ENV, _copy_into,
                           _hash_file, _judging_host, _now, _read_json,
                           _safe, _write_json, hash_bytes)
from ._kernel.identity import build_digest, root
from ._kernel.recipe import (carried_outputs, declared_inputs,
                             generated_outputs, gates, load_recipe,
                             pinned_outputs, produces, recipe_path,
                             step_class, step_guidance)
from ._kernel.seal import read_manifest, seal, verify
from ._kernel.run import (confinement, cost, furnish, gate_timeout,
                          independence, ledger,
                          ledger_events, locked_append, preflight, run_gate,
                          sandbox, sandbox_backend)
from ._kernel.build import audit, phase, rebuild
from ._kernel.attest import (record_canonical, record_digest, record_read,
                             record_signer, record_validate)
from ._kernel.crosscheck import (crosscheck, gate_deciders, mutation_score,
                                 record_proof, sign_node, vacuous_gates)

__all__ = [
    # identity
    "root", "build_digest", "seal", "verify", "read_manifest", "phase",
    "load_recipe", "recipe_path",
    # execution and verdicts
    "run_gate", "sandbox", "sandbox_backend", "confinement", "preflight",
    "furnish",
    "gate_timeout", "audit", "rebuild",
    # accounting
    "cost", "ledger", "ledger_events", "independence",
    # comparison and strength
    "crosscheck", "record_proof", "mutation_score", "vacuous_gates",
    "gate_deciders", "sign_node",
    # the record format
    "record_canonical", "record_digest", "record_read", "record_signer",
    "record_validate",
    # the refusal
    "ClaimError",
    # constants
    "RECIPE", "LEGACY_RECIPE", "STORE", "MANIFEST", "LEDGER", "SIGN_DIR",
    "NAMESPACE", "SIGN_NAMESPACE", "RECORD_NAMESPACE", "RECORD_FORMAT",
    "FORMAT", "DIGEST", "COST_KEYS", "COST_LADDER", "TOLERANCE", "KINDS",
]
