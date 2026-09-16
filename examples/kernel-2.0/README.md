# The seed claim

This directory is the claim whose generated output is the v2 kernel itself.

- `claim.toml` — the recipe: two generated outputs (`reticuli/__init__.py`,
  `reticuli/kernel.py`) and one gate (`checks/kernel_check.py`, verdict
  `KERNEL_OK`).
- `checks/kernel_check.py` — the acceptance suite, translated from the v1
  kernel check into the v2 vocabulary pinned by `spec/kernel-api.md`. It is
  the complete executable definition of "a correct v2 kernel".

The kernel source is deliberately absent: it is regrown **blind** by a
producer that sees only this directory (bootstrap step 3,
`docs/provenance/bootstrap.md`). The claim is in draft phase until that rebuild
earns the gate; only then is it sealed and its root recorded. The regrown
kernel must also agree with `reticuli.reference` on every root — two
implementations of `spec/identity.md`, written from the spec by different
hands, checked against each other.
