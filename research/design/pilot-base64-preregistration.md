# Pilot pre-registration: base64, to shake down the instrument

**Status: proposal, forward-looking. A throwaway pilot of the contraction
experiment in [`authority-and-basin-contraction.md`](authority-and-basin-contraction.md),
run on base64 to prove the measurement machinery before a deeper subject (A or
B) carries the real curve. Constants below are proposed; freezing them is the
keyholder's act, and it opens generation 0. Once frozen they are not changed
after data is seen — changing one restarts this pre-registration on the record.**

## Purpose, and what "pilot success" means

This pilot is not expected to produce a deep contraction curve. base64 has a
shallow disagreement surface, so it will likely go dry after one to three
generations — that is the point. The pilot succeeds if the **instrument** works
end to end:

- every frozen metric computes from real rebuilds (`R`, `S`, `D`, `U`, `A`,
  `Y`, `Y*`, `K*`);
- the differential harness builds a disagreement matrix and the reducer turns a
  disagreement into a minimal witness;
- a generation's accepted counterexamples become a `ΔC` that the keyholder can
  sign, moving `C_0` to `C_1` under the authority invariant;
- at least one contraction step (`S` preserved, a behavioral disagreement
  closed) is observable and recorded in `research/provenance/`.

A dry curve after that is a pass, not a failure. What would fail the pilot is a
metric that cannot be computed, a reducer that cannot minimize, or a `ΔC` the
harness cannot express — machinery holes to fix before spending a real subject
on them.

## Subject

**base64 as defined by RFC 4648**, standard alphabet, `=` padding. A claim
whose implementation is `encode(bytes) -> str` and `decode(str) -> bytes`.

## The partial boundary `C_0`

`C_0` specifies the happy path strongly and **deliberately leaves the strictness
surface unspecified**, so reconstruction and adjudication rediscover the
omissions rather than reading them off a complete RFC.

**Specified (in `C_0`):**

- round-trip: for every byte string `b`, `decode(encode(b)) == b`;
- `encode` emits the standard alphabet `A–Z a–z 0–9 + /` with `=` padding to a
  multiple of four;
- the RFC 4648 §10 vectors, exactly: `"" → ""`, `"f" → "Zg=="`,
  `"fo" → "Zm8="`, `"foo" → "Zm9v"`, `"foob" → "Zm9vYg=="`,
  `"fooba" → "Zm9vYmE="`, `"foobar" → "Zm9vYmFy"`.

**Left unspecified (the omissions the ratchet will surface as disagreements):**

- decode of input containing whitespace or newlines (MIME 76-column wrapping);
- decode with wrong, missing, or excess `=` padding;
- decode of **non-canonical** final quanta (final bits that a strict encoder
  would never emit, e.g. `"Zg=="` vs an overlong form);
- decode of characters outside the standard alphabet, including the URL-safe
  `- _` pair;
- whether `decode` on malformed input raises, truncates, or best-effort skips.

Each unspecified item is a place two conforming-to-`C_0` implementations can
diverge. `C_0` is frozen before any rebuild runs.

## Mechanical oracle and probe distribution `X`

The oracle needs no model in the loop:

- **round-trip** `decode ∘ encode = id` — generates happy-path disagreements
  automatically over random byte strings;
- **differential** — every surviving implementation is run against `X`, and any
  input on which two implementations produce different results (value, or
  raise-vs-return) is a candidate disagreement.

`X`, frozen at generation 0 and extended only by accepted counterexamples:

1. a fixed seed corpus — the RFC vectors, plus a hand list of malformed decode
   inputs covering each unspecified item above;
2. a seeded fuzzer, frozen seed set `0..999`: random byte strings for the
   encode round-trip, and random strings over `alphabet ∪ {whitespace, =, -, _,
   out-of-alphabet}` for decode strictness;
3. the property inputs (round-trip) themselves.

## Frozen constants (proposed — ratify before generation 0)

