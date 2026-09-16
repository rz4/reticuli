# The kernel claim

Root `4b90feef318d171a842dd285c589c8f2e350f0e32627d62fa99e64a67fcfc382`.

- `claim.toml` — two generated outputs (`reticuli/__init__.py`,
  `reticuli/kernel.py`) and one gate (`checks/kernel_check.py`, verdict
  `KERNEL_OK`).
- `checks/kernel_check.py` — the acceptance suite: the complete executable
  definition of "a correct kernel". It is a pinned input, so its bytes are
  inside the root. Never format it; see `spec/identity.md`.
- `reticuli/` — a conforming implementation. Generated, therefore *outside*
  the root: these bytes can be deleted and regrown, byte-different, and the
  claim keeps its name.

`tests/kernel_parity.py` holds `src/reticuli/` — the package this repository
ships — to this claim, by having the claim judge the living bytes.

## Lineage, and what is and is not proven

This claim is the **v2.1** revision. Its predecessor, `d64cc301…`, is kept
sealed and intact at [`../conformance/kernel-2.0/`](../conformance/kernel-2.0/): the
kernel exactly as a model regrew it blind, carrying the three-machine proof
it earned.

That proof belongs to the predecessor and **does not transfer**. The v2.1
suite pins seven behaviors the older one left free — two of which the two
independent rebuilds disagreed about — so it is a different claim, and the
predecessor's kernel fails four of the new pins. Re-earning the proof
requires fresh cross-vendor blind rebuilds against this suite.

Until then the honest statement is narrow and true: the living kernel earns
this gate, on macOS and Linux across CPython 3.11–3.13, with the gate run
sandboxed. See [`../docs/provenance/revision-2026-09-15.md`](../docs/provenance/revision-2026-09-15.md).
