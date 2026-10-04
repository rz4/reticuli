# Trust thermodynamics: the measured economics of earning and trusting

*2026-10-04, cycle 15. Instrument: `research/harness/scaling/thermo.py`,
extracting from ledgers the project already wrote — lineage regrowth
timestamps across all runs, the layered self-audit's per-layer earn
times, and the warm-cache transfer cost. Root `1361bfd9…`, unmoved.*

## The three costs

Every verdict in this economy is paid for at one of three prices:

    GENERATION   a producer regrows a layer blind        median 131.4 min/chain
    EARN         a verifier re-runs the layer's check     20.9 s/chain
    TRANSFER     a verifier accepts a trusted earn        ~0.2 s/chain
                 (cache lookup + signature verification)

Per layer, generation runs 100 s (seal) to ~32 min (crosscheck, the
114 KB suite); earns run 60 ms to 7.5 s. The asymmetries:

    generation / earn      ≈ 377×
    earn / transfer        ≈ 1,469×
    generation / transfer  ≈ 553,704×

## What the ratios mean

**377× is why acceptance criteria work.** Producing a conforming
implementation costs two to three orders of magnitude more than checking
one — the same asymmetry that makes proof systems and peer review
economical. It is also why the model prior matters so much: a producer
spends its 377× budget *once*, and everything the check doesn't force is
filled from the cheapest source available, which is what the ladder
measured.

**1,469× is what the earn cache buys a single machine** — the scaling
work's cold→warm collapse, now priced per layer.

**553,704× is what a signature buys a network.** One verified earner's
2.2 hours of producer work becomes any trusting party's fifth of a
second. This is the entire argument for the attested shared cache in one
number: trust is stored verification work, signatures transfer it nearly
losslessly, and the leverage is about half a million to one. It is also
the honest statement of what is at stake in the allowed-signers file —
each name in it wields a 10⁵-fold multiplier on whatever it vouches for.

**The spread matters too.** Generation/earn per layer ranges 78×
(reference — cheap to write, costly to check against seventeen vectors)
to 3,600× (identity — hard to derive, instant to check). Layers at the
low end are where checks are doing heavy work per verdict; layers at the
high end are where the criteria are maximally leveraged. If the cost
envelope is ever tightened per-layer, this column says where the budget
should go.

## A catch along the way

Building the instrument exposed a latent break from the final bundle:
`scripts/selfaudit.py` still staged every layer flat, so the layered
self-audit failed on the new reference layer (its room needs the
repository shape). Fixed root-neutrally; the self-audit now covers all
twenty layers — 21.4 s cold, 0.0 s warm. The gate never caught it
because selfaudit is repo tooling outside the boundary — a small,
honest reminder of exactly where the boundary ends.

## Caveats

Wall-clock on one machine, CPU-contended in places; generation times
include staging and in-room gate iterations (the price as actually
paid, not the model's token time); transfer measured warm on local
disk. The ratios are order-of-magnitude claims, and at these magnitudes
that is enough.
