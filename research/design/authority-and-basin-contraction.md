# Authority and basin contraction: an invariant to adopt and an experiment to pre-register

**Status: proposal, forward-looking (this wing is proposals, not normative).
It contains two things meant to outlive it. The first is normative text ready
to adopt into `GOVERNANCE.md`; adopting it is a keyholder's act, not this
document's — the invariant governs its own promotion. The second is the
pre-registration of an experiment: its predictions, its metric definitions,
and the thresholds that would end it, all fixed here before it runs so the
result cannot be argued into existence afterward.**

## What this proposes, and why now

Reticuli's root names a boundary, not a program: the SHA-256 is over the tests
and recipe, and the implementation is left out, so the root names every program
that passes this exact check on this exact data. An independent rebuild is
therefore a sample from the set of programs the boundary admits — call it the
claim's **reconstruction basin**. Two questions follow, and the rest of this
document is about keeping them separable:

- **How wide is the basin, and does it narrow the right way?** A good boundary
  admits implementations that differ freely in structure while agreeing on the
  behavior that was specified. Tightening it in response to observed
  disagreements should shrink the behavioral spread without shrinking the
  structural spread. That is a measurable claim, and Part B pre-registers the
  measurement.
- **Who is allowed to move the boundary?** If reconstruction and
  disagreement-finding become cheap, the one scarce step is deciding which
  discovered disagreements change what the software is supposed to mean. That
  decision must never be made by the thing being evaluated. Part A states the
  invariant that keeps it out.

The order matters. The invariant is cheap to state now, while the only agent
that could bend it is a cooperative one operating the ratchet by hand. It
becomes ambiguous the moment recursive machinery exists to bend it. So it is
written first, and the experiment that would justify building that machinery is
gated behind it.

## Standing and the public claim

Nothing here changes the public claim, and it should not until the experiment
in Part B has produced evidence across independent subjects and producers.

The load-bearing pitch stays **criteria-reproducibility**: an independent
machine reconstructs an implementation *that satisfies the same criteria* — not
the same bytes. This is the honest floor. It is what the tool already
demonstrates, and it is easy to falsify: point a second machine at the boundary
and see whether `crosscheck` earns one root. The word to avoid in public is
"reproducible" left bare, because it invites the byte-for-byte reading that
reticuli deliberately does not make (generated source is outside the root).

The stronger reading — that the boundary is a durable object from which
implementations are regenerated on demand, code as exhaust — sits one layer
down as the **hypothesis under test**, not the claim. Promoting it to the
README is itself a boundary move, and under Part A it waits on a human
authority event backed by the evidence Part B is designed to produce. If that
evidence arrives, the rewrite writes itself: *reticuli preserves software by
preserving what must remain true, not the code that happened to make it true.*
Until then that sentence stays in this wing, where the lineage lives.

---

## Part A — The authority invariant

### The invariant

> **No produced artifact may authorize its own promotion into the normative
> boundary.** An agent, a reconstruction, an evaluator, or an adversarial
> producer may propose anything — a test, a counterexample, an amendment, a
> complete candidate boundary. Moving the accepted boundary from one identity
> to the next requires an authority event external to the reconstruction being
> evaluated: a keyholder's signature over the specific boundary delta.

This is a strengthening of a rule `GOVERNANCE.md` already states — *a signature
over a moved root is a keyholder's act, never an agent's* — generalized from
"the agent did not sign" to "nothing the loop produced can be the thing that
ratifies the loop's own output."

### It blocks collusion, not only self-promotion

"Its own promotion" is too narrow read literally: artifact A could propose a
delta that promotes B while B proposes one that promotes A, and neither would
have promoted *itself*. The invariant therefore binds to the **reconstruction
machinery of a generation**, not to a single artifact. Authority is a distinct
principal — the human keyholder — and the promotion event is that principal's
signature over the boundary delta. External to the reconstruction, not merely
external to one of its outputs. A producer, an evaluator, and an adversary are
all inside the machinery; a keyholder is the only thing outside it.

### It binds to the signing ceremony that already exists

