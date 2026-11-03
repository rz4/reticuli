# Four obligations the APEIRON campaign measured against reticuli

> **ALL FOUR LANDED 2026-11-02**, under the keyholder's standing sign-off
> ("merge both PRs once CI is green, then do all the four items, I sign
> off"), and the root they moved is now signed.
>
> - **Item 1, audit-side** — `kernel.ownership` warning lane (#23). No
>   identity cost, as staged.
> - **Item 1, seal-side** — `[claim] constrains`, held to at seal (#25).
> - **Item 2** — `[claim] assembles`, the assembly claim (#25).
> - **Item 3** — `reticuli.divergence`, declared-shape divergence (#24),
>   plus the authoring lesson as `docs/criteria.md` rule 5. Ordinary change.
> - **Item 4** — `class = "carried"` (#25), with `ret pack --carried` and
>   pack's files-in-no-class note.
>
> Items 1 (seal-side), 2, and 4 were batched under one format bump exactly
> as the ordering below suggests, so the chain paid one re-seal instead of
> three: format 5, repo root `f2d49443 → 37d86018`. Account:
> `research/provenance/revision-2026-11-02-format-5.md` and
> `revision-2026-11-02-ownership-audit.md` and
> `revision-2026-11-02-declared-divergence.md`.
>
> One judgment call below was deliberately **not** taken: whether existing
> run claims should migrate their reference-series digests from a global
> counter to content keys. Item 3's instrument exists; the migration is the
> keyholder's, claim by claim.
>
> *The document is preserved below as received, including its provenance
> paths — one correction: the campaign workspace is not a sibling of this
> repository. It lives at `LBNL/ModCon/prototype/repos/apeiron_reticuli` on
> the machine that ran the campaign.*

2026-11-02. A handoff document for an implementing agent. Not landed here;
nothing below is staged. Each item carries a measured witness from the
APEIRON reconstruction campaign and states what it would cost to adopt.

## Provenance

The campaign packed `BaseSIM_APEIRON` (a nine-module PyTorch
continual-learning framework) into per-component claims and rebuilt it to
replacement grade: the regrown package reproduces the pinned MNIST run
exactly (31/31 metric series by digest, final weights by SHA-256) and
passes 590/591 of the original's own test suite, which the regrowth never
saw. The evidence lives in the sibling workspace
`../apeiron_reticuli/`:

- `claims/LOG.md` — the findings ledger, 111 entries. `A*` ids are
  APEIRON defects; `R*` ids are methodology findings about reticuli
  itself. Every citation below resolves there.
- `claims/scripts/ownership_audit.py` — a working prototype of item 1.
- `docs/regrown_apeiron.md` (branch `ret/2-apeiron-regrown`) — the full
  changelog of the regrown package.
- `compare_v2.py`, beside this file — the campaign's schema-aware series
  comparator (item 3's working prototype), kept verbatim as it ran.

The round trip validates the format: the claim set was a sufficient
encoding of the system. The four items below are where it was sufficient
only because a hand-built mechanism covered a gap the tool does not.

---

## 1. Ownership: a criterion must constrain a file its claim ships

**Priority: highest. A prototype exists and the failure mode is the
campaign's single largest.**

### The measurement

A claim may be handed a component with `class = "generated"` and
`from = "<component>"`: the producer writes its own copy, the gate
validates that copy, and assembly discards it for the owning room's.
A criterion asserting a property of a supplied module therefore
constrains a file that never ships (ledger R33).

Across the campaign's rebuild population, **11 of 50 upstream-test
failures** traced to exactly this: the obligation was written, the gate
passed, and the shipped file had never been under it. Running the
prototype over the finished claim set found **28 pinned criterion files**
whose imports reach a module their claim is supplied rather than owns.
Most are benign (importing `Config` to build a fixture constrains
nothing); the ones that assert are latent R33 instances.

### The proposed obligation

Two stages, independently adoptable:

1. **Audit-side (no identity cost):** port
   `claims/scripts/ownership_audit.py` into `audit` as a warning class.
   The prototype is 75 lines of stdlib: build the owner map from each
   recipe's `[[step]]` outputs, mark `from=`-handed outputs as supplied,
   flag pinned criterion files whose imports cross into the supplied set.
   Import-reach over-approximates "constrains", so this stage warns and
   names the owning claim; it never refuses.

2. **Seal-side (format-bearing):** an optional per-input declaration —
   `constrains = ["module.py", …]` on a pinned criterion — validated at
   seal: every declared target must be an output this claim owns. A claim
   that declares is held to it; a claim that does not gets the audit
   warning only. This keeps fixtures-only imports cheap while making the
   asserting case refusable.

### Acceptance

- `audit` over the APEIRON claim set reports the same 28 files the
  prototype reports today, each naming the owning claim.
- A seal with `constrains` naming a supplied module is refused with a
  message that says where the criterion belongs.

---

## 2. An assembly claim: the room that sees the composition

### The measurement

Five ledger entries (A58, A62, A63, A74, A77) are composition edges no
per-component criterion can express from inside its room: module and
symbol names across the import seam, call signatures, the override
protocol (hook arity, `StopIteration` as the stream-end contract), and
what an inherited method must *do* at a seam rather than merely be. Each
one produced a rebuild that passed every gate and failed at assembly.

Separately, R32: equal outputs do not mean equal measurements. Two
rebuilds with digest-identical training trajectories carried different
FLOP ledgers, because the K-FAC curvature contractions sat inside one
tree's measured window and outside the other's. Anything a program
measures about itself depends on code placement, which output-pinning
cannot see. Closing it took a hand-written boundary criterion run against
the assembled package (`claims/updaters/test_measured_cost_boundary.py`).

The campaign covered both by hand-building an N+1'th room whose fixtures
import the assembled tree. It works, but nothing in the format marks it
as different, and nothing routes a component claim's supplied-module
obligations toward it — which is why item 1's 28 strays had nowhere
correct to go.

### The proposed obligation

A claim whose pinned inputs may include **other claims' roots**, and
whose gates run against the assembly of those claims' shipped outputs.
Minimum viable shape: a recipe field (`assembles = ["<name>@<root>", …]`)
that (a) hashes the member roots into this claim's own root, so the
assembly claim moves when any member moves, and (b) materializes the
members' owned outputs into the gate's working tree before the gate runs.

This is the complement of `2026-10-15-layer-local-audit-deep.md`: that
proposal pushes obligations *down* to the layer that can steer; this one
gives obligations that only exist at composition a room that legitimately
owns them. Together they make item 1 total — every criterion has exactly
one home.

### Acceptance

- The campaign's hand-built assembly checks (`test_measured_cost_boundary`,
  `test_override_protocol`, `test_abstract_refusal`) re-expressed as one
  assembly claim, passing against the shipped tree and refusing the
  recorded diverging rebuilds.
- Editing any member claim moves the assembly claim's root.

---

## 3. Declared-shape divergence for digested series

### The measurement

The run claim digests each metric series over its `(step, value)` pairs,
and the subject's logger stamps a global per-stage step. The campaign's
A66 fix added two warmup-evaluation rows — values identical everywhere —
and the global counter relabeled every later row, so a two-row, declared,
correct change read as near-total divergence: most series digests moved
while the underlying measurements did not.

Telling "declared fix" from "drift" required a schema-aware comparator
built outside the tool — preserved verbatim alongside this proposal as
`compare_v2.py` — classifying each series as `identical` /
`prefix-added` (A66's signature) / `rows-inserted` (A31's signature,
checked as ordered-subsequence so the join is the row's own content, not
the global counter) / `wall-clock` / `DIFFERENT`, the last being the only
category that indicts a rebuild. With it, the regrown
package's divergence over three examples reduced to exactly the declared
fixes and the original's own run-to-run noise — zero unexplained. Without
it, the digest verdict was unusable for any rebuild that fixes anything.

### The proposed obligation

A transition (the `docs/transitions.md` machinery is the natural home)
should be able to declare the **shape** of an expected divergence, not
merely that one is expected: which surface, which class
(`prefix-added`, `rows-inserted`, value-change at named keys), and the
join key under which everything else must still match exactly. The
crosscheck then verifies the shape — rows outside the declaration must be
identical under the declared join — instead of reporting a flat digest
mismatch that the receiver must re-derive by hand.

A smaller, immediately adoptable lesson for authoring guidance: digesting
a series under a global counter couples every criterion to every earlier
row. Prefer content-keyed or stage-local-indexed digests in new run
claims; the global-counter form made one two-row fix cost a full
reference regeneration, twice.

### Acceptance

- A transition declaring "rows-inserted, stage `eval`, join on
  `(stage, event_id)`" over the A66 reference data verifies green, and
  the same declaration over a genuinely value-divergent tree refuses,
  naming the first row outside the declared shape.

---

## 4. A carried class: files that ship but are never regrown

### The measurement

Two losses in the replacement-grade rebuild were not behavioral and so
fell through every gate:

- Prose. The regrown `config/configuration.py` is 403 → 219 lines, almost
  entirely docstring loss — the one module that came back worse-documented
  than the original, because no criterion can (or should) pin prose.
- Non-code assets. Swapping the regrown package in deleted `deployment/`,
  `profilers/README.md`, and a `.gitkeep` — nothing owned them, so
  nothing shipped them. They were restored by hand, byte-for-byte from
  the original (branch commit `249973d`).

Both are the same hole: the class vocabulary offers *generated*
(regrowable, outside the root) and *pinned/validated* (hashed, inside the
root, but semantically an input or a verdict). There is no class for a
file that is part of the shipped artifact, hashed into identity, and
copied verbatim at rebuild rather than regrown.

### The proposed obligation

`class = "carried"` on a `[[step]]` output: hashed into the root like a
pinned input, excluded from producer regrowth, materialized byte-for-byte
into the shipped tree at rebuild. `pack` should offer to classify files
it finds in the subject tree but cannot attach a behavioral criterion to
as carried, rather than silently leaving them outside every claim — the
deletion above was silent precisely because pack had no bucket for them.

### Acceptance

- A rebuild of a claim carrying `deployment/` reproduces it
  byte-identical without the producer seeing a guidance step for it.
- Mutating a carried file moves the root.

---

## Suggested order

1 (audit-side) is pure addition with a working prototype — land first.
4 is a small format addition with an unambiguous witness. 2 and 3 are
design work; 2 should precede 3 only if the assembly claim becomes the
home of run claims' reference data, otherwise they are independent.
Items 1 (seal-side), 2, and 4 are format-bearing: batching them under one
format bump costs one re-seal instead of three.
