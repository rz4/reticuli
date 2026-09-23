# Reticuli's future: a cross-family synthesis

*2026-09-22, forward-looking (proposal, not normative). Two independent models —
Claude (Anthropic) and gpt-6-astra (OpenAI, via the codex producer) — each read
the real source and argued the future for a human keyholder to decide. This
records where they converged, where astra sharpened Claude's view, the
recommended next step, and the one bet only an experiment resolves.*

## Converged direction

- **What reticuli is for: credible exit.** A software system can outlive its
  implementation supplier — replace a dependency, its generator, or the whole
  chain while retaining an explicit account of what must remain acceptable.
  *Retain the obligation, replace the supplier, re-earn acceptance.*
- **Ground floor: criteria sufficiency.** Without criteria strong enough to
  admit only acceptable implementations, obligations do not determine software.
- **Deepest risk (structural, not a bug): the specification burden may not
  compress into a useful middle ground.** Weak criteria leave behavior in
  producer conventions and consumer expectations; strong criteria reaccumulate
  the software's own complexity; and once producers optimize against the gate,
  harmless omissions become attractive exploits (Goodhart). The failure it
  produces is governance: *formal ownership of judgment with insufficient
  capacity to exercise it* — the keyholder holds the key while practical
  authority migrates to whoever maintains the criteria.
- **Case against, and the response: economics.** Preserving and patching a known
  implementation is often cheaper and safer than specifying its replaceability;
  the criteria become a second maintained system. Pursue a **bounded research
  bet**, not a universal package ecosystem. Decisive evidence = a useful
  component whose implementation is replaced *repeatedly at lower total cost*
  (criterion maintenance and adjudication included) without downstream
  regressions.

## Five sharpenings astra contributed (accepted)

1. **Substitutability, not AI-regeneration.** A handwritten replacement should
   qualify too; making generation central narrows the idea. The essence is
   credible exit from any supplier.
2. **Sufficiency is consumer-relative.** Two implementations passing the same
   gate are not equivalent — their differences must be irrelevant *to the
   consumer under its declared assumptions*. So contraction should measure
   **downstream failures among gate-passing replacements**, and deliberately
   seek divergent implementations that still pass — not just inter-rebuild
   convergence. (Generalizes the quirkcalc shared-miss result to composition.)
3. **Composition is a versioned identity design, not a plumbing fix.** A parent
   must commit to a dependency's *obligation + the interface it consumes + the
   assumptions under which substitution is permitted*, with evidence separately
   binding the realization actually used — else a stable parent identity conceals
   an unsupported change (registry.py:234).
4. **Adjudication can be delegated within a bounded scope.** A keyholder can
   authorize a procedure to decide routine cases; what cannot silently transfer
   is authority to change the scope, waive obligations, or redefine acceptable
   evidence. Humans concentrate on adopting criteria, changing them, and
   resolving exceptions. (Refinement: the routine/scope boundary becomes the new
   critical surface — where spec-gaming would hide.)
5. **A fourth methodological finding:** `heldout.py`'s explanation treats high
   held-out success as evidence the retained cases *carried* the behavior; that
   causal attribution is too strong (shared conventions and task familiarity can
   fake it). The measurements are useful; the interpretation overreaches.

## Recommended next step

**One adversarial, two-layer substitution demonstrator.** A bounded but useful
dependency (e.g. a structured-data parser) and a real consumer. Produce two
substantially different accepted implementations, one deliberately exploiting
underspecification, and run the parent against both. It must establish:

- swapping the dependency preserves both claim identities;
- realization digests and bound execution evidence change appropriately;
- the consumer stays acceptable on independently designed integration
  challenges;
- a locally-accepted-but-consumer-violating candidate exposes a missing
  obligation;
- directory and record transports enforce identical declared obligations.

Fold the three soundness gaps (A guidance-in-room, B rebuild root-equality,
C crosscheck record obligations; see the essence/soundness audit) in as
prerequisites, and **record criterion-authoring effort and human review time** —
that cost is the decisive evidence. "Another successful blind rebuild would
answer less."

## The one open bet

Does the useful middle ground exist — criteria cheaper than the implementation
yet strong enough for safe, diverse substitution? Not a disagreement between the
two models; the empirical question the demonstrator is designed to answer. If it
exists, reticuli is a new primitive for renewable software. If not, reticuli
remains valuable for durable evidence and accountability, and the stronger
promise stays unproven.

