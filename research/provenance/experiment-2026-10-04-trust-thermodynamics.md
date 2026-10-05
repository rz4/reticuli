# Trust thermodynamics: the measured economics of earning and trusting

*2026-10-04, cycle 15. **Corrected 2026-10-05** — the original of this
record published unit-mixed ratios (see the correction note at the
end). Instrument: `research/harness/scaling/thermo.py`; every number
below is written by the instrument to
`research/harness/scaling/thermo_report.json`, and re-running the
instrument reproduces it from the lineage ledgers plus a fresh
measurement.*

## The three costs

Every verdict in this economy is paid for at one of three prices. All
chain figures are per-chain (20 layers); per-layer figures are labeled
as such and never mixed into a ratio.

    GENERATION   a producer regrows a layer blind     median 131.4 min/chain
    EARN         a verifier re-runs every check            25.7 s/chain
    TRANSFER     a verifier accepts a stored earn
        self     own local cache: fingerprint lookup,       0.02 s/chain
                 no cryptography
        signed   another's earn, ssh-verified against       0.18 s/chain
                 allowed signers — what a NETWORK pays

Per layer, generation runs ~100 s (seal) to ~32 min (crosscheck, the
largest suite); earns run 70 ms to 9.2 s. The asymmetries, per-chain
over per-chain:

    generation / earn                ≈ 307×
    earn / transfer (signed)         ≈ 142×
    generation / transfer (signed)   ≈ 44,000×
    generation / transfer (self)     ≈ 385,000×  (same-host only)

## What the ratios mean

**~300× is why acceptance criteria work.** Producing a conforming
implementation costs two to three orders of magnitude more than
checking one — the same asymmetry that makes proof systems and peer
review economical. It is also why the model prior matters so much: a
producer spends that budget *once*, and everything the check doesn't
force is filled from the cheapest source available, which is what the
ladder measured.

**~1,250× is what the earn cache buys a single machine** (self policy —
the scaling work's cold→warm collapse, priced per chain). It is a
same-host number: no signature is checked, so it transfers trust to
nobody.

**~44,000× is what a signature buys a network.** One verified earner's
2.2 hours of producer work becomes any trusting party's fifth of a
second, *including* the ssh verification of a signed statement per
layer. That is the argument for the attested shared cache in one
number — and the honest statement of what is at stake in the
allowed-signers file: each name in it wields a four-orders-of-magnitude
multiplier on whatever it vouches for. Signature verification is not
free (it is ~10× the raw lookup), which is exactly why it is worth
stating separately instead of rounding to zero.

**The per-layer spread matters too.** Generation/earn ranges ~64×
(reference — cheap to write, costly to check against the vectors) to
~2,600× (cli-render — hard to derive, instant to check). Layers at the
low end are where checks do heavy work per verdict; the high end is
where criteria are maximally leveraged. If the cost envelope is ever
tightened per-layer, that column says where the budget should go.

## A catch along the way

Building the instrument exposed a latent break from the final bundle:
`scripts/selfaudit.py` still staged every layer flat, so the layered
self-audit failed on the new reference layer (its room needs the
repository shape). Fixed root-neutrally. The gate never caught it
because selfaudit is repo tooling outside the boundary — a small,
honest reminder of exactly where the boundary ends.

## Caveats

Wall-clock on one machine; the corrected run was taken while an r4
regrowth was in progress (load average is recorded in the report, and
the earn figure moved 20.9 s → 25.7 s between the quiet and contended
runs — the ratios are order-of-magnitude claims and survive that).
Generation medians pool every lineage ledger across eras (r1–r3 at
their respective roots); that mixing is stated, not hidden, and the
per-run sources are listed in the report.

## Correction note (2026-10-05)

The first version of this record claimed earn/transfer ≈ 1,469× and
generation/transfer ≈ 553,704×. Both divided a per-chain numerator by a
per-layer denominator — inflating each by the layer count — and the
"transfer" they priced was the self-policy cache lookup, which verifies
no signature at all, while the prose said "cache lookup + signature
verification". The instrument now measures the signed path as itself
(ephemeral key, local cache cleared, every layer accepted only through
ssh-keygen verification), keeps every ratio per-chain over per-chain,
and writes all raw rows to the report file. The corrected network
leverage is ~44,000× — an order of magnitude smaller than first
published, and still the whole argument.
