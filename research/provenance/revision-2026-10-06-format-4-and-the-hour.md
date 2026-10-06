# Revision — format 4, and the hour

*2026-10-06, late. Keyholder-signed ("I sign off on them, start working
on r8"), both pins from the r7 trial — the trial that found no new
behavioral seam and left exactly two named walls. This bundle removes
both. Sixth signed bundle in three days; second migration in one.*

    old root  c6eac1332529ce9975dcf959b99077158b76cd4faddf26c252cff38636a0214a
    new root  47ee199b97e41c96d6c585bd61af5db67d56cfb2c7db896b9d75ce3c295a269c

    all twenty layer roots moved — core too this time, because core's own
    recipe declares the format. (An intermediate reseal, 06e7dfaa…, stood
    for the half hour the audit took to catch an undeclared input; see
    "the audit ate third", below.)

## Click one — format 4: the step list is a set

The r7 trial's finding: two conforming packs emitted the same steps in
different orders (lexicographic against glob-pattern) and minted
different roots, drifting 13 of 20 layer roots from exactly where
`kernel.py` sorts after `_kernel/*`. Order can no more reject a
realization than a hint's wording can, so the preimage now sorts the
step list — after the format-3 guidance strip — by each step's
canonical JSON encoding.

Landed as a format, not a convention, which is the whole point: the
authoring-FORM family (wording at r6, order at r7) is closed in the
preimage rather than member by member, so a third member cannot
appear. Everything carries the change together — `spec/identity.md`
and `spec/claim-format.md` state it, `_kernel/identity.py` and
`reference.py` implement it identically (the two-implementation
cross-check is the only thing standing behind the identity
computation), `core.FORMAT` rises to 4 so a format-4 claim is readable,
`identity_check` pins both halves (reordering at format 4 does not
move the root; at format 3 it still does, so no older root can move),
and two new twin vectors — `v12-format4-order-a` and `-b`, same steps
in different file orders — publish one `expected-root` for
implementations in any language. Nineteen vectors, two
implementations, one answer.

## Click two — the window is an hour

The r7 tree died at 1800.019 seconds with every criterion it reached
passing: the first refusal by cost alone. Measured, it runs the same
work at ~1.6× the original's pace (chain build ~16 min against ~10).
Half an hour was calibrated to this implementation's speed, and a
window calibrated to the author's own pace quietly makes membership
author-relative — exactly what an equivalence class is not. An hour
admits every conforming tree sampled to date and is still a bound. The
real fix is a cheaper audit (incremental `self_check` through the
shipped reuse primitive), which is ordinary engineering and not
identity; the window buys the closure arc room to measure
specification completeness instead of interpreter pace.

## The audit ate third

The gate passed this bundle on the first draft and the AUDIT refused
it — the room-versus-local asymmetry doing precisely its job. The two
new vector directories are pinned INPUTS of the reference layer (that
layer stages `spec/vectors` and pins what it stages), so adding them
moved the reference root, which the lockfile duly recorded from a local
build. But the files were not declared in this claim's own `inputs`,
and an audit room materializes only declared inputs — so the room built
the chain with seventeen vectors where the lockfile named nineteen, and
`self_check` refused.

The gate could not see it: the files are sitting right there in the
working tree. Only a room that is told what the claim contains, and
contains nothing else, can tell you that a file you added is not yet
part of the claim. A conformance vector the claim does not ship is not
a vector — a stranger's blind room would never have received it. Both
are declared now, and the fix is the kind this project likes: the
instrument found an authoring omission nobody was looking for, one
layer away from where the work was happening.

## Deliberately not in this bundle

`pack`'s authoring default stays format 3. The signed proposal
migrated the chain and this claim and said nothing about fresh
authoring, so the leftover question is written down rather than
assumed: `research/proposals/author-at-format-4.md`.

## The shape of the move

Two spec documents, two implementations of the preimage, one shared
constant, three criteria (identity, core, and the chain's builder), two
new vectors, and the repository recipe; all twenty roots re-pinned
mechanically from one selfclaim run. Full gate and audit green at the
new root; parity green across the eight staged suites; 103/103;
closure and the self-contained scanner clean on the first draft. r8
runs next at the frozen new root — the first generation facing a
boundary with no known walls, and the first with a real chance to be
qualifying trial 1 of 3.
