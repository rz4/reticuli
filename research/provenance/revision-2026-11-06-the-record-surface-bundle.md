# revision 2026-11-06 — the record surface bundle

    f419e409dfaada9d0eba77014aac51853193421eebe2521b39f0ba9d682937b1
 -> 358edfc8de6e59c08becdbbed46e35d86ec166a0b94e8780b498cdc54b757d27

*An identity-bearing transition. The boundary moved because the record
reader was swept across a population of implementations that had all earned
`f419e409`, and came back with five behaviours nothing tested. A second
division, on the recipe reader, was found by hand afterwards. The sweep
entries are in `zeta/queue/descendants/`.*

## Why identity had to move

A root names an equivalence class of implementations that pass the criteria.
Everything inside that class is supposed to be substitutable. The class is
only as tight as the criteria, so every behaviour the criteria do not test is
a direction in which two members of one class may differ — and a consumer
that depends on such a behaviour is depending on something the root does not
promise.

`spec/record.md` already said this, in a paragraph written after it had
already happened once:

> This paragraph exists because it was missing. On 2026-10-14 four
> implementations that had all earned the same root were asked to
> canonicalize a document that was not a JSON object: two produced bytes and
> a digest, two refused. The root could not say which was correct, because no
> criterion tested it.

The prose was written and the criterion was not. So the surface stayed
untested, and on 2026-11-05 the same thing happened again on the same
reader — which is the argument for this transition. A lesson recorded in
specification prose and not in a gate is not retained.

## The population

Six implementations had earned `f419e409`:

| member | tool that built it | producer that wrote it |
|---|---|---|
| shipped | — | authored |
| `r34` father | codex | codex |
| `r36` father | claude | claude |
| `A` child | codex | claude |
| `B` child | claude | codex |
| `D` child | claude | claude |

The fathers are first-generation blind rebuilds from `f419e409`. The children
are second-generation: regrown from the same blind boundary by one producer,
with a *regrown* tool doing the materializing, jailing, sealing and root
computation. A fourth child, codex-tool/codex-producer, died to a provider
usage limit and is recorded as refused rather than quietly dropped.

**The sweep did not see all six.** By 2026-11-05 the registry had already
retired both fathers, so `zeta` swept four members — the authored tree and
the three children — on six pressures against the record reader. Every
number below says which set it was measured over, because the two sets give
different counts and conflating them is how the first draft of this record
came to overstate the evidence.

## What the sweep found

Over the four swept members: five agreements and one split.

The five agreements are now pinned in `criteria/record_surface_check.py`.
Pinning an agreement evicts nobody — every current member already behaves
that way — and that is the point: it converts a coincidence into an
obligation before a future reconstruction fills the silence differently.
They are that `record_validate`, `record_canonical` and `record_digest` each
refuse a document that is not a record; that the canonical bytes round-trip;
that the digest is 64 hex characters; and that it is deterministic.

### The split: `record_validate` returned nothing

Of the four swept members the three children returned the validated
document; the authored tree alone returned `None`. Widening to all six
implementations afterwards, both fathers return it too, so the ruling runs
five reconstructions to one.

Ruled **in the direction the reconstructions took**. The reader family is
otherwise uniform — `record_canonical` returns bytes, `record_digest` returns
a digest, `record_read` returns the document — and a validator returning
nothing was the one member of it that could not be chained. The change breaks
no caller, because no caller can consume `None`. Here the reconstructions
were simply right and the authored tree was the outlier, which is the
cheapest kind of finding to act on.

### The division the sweep missed: `[record]` as a recipe table

No pressure in the sweep probes the *recipe* reader, only the record reader.
This one was found by hand and then measured across all six: two
reconstructions accept a recipe whose only table is `[record]`, four refuse
it. Ruled **against the accepting pair**: `[claim]` is the only spelling.

That the sweep could not have found it is itself a result. A battery aimed at
one reader certifies one reader, and the comfort of five clean agreements
said nothing about the surface next door.

The ruling is not the interesting part. **Which** two accepted is:

