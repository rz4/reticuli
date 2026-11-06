"""The kernel: identity, verification, and confined execution.

Eight modules, inner to outer, each depending only on the ones before it:

    core        the path and bytes boundaries, the vocabulary, the constants
    recipe      parsing an untrusted recipe into validated tables
    identity    the canonical root and build-digest serializations
    seal        freezing a root onto the manifest, and confirming it
    run         confined gate execution, the ledger, the environment contract
    build       materialize, audit, rebuild, the signed phase
    attest      the record format (spec/record.md)
    crosscheck  the three-machine test, vacuity, mutation score

`reticuli.kernel` re-exports the union as the kernel's public surface; the
split exists so each piece is small enough to regrow on its own.
"""
