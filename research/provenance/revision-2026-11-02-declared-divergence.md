# A transition can declare the shape of its divergence

2026-11-02. Item 3 of the APEIRON campaign's feedback
(`research/proposals/2026-11-02-apeiron-campaign-feedback.md`), landed as an
ordinary change: `src/` and `docs/` only, no root moves.

## What landed

`reticuli.divergence` — the campaign's schema-aware comparator
(`compare_v2.py`, committed verbatim beside the handoff) made declarative. A
transition that deliberately changes pinned reference data declares the
shape it expects — which series, which class (`prefix-added`,
`rows-inserted`, `value-change`), the join under which everything else must
still match exactly, and any field a relabeled counter excuses — and
`verify` holds the revised data to it. Rows outside the declaration refuse,
naming the first offending row; a series the declaration does not cover must
be identical; a series present on one side only refuses; `ignore` is the one
escape and is visible in the verdict. A malformed declaration is refused in
band (ClaimError), the same rule the recipe parser holds `envelope` and
`tolerance` to: a shape nobody can read must not reach a verdict.

Runnable as `python3 -m reticuli.divergence ORIGINAL REVISED DECLARATION`
(.csv in the run-metrics layout or .json), exit 0 only when the divergence
is exactly the declared shape.

## The acceptance, reproduced

The handoff's acceptance is A66's own shape. The campaign's recorded run
CSVs did not survive (the comparator ran on transient outputs), so the tests
carry fixtures in the exact documented shape: two warmup-evaluation rows
join the head of the eval series with values identical everywhere, and the
global sticky counter relabels every later row. Declared as `rows-inserted`
on the eval surface, join `(stage, event_id)`, counter excused — verifies
green. The same declaration over a genuinely value-divergent tree refuses at
the first row whose declared identity carries different content; an
insertion off the declared surface refuses; a dropped original row refuses
(`tests/test_divergence.py`).

## The authoring lesson, kept

`docs/criteria.md` gains rule 5: digest a series under its own content,
never a global counter — the counter coupling is what turned a two-row fix
into near-total divergence and cost the campaign a full reference
regeneration, twice. `docs/transitions.md` gains the procedure for shipping
a declaration with a transition.

## What this does not do

The digest still pins what the claim shipped; the declaration never loosens
it. This is the receiver's instrument for reading an intentional root move,
not a tolerance band inside identity. And nothing here is format-bearing —
the declaration lives with the transition (a provenance note, a review),
not in the recipe.
