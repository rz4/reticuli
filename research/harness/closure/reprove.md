# The reprove for 358edfc8: the grandfather crosschecks the grandchildren

*The accept bar for this boundary, written before anything is spent against
it. Research tooling — not normative, not pinned.*

## The shape

Step 4 of the transition ritual asks for an independent blind rebuild from
the new boundary. For the `358edfc8` boundary the keyholder set the bar as a
single structure rather than three loose trials:

**The grandfather crosschecks the four grandchildren.**

The lineage the bar is named over:

| generation | who |
|---|---|
| grandfather | the authored tree on `main` |
| fathers | `r34` (codex), `r36` (claude) — first-generation blind rebuilds |
| grandchildren | `A`, `B`, `C`, `D` — second generation, one per tool×producer cell |

The grandchildren are the four combinations of which family's *regrown tool*
does the materializing, jailing, sealing and root computation, and which
family's *producer* writes the implementation:

| id | tool | producer |
|---|---|---|
| `A-codexTool-claudeProd` | codex | claude |
| `B-claudeTool-codexProd` | claude | codex |
| `C-codexTool-codexProd` | codex | codex |
| `D-claudeTool-claudeProd` | claude | claude |

## Why `crosscheck` is the right verb

`ret crosscheck` is strictly a three-machine test: M1 an original, M2 a
byte-reuse that travelled by content, M3 an independent redo. Root equality
is identity, not soundness, so every leg re-earns its own verdicts on its own
bytes. Given three or more realizations the command treats the extras as
further rebuilds and tests each.

That maps onto this lineage exactly:

- **M1** — the grandfather, the authored tree. One original, not four.
- **M2** — a byte copy of the grandfather, so the reuse leg is genuine
  byte-reuse rather than a second redo that merely lands the same root.
- **M3** — each grandchild in turn.

Four judgements from one authored original is what "made by the grandfather"
means operationally: the grandfather is the fixed point of comparison and
never one of the things being compared.

## What must be true before it runs

**1. The grandchildren must be regrown from `358edfc8`.**

The three that exist earned `f419e409`. Judging them as they stand would not
be a reprove, it would be an eviction test, and its outcome is already known
from measurement: the `[record]` ruling divides the population cleanly by
producer, so both codex-produced grandchildren fail the new criterion.

| grandchild | producer | `[record]` | judged at `358edfc8` as it stands |
|---|---|---|---|
| `A` | claude | refuses | passes |
| `B` | codex | accepts | **evicted** |
| `C` | codex | not built | predicted evicted |
| `D` | claude | refuses | passes |

A reprove has to start from the new blind boundary. `room/reticuli` now
publishes `358edfc8`, which is what makes that possible.

**2. `C` has to exist.**

`C-codexTool-codexProd` died to a provider usage limit during the
`f419e409` campaign and is recorded as refused rather than quietly dropped.
A bar named over four grandchildren is not met by three.

**3. The cost is four producer sessions**, two of them codex — which is the
cell that hit the limit last time, and the reason `C` is missing.

## What this bar establishes, and what it does not

It establishes membership per **condition 3**: the full conformance gate
rather than a sampled subset, with `ret verify` and `ret crosscheck` in it.

It spans two model families, which is the half of **condition 7** about
family coverage. The other half — that no boundary change intervenes — is
what resets the count, and this bar is being written because one just did.

It does **not** cover **condition 4**, the recursive step: each regrown tree
must itself perform the pinned reconstruction through its own command line,
from a blind room, landing that claim's root. A tree that passes every suite
but cannot reconstruct is a decoy rather than a member, as the `r4` tree
was. That leg is separate work and `trial.py` is where it lives.

It does **not** cover **condition 5**. Every run in this bar would be ours,
on our machines, under our accounts. The outside re-earn remains the one
piece of evidence we cannot manufacture, and
[`outside.md`](outside.md) is its protocol.

And it does not establish that four rebuilds are four independent witnesses.
Two share the claude producer and two share the codex producer, and the
2026-11-06 measurement is the reason to care: the `[record]` division fell
exactly along producer lines, and the producer fingerprint is measurable in
form as well (codex-produced trees pairwise 0.40–0.47 against a 0.017–0.048
cross-producer baseline). Four cells across two producers is better coverage
than four samples from one. It is not four votes.