The record spec already separates signatures by purpose into their own
namespaces so that a signature made for one purpose cannot be presented for
another: `reticuli` for attestation, `reticuli.record` for results,
`reticuli.mint` for authorizing an implementation. Boundary promotion is a
fourth purpose — authorizing a *criterion change*, not an implementation — and
by the same principle it takes its own namespace, proposed here as
**`reticuli.boundary`**. A signature in that namespace covers the boundary
delta: the changed criteria bytes together with the old→new root pair. Minting
that namespace and wiring a verb to it is deferred enforcement (see below); the
namespace is named now so the design is settled before the machinery lands.

The machine/human split the sign-family fold left in place is exactly the
substrate this needs. Machine artifacts propose and attest (`record`,
`attest`); the human ceremony authorizes (`sign`). The invariant adds one rule
to that split: **boundary promotion is a `sign`-class act, never a `record`- or
`attest`-class one.**

### What it governs today

The invariant is not a future concern. Today an agent operating the ratchet
edits `criteria/`, updates the pinned lockfile in `criteria/self_check.py`,
reseals, and re-earns the gate. Under this invariant that agent is
**proposer and operator, never authority**. The mechanical work — the edit, the
reseal, the re-earn — may be an agent's; the transition from one accepted
boundary to the next is not accepted until the keyholder signs the moved root.
A generated implementation that both satisfies a criterion *and* rewrites the
criterion it satisfies, in one self-authorizing step, is the exact thing this
forbids — even when the change is a small usability tightening, and even when
the agent did every keystroke cooperatively. The point of stating it while the
only such agent is cooperative is that there is then nothing to negotiate with.

### Proposed normative text for `GOVERNANCE.md`

To be added under "How changes are decided", adoption pending a keyholder's
act:

> **The authority boundary.** Anything the reconstruction loop produces —
> implementations, evaluations, counterexamples, proposed amendments, candidate
> boundaries — is a proposal. Promoting the accepted boundary from one root to
> the next is an authority event external to that loop: a keyholder's signature
> over the boundary delta (the changed pinned inputs and the old→new root
> pair), in the `reticuli.boundary` namespace. No produced artifact may
> authorize its own promotion, and no set of artifacts from one generation may
> authorize each other's. An agent may perform every mechanical step of a
> transition; the transition is not accepted until the keyholder signs.

### What "enforce later" means

Adopting the text above is a documentation act with a signature behind it, not
a root move. **Mechanically enforcing** it — minting the `reticuli.boundary`
namespace, adding the verb that verifies a promotion signature, and having the
gate refuse a boundary move that lacks one — edits pinned surface and so is an
identity-bearing transition under the existing procedure. That work is deferred
until the experiment in Part B justifies the recursive machinery it protects.
Stating the invariant costs nothing and constrains the machinery's design;
building the enforcement before there is anything to enforce would be premature.

---

## Part B — The contraction experiment (pre-registration)

### Hypothesis

Repeated independent reconstruction, followed by incorporation of only
human-accepted disagreements, contracts a claim's basin **on behavior while
preserving it on structure**. Formally, across generations `n`:

    accepted-disagreement yield  Y*(n)  →  0
    behavioral diversity         D(n)   ↓
    structural diversity         S(n)   stays > δ
    reconstruction success       R(n)   stays high

The third and fourth lines are what separate the hypothesis from its trivial
cousin. A boundary can be made reconstructible by collapsing every producer
onto one implementation; that is reproducible source generation wearing the
basin's clothes. The claim is only interesting if behavioral agreement rises
*while structural disagreement remains*.

### Subjects

Two subjects, because each answers a question the other cannot.

- **Reticuli itself** — the legible, recursive, brutally relevant engineering
  demonstration. Its weakness as *science* is contamination: the specification,
  implementation, tests, and reconstruction machinery co-evolved, and enormous
  effort has gone into this exact problem, so a clean curve here could be an
  artifact of the tool's own structure.
