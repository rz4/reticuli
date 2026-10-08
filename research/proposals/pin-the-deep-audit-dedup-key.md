# Proposal — the deep audit dedups by root, not by name

*Staged 2026-10-08, from trial 1 of set 3 (r13, the claude lineage). A
contract decision for the keyholder; nothing here moves a root until
signed. Signing resets the closure count, as twice before.*

## The finding

The transitivity pin (the format-4-era `exchange_check` three-claim
fixture) requires the deep audit to WALK the whole ancestor chain. r13
walks it — the pin steered. But it dedups the walk by component NAME,
marking a name visited before recursing into that component's own
ancestors; the original dedups by component ROOT (`registry.chain`:
`if link["root"] in seen`). In the self-claim chain every layer
re-links the same-named ancestors it carries, so r13 collapses
distinct-root layers that share a name into a single visit and returns
fewer than eighteen judged layers. `self_check` counts the shortfall
and refuses — the SAME assertion that felled r4 (then it was
one-level recursion; now it is whole-walk with the wrong identity key).

Why the pin did not catch it: the three-claim fixture has three
DISTINCT names (base, mid, top), so name-dedup and root-dedup agree on
it exactly. The fixture exercises "does it recurse?" and is silent on
"what makes two visited layers the same layer?" — the fifth-species
pattern once more, the unexercised half of a symmetric choice (dedup
by name vs by root), and the half the self-claim chain depends on.

## What must be pinned if accepted

`exchange_check`'s deep-audit fixture gains a layer that RE-LINKS an
ancestor under a name already present higher in the chain but at a
DIFFERENT root (the shape the self-claim chain actually has), and
asserts the deep audit judges both — i.e. two components sharing a
name but differing in root are two layers, not one. Equivalently and
more directly: assert the walk dedups by root. A criteria edit, so a
root move, hence the signature gate.

## The cross-family datum this completes

Three claude draws, three load-bearing seams: input-pattern globs
(r10), the room recipe's syntax (r12), the deep-audit dedup key (r13).
All three are the unexercised half of a symmetric contract; all three
were invisible to the codex generations that drained the codex prior.
But the depth is increasing: r10 failed at 21 s (pack, the shallowest
layer), r12 at 0.4 min (room materialization), r13 at 22 min (deep in
self_check, after the full bootstrap had already held — gen-2,
audit_repo, and matrix orchestration all passed first). Each claude
draw penetrates further before the next unexercised half stops it.
That is pin-steering working across a family at a measurable rate: the
reservoir is not refilling, it is draining, one seam deeper per draw.

## The honest cost

This is the third reset. The count returns to 0 and both qualifying
codex trials of the current set are spent. The alternative — a
boundary whose deep audit admits a name-colliding chain as fewer
layers than it has — is a published bar with a counting bug in its own
self-description. Pay the reset.
