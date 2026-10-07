# Proposal — the materialized room recipe is the preimage, as TOML

*Staged 2026-10-07, from closure trial 2 of the new set (r12, the
claude lineage). A contract decision for the keyholder; nothing here
moves a root until signed.*

## The finding

At format 3+ a rebuild room receives "the recipe the root was computed
from" — the guidance-stripped (and at format 4, step-sorted) preimage —
rather than the raw file. The original produces it with
`_dump_recipe`: the parsed tables REWRITTEN AS TOML that parses back to
the same tables. The r12 kernel instead wrote the preimage's canonical
JSON serialization into the file named `reticuli.toml`, and then its
own `load_recipe` refused the file it had just written:

    refused: malformed recipe '…/child/reticuli.toml':
    Invalid statement (at line 1, column 1)

A kernel that cannot rebuild what it itself seals — self-incompatible
at format 3 and above, which since the migration is every layer of the
self-claim chain and the repository claim itself.

## Why no criterion saw it

Every rebuild fixture in the boundary is FORMAT 1: build_check's
single- and multi-output claims, kernel_check's producer probes,
launcher_check's — all raw `claim.toml` files with no format key. At
format 1 the room receives the recipe byte-for-byte (a copy), so the
rewrite path never executes under any pinned rebuild. The one place a
format-4 rebuild happens is self_check's bootstrap and the research
trial — the whole-repo instruments, where it surfaced. The familiar
species, fifth sighting: a symmetric contract (copy at format ≤2,
rewrite at format ≥3) exercised on one side only.

## What must be pinned if accepted

`build_check` (owning rebuild's room materialization): one of its
rebuild fixtures becomes format 4 with a guidance line, and the check
asserts (a) the rebuild succeeds, (b) the ROOM's recipe file parses as
TOML, (c) the parsed tables equal the preimage (guidance absent, steps
canonically ordered), and (d) the child lands the parent's root. A
criteria edit — a root move — hence the signature gate. Adoption
resets the count from 1 to 0, same as last time, for the same reason:
trial 1 of this set qualified against a boundary now known to carry
this hole (r11's own rebuild path was simply never asked the
format-3+ question by the fixtures; it happens to answer correctly).

## The cross-family scoreboard, honestly

The glob pin DID steer: the r12 pack expands input patterns, the chain
builds, and the layer that felled r10 passed first-attempt. Cross-
family pin-steering works. What this trial adds is that the foreign
prior's reservoir was deeper than one seam — the second claude draw
found the second claude-shaped hole, again in the half of a symmetric
contract the fixtures never exercised. Two draws, two seams, both of
the same species as everything since r6: the unexercised half of a
symmetric pair.

## Status

Signed by the keyholder 2026-10-07 ("I approve move on to r13") and
landed the same day (see the provenance record
revision-2026-10-07-the-room-recipe-bundle.md). Adoption reset the
closure count from 1 to 0, as the bar requires — the second such
reset, paid for the same reason as the first.
