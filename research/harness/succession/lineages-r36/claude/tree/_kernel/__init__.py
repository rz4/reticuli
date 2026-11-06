"""The kernel, as a chain of small claims.

    core        the path and bytes boundaries, the shared vocabulary
    recipe      parsing an untrusted recipe
    identity    the canonical root and build-digest serializations
    seal        freezing identity, and confirming it
    run         confined gate execution and the cost ledger
    build       materialize, re-earn, rebuild
    attest      the record format
    crosscheck  the three-machine test, vacuity, mutation

`reticuli.kernel` is the facade over all eight; nothing outside the kernel
imports these modules directly.
"""
