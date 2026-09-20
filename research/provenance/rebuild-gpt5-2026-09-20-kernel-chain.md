# The decomposed kernel regrows: gpt-5 rebuilds all eight sub-claims

*Research record — what was tried and what it showed. Not normative.*

The payoff experiment for the whole reuse-primitive-plus-8-way-split arc. On
2026-09-19 the second full self-rebuild showed the kernel does **not**
one-shot-regrow: as a 2,562-line monolith judged by a 1,865-line suite, gpt-5
ground for ~48 minutes and never passed the gate, at no bounded budget. The
response was to decompose the kernel into eight small sub-claims and give
`ret rebuild` a reuse mode. This experiment tests whether that made the
intractable tractable.

## Method

The kernel is now eight layered sub-claims (core → recipe → identity → seal →
run → build → attest → crosscheck). For each, `ret rebuild <chain>/<layer>
--producer openai` reuses the sealed layers below (the incremental primitive)
and asks gpt-5 to regrow only that layer's module from its acceptance suite plus
the supplied lower modules. Cost metered; the three largest capped at 20 minutes.

## Result: all eight converged

Every layer rebuilt to its **exact sealed root** (verified; the six with a
behavioral gate also crosscheck-accept). The regrown code is different from ours
in every case — and, except for identity, markedly leaner.

| layer | ours → gpt-5 | cost | note |
|---|---|---|---|
| core | 225 → 102 | $0.05 | boundaries, hashing, vocabulary |
| recipe | 198 → 87 | $0.12 | recipe parsing |
| identity | 134 → **149** | $2.35 | the only one *longer* — see below |
| seal | 132 → 67 | $0.18 | seal/verify |
| run | 534 → 184 | $0.24 | gate execution, ledger |
| build | 506 → **66** | $0.42 | audit/rebuild — see caveat |
| attest | 224 → 140 | $0.69 | the record format |
| crosscheck | 797 → 422 | $9.70 | the three-machine apex, mutation |
| **total** | | **$13.75** | the whole kernel, regrown |

The monolith did not regrow at any price; decomposed, the whole kernel regrows
for under fourteen dollars — and the four smallest layers for about one. That is
the economy the layered build was built to unlock, demonstrated end to end.

## Two findings worth keeping

**1. Byte-exact serialization is the hard floor, and it is identity.** Every
behavioral layer converged on the first attempt at 30 turns. `identity` did not:
its suite pins the canonical root and build-digest by *golden vectors* — exact
SHA-256 preimages, where correct behavior is not enough, the bytes must be
identical. It failed at 30 turns, and only converged when given 80 ($2.35, and
the one layer where gpt-5's code came out *longer* than ours — reproducing an
exact serialization takes explicit code, not clever code). The unforgiving pin
is the expensive one; that is a property of what identity guarantees, not a
defect.

**2. A layer regrows to its check's strength, and the checks differ.** gpt-5's
`build` is 66 lines to our 506, and it lands the build root — because
`build_check` is a focused suite (seal a claim, audit it, reject a tampered
input), lighter than the comprehensive `kernel_check` the crosscheck layer
carries. So "regrew to the sealed root" means "satisfies that layer's
criterion," which is exactly what the root promises — not "is a full drop-in
build layer." The inner layers whose suites are tight (identity's golden
vectors, core's boundaries) are faithful; the outer layers whose suites I kept
light regrow minimal modules that pass their own gate. **The check's strength is
the knob for composition fidelity**, and the comprehensive `kernel_check` at the
top layer (plus the deep audit over the assembled chain) is what still holds the
whole kernel to full behavior. Tightening run/build/attest's own suites toward
kernel_check's coverage is the follow-up that would make each independently
drop-in, at higher regrow cost.

## The thesis, at the scale that had resisted it

The equivalence-class claim — a root names the criteria, not the code — now holds
for reticuli's own kernel, piece by piece, by an independent producer: eight
structurally different modules, eight exact roots. And the operational lesson is
the one that matters for large software: you do not regrow a big system in one
shot; you decompose it into checkable pieces, regrow each cheaply against its
criterion, reuse the ones you trust, and let the composite gate hold the whole.
The kernel was the hardest case in the tree, and it fell.