## Industrial economics and IP (cross-family, 2026-09-23)

The keyholder pushed to the industrial framing: recursive specification
improvement used to consolidate industry software, cost falling over time, and
regenerated code "distinct to circumvent copyright." Claude engaged the first
two and declined the third; astra reasoned independently. What the two converged
on:

**The economic lever is adjudication reuse, not generation cost.** The
comparison over a horizon is `S + W + Σ(G+A+M+O+L) < Σ P` — criterion authoring
`S`, spec maintenance `W`, and per-deployment generation `G`, adjudication `A`,
migration `M`, operations `O`, expected loss `L`, versus preserving the incumbent
`P`. Crossover: `N > (S+W)/(P − (G+A+M+O+L))`; a negative denominator means scale
cannot rescue it. **Making generation free recovers almost nothing; adjudication
dominates.** Token cost is the wrong headline. The scarce asset is the
maintained, credible acceptance contract, and whoever governs it holds real
power.

**Value without continual regeneration: credible exit is an option.** Capture
the acceptance contract, keep the working implementation, regenerate only when
the economics turn. Where it pays: parsers/codecs/protocol adapters, and
portfolio-wide rules that amortize. Where patch-the-incumbent wins:
stateful/ERP/DB platforms and experience-heavy products, where compatibility and
integration overwhelm code production. Smallness is not the variable; a compact
contract over a large system is favorable, a quirk-laden tiny integration is
not. "Equivalent" is finite only against a **consumer boundary** (equivalent for
these workflows/SLAs), not "equivalent in every circumstance."

**Recursive spec improvement is real but not automatic.** Stronger ≠ easier:
removing ambiguity (a rounding rule) lowers production cost; adding capability
(crash recovery, isolation) is new work whose cost need not fall. The loop
requires external consumer evidence and a human oracle — a generator improving
its own gate from its own outputs drifts from the consumer's obligation. What
breaks first at scale: the authority/cost of the oracle, composition (component
interfaces must carry retry/ordering/txn/auth obligations or uncertainty just
relocates to integration), and adaptive overfitting to public gates. A real
ratchet means **less expert effort per accepted replacement at maintained
independently-assessed risk** — not more tests, shorter prompts, or lower token
bills.

**IP: the direction holds, the formulations tighten.** Behavior is broader than
function (§102(b) frees methods, not displayed protected content); derivation
does not categorically contaminate everything (*Sega*, *Altai*
abstraction-filtration); *Google v. Oracle* was fair use, not a blanket API
rule; evasion intent is an evidentiary/willfulness point, not a determinant of
underlying legality; trade-secret law expressly protects reverse engineering and
independent derivation (§1839). Replace "provably independent to defend" with
**"documented lawful derivation and bounded evidence of independent
implementation."** Absolute independence is neither provable nor necessary (a
licensed reimplementation can be lawful despite deliberate reuse), and it cannot
cure an unlawfully-obtained spec.

**Reticuli does not yet enforce a provenance wall.** `_materialize` classifies
files, it does not clear rights; `_produce` runs the producer via `_run` with no
filesystem/network confinement and the bundled producer disables its sandbox;
record "blindness" is a relayed declaration; guidance shapes production but is
outside the format-3 root; the record's cutoff-vs-publication contamination check
overreaches (a signature authenticates an assertion, not what the signer saw).
A defensible clean-room reticuli would have to bind the full production input
manifest (guidance, deps, tools, feedback) to a build, record lawful source and
review of all spec material (tests and fixtures included), enforce producer
access restriction outside the agent, and preserve independently-witnessed
execution evidence — and even then it establishes only "this run, this material,
these controls," never universal independence, patent freedom, or contract
permission.

**Governance consequence.** Consolidation transfers dependence from the
implementation supplier to the specification steward. Credible exit is credible
only if consumers retain portable criteria and authority over their own
acceptance policy — otherwise a replaceable implementation sits beneath an
irreplaceable acceptance authority. The authority invariant guards against
producer capture; it does not yet address steward capture.

**Decisive experiment.** Several successive replacements across related real
deployments, measuring total human adjudication + migration + escaped defects
against preserve-and-patch: does marginal cost fall *without narrowing the
obligation*? That single measurement decides whether reticuli builds a reusable
industrial asset or repeatedly finances specification discovery.