- **One external subject** — scientifically necessary, and deliberately not
  designed around reticuli's worldview. Selection criteria, fixed here:
  1. small enough for 20–100 independent rebuilds at tolerable cost;
  2. semantics nontrivial enough that disagreements are interesting;
  3. deterministic enough that a disagreement is interpretable, not
     environmental;
  4. admits a **mechanical oracle** — a property or invariant that generates
     disagreements without a model in the loop (see "Why a mechanical oracle");
  5. unrelated to reproducibility, specification, or reticuli's own concerns.

  The subject is an **open slot**; the shortlist is decided with the keyholder
  before generation 0 and recorded in the Decisions block. Whatever is chosen,
  its boundary is frozen as `C_0` before any reconstruction runs.

### Why a mechanical oracle

The scientific weak point is disagreement *discovery*, not reconstruction. If
models find the disagreements, the disagreements the models are blind to go
unmeasured, and that gap is invisible in every metric below. The fix is a
disagreement generator with no model in it — a round-trip or property invariant
the subject must satisfy (`parse ∘ format = id`, an algebraic law, differential
comparison against a reference format). The human then only ever *adjudicates*
disagreements, never *discovers* them. This is why criterion 4 is not
negotiable, and why property-rich subjects (parsers, codecs, calculators) are
preferred over open-ended ones (interpreters, general utilities).

### One generation of the loop

    C(n)
      → reconstruct        k independent blind rebuilds, heterogeneous producers
      → find disagreements mechanical oracle + adversarial probes over the survivors
      → adjudicate         keyholder classifies each: irrelevant | specified | counterexample
      → promote            accepted counterexamples become ΔC; keyholder signs (Part A)
      → C(n+1)             freeze; quarantine the generation's implementations
    repeat

Implementations are intermediates. They may be discarded after each generation;
the persistent state is the boundary and its accepted-counterexample history,
recorded per generation in `research/provenance/`. This reuses existing
machinery: reconstruction is `rebuild` across the producer set, the cost block
of each `record` supplies `K*`, and per-generation measurements accumulate in
`research/corpus/` beside the assess population.

### Frozen metric definitions

Frozen here so none is defined after seeing data. Every distance, canonical
form, and input set below is fixed at generation 0 and changed only by an
accepted counterexample, never re-rolled.

| symbol | name | definition (frozen) |
|---|---|---|
| `R(n)` | reconstruction success | fraction of independent blind rebuilds at generation `n` that pass the frozen gate. "Independent" = distinct producer run; the heterogeneity dimensions (model family, seed, language where permitted, prompt) are logged per rebuild |
| `S(n)` | structural diversity | mean over accepted pairs of `d_struct(p_i, p_j) ∈ [0,1]`, where `d_struct` is normalized token-level edit distance over a **canonicalized** form of the generated source (comments and whitespace stripped, identifiers normalized) — blind to naming, so it measures structure, not surface. Reported alongside a cluster count at threshold `τ` |
| `D(n)` | behavioral diversity | mean over accepted pairs of `d(p_i, p_j) = Pr_{x∼X}[f_i(x) ≠ f_j(x)]`, where `X` is the frozen probe distribution below |
| `X` | probe distribution | the external subject's mechanical-oracle inputs: a fixed seed corpus (hand + spec-derived) ∪ a seeded fuzzer with a frozen seed set ∪ the property/round-trip inputs. Extended only by accepted counterexamples, so cross-generation numbers stay comparable |
| `U(n)` | novel disagreements | count of minimal disagreement witnesses at generation `n` not already decided by `C(n)` and not equivalent to one counted in a prior generation (equivalence = same minimal witness after the frozen reducer) |
| `A(n)` | accepted disagreements | subset of `U(n)` the keyholder adjudicates as *counterexample* (one side is intended, the other wrong), as opposed to *irrelevant* (both acceptable — legitimate freedom) or *already specified* |
| `Y(n)` | disagreement yield | `U(n) / R(n)` |
| `Y*(n)` | accepted yield | `A(n) / R(n)` — the headline metric |
| `K*(n)` | operational cost | minimum observed producer cost (from the `record` cost block, per unit) to land one valid realization at generation `n` |