| | accepts `[record]` | refuses |
|---|---|---|
| codex-produced | `r34`, `B` | — |
| claude-produced | — | `r36`, `A`, `D` |
| authored | — | shipped |

Both codex-produced trees accept it. None of the three claude-produced trees
do. The division is clean by producer, measured 2026-11-06 across all six
members.

A 2-of-5 minority is a weak basis for pinning anything. A minority that is
*exactly one producer's output* is not a minority at all — it is one reading
of ambiguous prose, held by however many trees that producer happens to have
been asked to make. Sample it more and the count moves without the evidence
moving. This is the producer fingerprint, already measured as a similarity
effect (codex-produced trees sit at 0.40–0.47 pairwise against a 0.017–0.048
cross-producer baseline), showing up in *semantics* rather than in form.

The practical consequence is a counting rule, and it is the lasting result of
this transition: **implementations by one producer are not independent
witnesses.** Six members read as six votes and are not. Where a division
falls along producer lines, the honest conclusion is that the specification
is ambiguous, not that the majority is correct.

So the prose was fixed rather than the count being trusted. The ambiguity was
real: `spec/claim-format.md` carried the filename legacy (`claim.toml` stays
readable, and the kernel carries `LEGACY_RECIPE` for it) as an annotation
next to the table rule, close enough to read as symmetric. It is not
symmetric, and the asymmetry is now stated outright: **the filename is
outside the root preimage and the table name is inside it**, so a reader
accepting both spellings would compute one root for two different documents.
That is an identity defect, not a convenience.

## What moved

- `criteria/record_surface_check.py`, new and pinned. The five agreements and
  both rulings. Its path resolution is deliberately relative —
  `SRC = "src" if os.path.isdir("src/reticuli") else "."` — because the
  substituted gate runs in a room whose `src/` holds the implementation under
  test, and the first draft derived an absolute path from `__file__` and so
  reported two reconstructions passing a check they fail.
- `src/reticuli/_kernel/attest.py`: `record_validate` returns the document.
- `spec/claim-format.md`: the filename-versus-table asymmetry is stated
  rather than left to be inferred from an annotation.
- `research/harness/descendants/`, and `zeta`'s `descendants` population, so
  the children are addressable by name instead of by path.

## What this evicts

`r34`, the codex father, no longer re-earns. It accepts `[record]`, so the
substituted gate refuses it by name. It stays on disk as a control rather
than being deleted, and
[`research/harness/closure/outside.md`](../harness/closure/outside.md) now
directs an outside operator to `r36` and explains why `r34` fails, so a
failure there reads as the eviction working rather than as a broken trial.

`r36`, the claude father, still re-earns at the new root.

This is the first time a boundary change has evicted a member of its own
population. It is worth being plain that this was the intended behaviour and
not a cost: a criterion that could not evict anything would not be testing
anything.

## A gap this leaves open

`spec/record.md` was **not** touched. It still carries only the 2026-10-14
lesson quoted above, so the five agreements and the `record_validate` ruling
are now pinned in a criterion that no specification prose describes.

Identity is unaffected — the criteria *are* the blind boundary, so a
reconstruction is handed the obligation whether or not the spec spells it
out. But the asymmetry is the same one this project keeps rediscovering in
the other direction: last time the prose existed and the criterion did not,
and the lesson was not retained. Now the criterion exists and the prose does
not, and a human reading `spec/record.md` to learn the reader's contract will
not find it.

Writing it down moves the root again, because `spec/` is inside the preimage.
That is a boundary change and belongs to its own transition rather than being
smuggled into this one, so it is recorded here as owed rather than done.

## What this does not establish

The closure count returns to **0 of 3**. Condition 7 resets it on any adopted
boundary change, and this is one. Condition 5, an outside operator, remains
unmet — and nothing here addresses it, because every run above was ours.

The sweep tested the record reader over four members on six pressures. It
says nothing about the surfaces nobody thought to sweep — the recipe reader
being the case in point, since the division there was found by hand and not
by the battery. The honest reading of two findings on adjacent readers inside
one month is that there are more, and that the next one will also be found
the slow way unless the pressures are widened.
