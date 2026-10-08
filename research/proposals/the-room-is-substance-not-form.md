# Proposal — the room pin checks substance, not presentation

*Staged 2026-10-07, found while smoke-testing the outside-re-earn kit
against the r11 tree. A correction to a pin signed earlier the same
day; a root move, hence the signature gate.*

## The finding

Bundle 9's room-recipe fixture asserts the materialized room recipe
(a) parses as TOML, (b) carries no guidance, (c) lists its steps in
format-4 CANONICAL ORDER, and (d) the child lands the parent's root.
Assertion (c) over-reaches: at format 4, step order is authoring FORM —
it cannot affect any judgment and re-derives the identical root, which
is the entire doctrine the format exists to state. The r11 codex tree,
which qualified as a trial under the previous boundary, materializes
an honest TOML, guidance-free room in FILE order — and the pin refuses
it. A criterion that rejects a conforming member on a byte that judges
nothing is the kill-bound mistake again: the first draft of a hard
pin, too strict where the previous gap was too loose.

Found by the outside-re-earn kit's smoke test — an instrument built
for condition 5 doing register work on its way out the door.

## The correction

Assertion (c) relaxes to SUBSTANCE: the room recipe's parsed tables,
with each step list treated as a set (compared in canonical-JSON
order), equal the preimage's. This still refuses the r12 defect
outright — JSON in the file fails the TOML parse, and content
divergence fails the set comparison — while admitting any order,
exactly as format 4 admits any order in the sealed recipe itself.

## Effect on the ledger

None retroactively: no trial has been judged by the over-strict form
(r13's build layer passed it in-room, so r13 is unaffected either
way). But the boundary currently excludes known-conforming members,
which the bar cannot tolerate going forward, and the outside re-earn
of any codex tree would fail on it spuriously — so this should land
before the current set's trial 2.

## Status

Signed by the keyholder 2026-10-07, landed 2026-10-08 (see the
provenance record revision-2026-10-08-room-substance-and-a-withdrawal.md).
Its signed sibling, pin-the-deep-audit-dedup-key, was WITHDRAWN before
landing when its diagnosis was falsified by measurement — so this
bundle moved one layer root (build), not two.