No structural metric is perfect; `d_struct` is frozen and reported, and each
cluster additionally carries a one-line human architecture note so a collapse
that the number misses is still visible.

### Pre-registered predictions (success)

The experiment **supports** the hypothesis if, across both subjects:

- `Y*(n)` falls to below `ε` and stays there for `K` consecutive generations,
  across at least two independent producer families; **and**
- `S(n)` stays at or above `δ` (or the cluster count stays ≥ the floor)
  throughout — behavioral agreement is not bought by structural collapse; **and**
- `R(n)` does not fall — reconstructibility is preserved as the boundary
  tightens; **and**
- the held-out control (below) passes.

Proposed constants, **to be frozen by the keyholder before generation 0** (and
never tuned afterward): `ε = 0.05` accepted disagreements per reconstruction;
`δ = 0.40` mean structural distance, or a cluster floor of `3`; `K = 2`
consecutive generations; falsification patience `N = 4` generations.

### Pre-registered falsifiers (abandonment)

The experiment **fails**, and the specification-compiler thesis is not promoted,
under any of:

| # | falsifier | fires when |
|---|---|---|
| F1 | persistent accepted disagreement | `Y*(n)` does not trend down — stays above `ε` after `N` generations of ratcheting. The basin does not contract |
| F2 | producer dependence | apparent convergence disappears when the model family changes, or the held-out producer surfaces a new human-relevant disagreement. We were measuring a shared prior, not the boundary |
| F3 | implementation collapse | `S(n)` falls below `δ` (or below the cluster floor) as `C` tightens — producers herded toward one architecture. The boundary encodes implementation, not behavior |
| F4 | adversarial discontinuity | small changes in probe strategy repeatedly reveal large unexplored disagreement regions. Empirical reconstruction gives little confidence about the unseen basin |
| F5 | judgment instability | independent authorities disagree on accept/reject above a fixed rate. The limiting uncertainty is above the software — itself a finding, and a cap on the whole leverage story |

### The held-out-producer control

After a boundary appears to converge, hand `C(n)` to a producer from a model
family that participated in **neither** the ratcheting **nor** the criteria
authoring — a different family, not a different checkpoint of a participating
one, since checkpoint-siblings share the prior under test. Two conditions, both
required to pass:

1. it reconstructs a **structurally distinct** valid realization (its distance
   to the converged population is at or above `δ`); **and**
2. its adversarial probe against the converged population surfaces **no new
   human-relevant disagreement**.

Condition 1 alone is only diversity. Condition 2 is what says the boundary — not
a shared prior filling the gaps — carried the semantics. Failing either fires
F2.

### Pre-registration integrity

The constants above are frozen by the keyholder before generation 0, in the
Decisions block of this document, and are not changed after any data is seen;
changing a frozen constant ends and restarts the pre-registration on the
record. Each generation's reconstructions, disagreements, adjudications, and the
signed boundary delta are recorded in `research/provenance/` in the order they
happened, so a reader can walk the whole curve from raw rebuilds to the final
boundary. The headline artifact of the experiment is a single plot per subject:
generation against `Y*(n)`, with `S(n)` overlaid.

---

## Decisions

- **Public claim unchanged.** Criteria-reproducibility stays the pitch; the
  specification-compiler thesis stays a hypothesis in this wing until Part B
  produces evidence across subjects and producers. Promoting it is a boundary
  move under Part A.
- **Invariant adopted before machinery.** Part A's normative text is adopted
  into `GOVERNANCE.md` by a keyholder's act; mechanical enforcement
  (`reticuli.boundary` namespace and its verb) is deferred until Part B
  justifies it.
- **Ordering.** Adopt Part A, then run Part B, then build enforcement and the
  closed loop only if Part B's curve contracts on behavior with structure
  preserved.

### Open slots (to be filled with the keyholder before generation 0)

- **External subject** — chosen from the shortlist against the five criteria
  above; boundary frozen as `C_0`.
- **Frozen constants** — `ε`, `δ` (and cluster floor), `K`, `N`, the fuzzer
  seed set, `τ`, and the `d_struct` canonicalizer, ratified and recorded here.