| constant | proposed | meaning |
|---|---|---|
| `k` | 8 | independent blind rebuilds per generation |
| producer families | codex, anthropic | the reconstruction set (see budget note) |
| held-out family | openai | reserved for the control; participates in no ratcheting or authoring |
| `ε` | 0.05 | accepted-disagreement yield `Y*` counted as converged |
| `K` | 2 | consecutive converged generations to stop |
| `N` | 4 | falsification patience (F1) |
| `δ` | 0.40 | structural-distance floor, or a cluster floor of 3 |
| `τ` | 0.30 | clustering threshold on `d_struct` |
| `d_struct` canonicalizer | strip comments + whitespace, normalize identifiers, then token-level normalized edit distance | so the metric sees structure, not surface |
| fuzzer seed set | `0..999` | frozen; extended only by accepted counterexamples |

## The disagreement pipeline

    rebuilds (survivors of C_n's gate)
      → run each against X
      → disagreement matrix M[i][j] = fraction of X where impl i, j differ
      → collect divergent inputs, reduce each to a minimal, partition-preserving
         witness, and group by partition into one class per question
      → novelty filter: drop questions C_n already decides, and classes whose
         representative witness was seen in a prior generation
      → keyholder adjudicates each class: irrelevant | already-specified | counterexample
      → accepted counterexamples → ΔC → keyholder signs (reticuli.boundary) → C_{n+1}

Each generation's rebuilds, matrix, minimal witnesses, adjudications, and the
signed `ΔC` are written to `research/provenance/` in order. The instrument is
`research/harness/contraction/`, self-tested on hand-written fixtures with no
producer spend.

### Refinements the shake-down forced (part of what gets frozen)

The self-test over the fixtures changed three definitions from the first draft.
Freezing the constants freezes these too:

- **A disagreement is a partition, not a string.** Its identity is the
  who-agrees-with-whom split over the survivors, so near-duplicate inputs
  collapse to one question and one adjudication. (Deduping by exact minimal
  witness counted `!`, `*`, `+` as three questions — 433 of them; by partition,
  7.) Cross-generation dedup is by the class's representative witness string,
  which is population-independent.
- **The reducer preserves the partition.** It shrinks a witness only while the
  same split holds, so a URL-safe question does not decay into a generic
  junk-character one during minimization.
- **Rejection is rejection.** The canonical outcome collapses every exception to
  one "rejected" token; a different exception *type* is not a behavioral
  distinction, and counting it as one made two strict decoders look maximally
  divergent.

The instrument also raises the structural-collapse alarm (F3, `S → 0`) when an
adjudication would eliminate too many implementations — which is why a real
keyholder, like the simulated one, guards the structural floor when accepting.

## The held-out control

After the pilot appears converged, hand `C_n` to the held-out family (openai),
which participated in neither ratcheting nor authoring. It passes only if it
(1) reconstructs a structurally distinct valid implementation (distance to the
population ≥ `δ`) **and** (2) surfaces no new human-relevant disagreement.
Failing either fires F2. On a pilot this mostly proves the control *procedure*
runs.

## Budget note

Reconstruction favors the **un-metered codex producer** (ChatGPT plan, not the
metered OpenAI API), so the pilot does not draw on the metered budget. anthropic
rounds out a second family. The held-out **openai** family is metered; running
it — like any paid producer beyond standing authorization — is the keyholder's
call, requested explicitly when the control step is reached, not started
implicitly by the harness.

## Decisions

- **Subject: base64 (RFC 4648), standard alphabet.** Chosen as the pilot for
  its tight determinism and external ground truth; expected to dry fast, which
  is acceptable for an instrument shake-down.
- **`C_0` is deliberately partial.** The strictness surface is unspecified on
  purpose, so the ratchet discovers it.
- **Constants pending ratification.** Freezing the table above is the
  keyholder's act and opens generation 0.

### Open (to be filled by the keyholder)

- Ratify or adjust the frozen-constants table.
- Confirm the producer families and the un-metered-first budget posture.
