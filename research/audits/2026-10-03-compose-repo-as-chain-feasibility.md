# Can the repository be composed as its layer chain? — feasibility

*2026-10-03. A research finding, read-only. It answers whether the
"fully principled" layered self-audit (compose the repo AS the selfclaim
chain so the sandboxed `audit_deep` + per-component reuse applies
directly) is a clean transition. It is not — and the reason is worth
pinning down, because it says something true about what the repository's
identity actually commits to.*

## The question

The scaling thread shipped per-component reuse and a layered self-audit
(`reuse.layered_audit` + `scripts/selfaudit.py`), which earns each
selfclaim layer against the live `src/` with reuse. The proposed deeper
step was to make the repository itself a composed claim — the surface
layer of the chain — so its own `ret audit` would run the kernel's
sandboxed `audit_deep` per component instead of `layered_audit`'s staged
check runs. That changes how the repository seals: its root would become
the chain's surface-layer root.

## The finding: the chain pins strictly less than the repository does

The repository root (`reticuli.toml`) pins **111 inputs**: 87 under
`spec/`, 22 criteria, `gate.py`, and `scripts/selfclaim.py` — plus
`gate_timeout`, `requires`, and the one gate `python3 gate.py` that runs
*every* criterion. The selfclaim chain pins, across its nineteen layers,
only the nineteen per-layer checks. The gap is not incidental:

- **The entire specification (87 `spec/` files) is pinned by the repo
  root and by no layer.** `spec/identity.md`, `spec/claim-format.md`, the
  conformance vectors, the threat model — changing any of them moves the
  repository root today. The layer chain commits to none of it. A
  chain-root repository would stop committing to its own normative
  surface.
- **Three criteria belong to no layer**, because they are cross-cutting
  by nature:
  - `self_check.py` — the lockfile over the layer roots themselves; it is
    *about* the chain, so it cannot be a link in it;
  - `vectors_check.py` — the conformance vectors and `reference.py`
    parity, which the nineteen layers do not include;
  - `kernel_parity.py` — that the living kernel satisfies every kernel
    suite.

So the repository is not merely the top of the chain. It is **the chain,
plus the specification, plus the cross-cutting invariants that no single
layer owns.** Re-sealing it as the chain root would silently drop all of
that — the exact coverage loss the whole tool exists to catch.

## The reading, and the recommendation

This is a genuine property, not an accident of layout: an acceptance
boundary deliberately commits to more than the sum of its parts — the
spec that gives the parts meaning, and the invariants that hold the parts
together. The layer decomposition is a *construction and audit*
convenience; it was never the whole claim.

Therefore:

- **Do not re-seal the repository as the chain root.** As described it is
  a weaker claim wearing the same name. Done *correctly* — folding spec/
  and the three cross-cutting criteria back onto the surface layer — it is
  a large, intricate re-architecture whose only gain over what already
  ships is per-layer sandbox isolation during self-audit, a fidelity
  point, not a coverage or correctness one.
- **The practical and distributed win is already delivered**, root-neutral:
  `scripts/selfaudit.py` makes the repository's own self-audit incremental
  (O(the frontier)), and the attested shared cache (`signed`/`quorum`)
  lets a fresh host trust verified earners. Neither touches the
  repository's identity.
- **If more audit fidelity is wanted**, the cheap root-neutral step is to
  earn each layer in `layered_audit` through the kernel's sandbox rather
  than a plain subprocess — matching `ret audit`'s isolation without
  moving a single root. That is a `src` change, available on request; it
  does not require redefining what the repository is.

The honest version of "both" the keyholder signed off: the attested
shared cache is built and shipped; the repo-as-chain is investigated and
found to be an identity-weakening move that should not be taken — which is
itself the answer, and a better outcome than performing it.
