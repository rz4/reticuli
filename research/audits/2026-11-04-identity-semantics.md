# Two states with one identity and different acceptance

*2026-11-04. An outside review proposed that the format-4 step
canonicalization is unsound, and that the build digest's silence about file
modes is a second instance of the same gap. Both reproduce. The review had
run neither against the kernel; this document is the end-to-end confirmation,
one correction, and the disposition.*

Reproduce with `python3 research/harness/identity/step_order.py`.

## The invariant at stake

The root is supposed to name an equivalence class of implementations that
pass. For that to mean anything, identity must determine acceptance:

    root(C1) == root(C2)  =>  audit(C1, E) == audit(C2, E)

Everything the identity function discards must be incapable of changing
whether a realization is accepted. Two things it discards can.

## Finding 1: step order is discarded but decides acceptance

`_preimage_recipe` in `_kernel/identity.py` sorts the step list at format ≥ 4,
on the stated ground that "the steps are a set of obligations, and file order
is authoring form." `_steps` in `_kernel/recipe.py` returns the steps in file
order, and `gates()` preserves it, so `audit` executes them in the order the
author wrote.

Two claims, identical but for the order of two gates, where the second reads a
file the first writes:

```toml
[[step]]                                   [[step]]
kind = "gate"                              kind = "gate"
output = "READY"                           output = "VERDICT"
class = "validated"                        class = "validated"
run = "printf ready > READY"               run = "test -f READY && printf ok > VERDICT"
```

Gate outputs are never materialized into a room, so `READY` does not exist
when the room opens. Measured:

| claim | gate order in file | root | `verify` | `audit` |
|---|---|---|---|---|
| A | `READY`, `VERDICT` | `42909c24ae7df581…` | ok | **earned** |
| B | `VERDICT`, `READY` | `42909c24ae7df581…` | ok | **failed** |

One root, two acceptance behaviours. The invariant does not hold.

### This is the specification's defect, not the kernel's

`reticuli.reference` — the second implementation kept deliberately
independent of the kernel so the two must agree — computes the **same root
for both orderings**. The two implementations agree perfectly and are wrong
together, because the rule they both implement faithfully is the unsound one.

That is the finding worth keeping. A conformance vector proves two
implementations compute one hash; it cannot prove the hash identifies the
acceptance predicate. Three independent reconstructions would pass every
vector in `spec/vectors/` and inherit this defect, because it lives in
`spec/identity.md`.

The existing order vectors (`v12-format4-order-a` and `-b`) carry one gate,
so no ordering dependency is expressible in them.

### Scope

This repository's own claim is **not** exposed: format 4, one gate
(`REPO_OK`, running `gate.py`). A single gate has no order to depend on. Any
claim with two or more gates where one reads another's output is exposed.

## Finding 2: file mode is discarded and can decide acceptance

`build_digest` commits `[output, sha256(bytes)]` pairs. It does not commit
the mode. Measured on one file, changed only by `chmod`:

    mode 755   build_digest 5a6949dc3e2492d7dd5151323f85fed0…
    mode 644   build_digest 5a6949dc3e2492d7dd5151323f85fed0…

Identical. Meanwhile `_kernel/core.py` deliberately preserves mode bits when
materializing, precisely because generated artifacts may be programs.

The downstream half of this was found the same day by a different method, in
`2026-11-04-manual-population-audit.md`, without the cause being identified:
**`export`/`import` drops the executable bit, and so does `ret pull`**. After
either, a gate that runs the artifact fails with `Permission denied`. Two
transport paths silently produce a state the digest calls identical and the
gate rejects.

The same gap applies to pinned inputs: their contents are hashed, their modes
are not, so a criterion that executes one directly can change behaviour
without moving the root.

### The authorization consequence, verified structurally

`phase()` in `_kernel/build.py` decides `signed` from the recomputed root, a
recorded proof, and an anchored signature. It re-executes no gate. With the
build digest unmoved by `chmod`, a mode-only change leaves a claim reporting
`signed` while its executable gate would now fail.

**Not tested end to end.** Completing it requires signing a claim, and
`ret sign` is the keyholder's act. Every link is verified except the ceremony.

## One correction to the review

The review offers "execute gates in a canonical order" as a repair option.
That is the wrong half of the fork. Sorting by canonical JSON gives an
execution order unrelated to dependency, so it would make ordering arbitrary
rather than authored, and would silently change what already-sealed format-4
claims do. The defensible options are:

1. **Put step order back in the preimage** under a new format. Honest, and it
   gives up the r6/r7 defect that motivated format 4 — two conforming packs
   minting different roots for one claim by order alone.
2. **Refuse order-dependent recipes at seal time.** Keeps the format-4 win.
   Detectable in the common case: a gate whose command reads a path another
   gate declares as its output. Not decidable in general.
3. **Both**: refuse what is detectable, and version the rest.

Option 2 is the one that preserves the original motivation, and its
incompleteness is statable rather than silent.

For modes, the parallel question is whether the execution-relevant bit
belongs in the commitment, or whether materialization should normalize modes
under an explicit hashed policy. Normalizing is cheaper and makes transport
total; committing is more honest about what the artifact is.

## Disposition

Both repairs are identity-bearing: they touch `spec/identity.md`, the vectors,
and probably `criteria/`. They move the root and need the full transition
procedure and a keyholder signature. Nothing here is patched silently.

Recorded as a candidate **format 6** design question. Two notes on timing:

- The closure ledger records 0 of 3 at the current root, so a versioned fix
  now discards no completed sequence.
- `docs/transitions.md` already names the obligation this exercise satisfies:
  a transition that changes pinned reference data owes the receiver the
  *shape* of the difference, not just a moved digest.

What a repair should carry with it is a new conformance layer the review
names correctly: **identity-preserving transformation tests**. Vary what the
root discards — step order, file mode, comment text, key order — and require
acceptance to be unchanged. Then vary what should change identity and require
the root to move or the claim to be refused. That tests the equivalence class
rather than the hash.
