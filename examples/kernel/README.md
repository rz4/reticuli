# The kernel claim

Root `fac55f897b323f7b694c5f2e117a3afca0748e55f67389071c10399891be77e3`.

- `reticuli.toml` — two generated outputs (`reticuli/__init__.py`,
  `reticuli/kernel.py`), one gate (`checks/kernel_check.py`, verdict
  `KERNEL_OK`), and a declared cost ceiling: `envelope = { usd = 40.0 }`,
  pinned from this claim's own rebuild ledger with honest headroom. The
  ceiling is a hard condition — a redo measured over it is rejected, and a
  proof that never measured dollars is incomplete, never accepted.
- `checks/kernel_check.py` — the acceptance suite: the complete executable
  definition of "a correct kernel". It is a pinned input, so its bytes are
  inside the root. Never format it; see `spec/identity.md`.
- `reticuli/` — a conforming implementation. Generated, therefore *outside*
  the root: these bytes can be deleted and regrown, byte-different, and the
  claim keeps its name.

`criteria/kernel_parity.py` holds `src/reticuli/` — the package this
repository ships — to this claim, by running the claim's suite against the
living bytes.

## Lineage, and what is and is not proven

This claim is the **v2.3** revision. The chain: `d64cc301…` (the proven
birth claim, retired with its bytes preserved outside the repository),
`4b90feef…` (v2.1, seven measured under-specifications), `e650b524…` (v2.2:
the symlink rule, records as a crosscheck transport, complete audit of a
self-referential claim — finding 12), `82a81357…` (v2.3), and now
`fac55f89…` (v2.4: format 3, so producer guidance leaves the root, and the
cost band is hard only when the claim declares a tolerance).

v2.3 pins the recipe's two names in the kernel's own suite (finding 13: a
kernel must read `reticuli.toml`, the name a v2.2 rebuild could not),
introduces the three-valued verdict (accept, reject, or incomplete — a
declared condition nobody measured can never accept), declares the cost
ceiling `envelope = { usd = 40.0 }` as a hard condition, and pins the
declared environment.

A proof does not transfer across a revision, so **this claim is sealed with
no proof**: the v2.2 proof stays with `e650b524…` where it was earned, and
re-earning against this suite is the open exercise
([`../../docs/open-call.md`](../../docs/open-call.md)). Full account:
[`../../docs/provenance/revision-2026-09-17.md`](../../docs/provenance/revision-2026-09-17.md).
