# Three thresholds: from research record to reconstruction platform

*2026-10-05. Strategy note, from the keyholder's framing. Not
normative; nothing here moves a root.*

## The ladder

1. **Research value** — the machinery finds specification gaps that
   ordinary tests missed. STATUS: demonstrated, on reticuli itself
   (the closure criterion's history-validated latent gaps; the silence
   maps' seams under green tests and green CI; cross-judging finding
   the parent minting identities no criterion judges). Small system,
   real result.
2. **Engineering value** — the discoveries make successive independent
   implementations measurably more compatible: the contraction curve
   on an external system. INSTRUMENT: the jq experiment
   (jq-negative-space-experiment.md).
3. **Commercial value** — someone hands over a real system they need
   to replace, migrate, audit, or preserve, and the machinery
   materially reduces the human effort of recovering its behavioral
   contract. Threshold 2, shown convincingly (eventually: SQLite),
   makes 3 an inference rather than a pitch.

The reframe at the top of the ladder: not a research-record format but
a **behavioral specification compiler** — implementation in,
executable regenerable specification out, with the differences between
regenerations driving the specification's own repair.

## What the existing measurements contribute

- **Unit economics.** Contract recovery costs ~300× verification;
  verification transfers at ~44,000× by signature
  (thermo_report.json). So the expensive act happens once per system
  and its product is durable and nearly free to re-verify forever. The
  revenue shape is the standing boundary, not the one-time rebuild:
  continuous semantic-equivalence CI holding every future change to
  the recovered contract. The rebuild is onboarding; the boundary is
  the subscription.
- **The register is the deliverable.** "What you forgot to specify" is
  unpriceable while invisible; the silence map's consumption tiers
  turn it into a document — N exhibited-but-unspecified behaviors, the
  k something stands on, a witness for each. For M&A diligence and
  regulated replacement, that register plus the signed chain of
  specification repairs is what an auditor can actually read. The new
  implementation is almost a byproduct.
- **The blind room is a machine-enforced clean room.** Rooms provably
  never containing the original source, ledgered inputs, tamper
  snapshots, replayability — documentation of independence that
  hand-run clean rooms produce only as procedural theater. Caveat with
  a legal twin: for famous systems the room is clean but the
  producer's training memory is not; for proprietary internal systems
  — the actual market — the claim is clean on both axes, and real
  traffic makes the consumed tier measurable from production call
  sites instead of inferred.

## The direct uses (the keyholder's list, kept verbatim in spirit)

Legacy modernization; vendor replacement; language/runtime migration
with continuous equivalence checking; M&A software archaeology;
verification beyond coverage; regulated-software replacement evidence;
long-term preservation of the contract rather than the implementation.
The common economic fact underneath: organizations hold decades of
code they do not want — an expensive, fragile encoding of an implicit
specification. The proposition: *give me the old system; I will tell
you what behavior actually matters, what you forgot to specify, and
whether a completely different implementation can safely replace it.*

## The honest hard part

The modernization market's real difficulty is not expression semantics
but behavior entangled with environment: timing, concurrency, crash
recovery, durability, platform quirks. jq is clean input→output;
SQLite's contract includes what survives a power failure
mid-transaction, and gates for THAT are a research problem (fault
injection as criteria — SQLite's own anomaly testing shows both that
it is possible and what it costs by hand). This is the real reason
SQLite is step 4 rather than step 2: the progression is ordered by how
much of the contract is functional, not by code size. Do not skip
thresholds; jq first.
