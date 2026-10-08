# Recursive improvement of Reticuli through reconstructible discovery instruments

*Archived verbatim 2026-10-07: a technical design report supplied by
the keyholder (drafted outside this repository's sessions), baselined
at commit fdd3e81. The project's assessment and adoption order are in
instrument-recursion-response.md beside this file. Not normative.*

---

Technical design report
Repository baseline: fdd3e81ebc3156736a3f789bf424f105e3b9110d
Status: Proposed extension grounded in the inspected implementation and experimental records. No changes were made to the repository.

## 1. Central proposal

Reticuli can be extended into a system that improves its own ability to discover missing software requirements.

The mechanism is to make its investigative tools — probe generators, consumer checks, reducers, static analyses, and experiment schedulers — individually reconstructible claims. Candidate successors compete against their predecessors on independently evaluated tasks. A successor becomes eligible for adoption when its advantage survives both unfamiliar targets and reconstruction from its declared requirements.

The resulting process has three forms of accumulated knowledge:

1. Requirements: facts about what a particular subject must do.
2. Methods: reusable ways to discover missing requirements.
3. Experimental policy: knowledge about which method to apply next.

The first makes a specification stronger. The second makes investigation more capable. The third can make the process more economical.

The research hypothesis is:

> Successive generations of reconstructible investigative software can discover and resolve more consequential specification gaps per unit of total effort, while preserving established obligations.

Reticuli already contains machinery relevant to this hypothesis. It has not yet demonstrated the complete process.

## 2. What exists and what must be added

The inspected repository already separates claim identity from implementation identity and includes experiments on reconstruction, behavioral disagreement, and consumer compatibility.

| Existing mechanism | Relevant capability | Remaining limitation |
|---|---|---|
| Claim roots and manifests | Identify frozen acceptance criteria and recipes | A root establishes identity of criteria, not completeness |
| Blind reconstruction | Samples implementations admitted by those criteria | Samples can share untested assumptions |
| assess.py | Measures mutation resistance, reconstruction, and held-out behavior | Does not evolve investigative methods |
| Silence maps | Locate differences among accepted implementations | Cannot detect failures on which every implementation agrees |
| Contraction reducer | Minimizes witnesses while retaining a behavioral partition | Partition identity does not establish semantic defect identity |
| Substitution experiments | Expose consumer obligations absent from dependency criteria | Require identified consumers and meaningful checks |
| Cross-judging | Tests descendants' ability to judge and reconstruct | Agreement among judges can still reflect a shared defect |
| Boundary transitions | Record deliberate changes to acceptance criteria | Do not themselves measure improvement in investigative competence |

The most important missing artifact is a versioned, testable discovery instrument.

Today, a useful finding can lead to a criterion change. The extension should also ask:

> What procedure would have found this class of mistake earlier, and can that procedure find related mistakes elsewhere?

That question turns an individual failure into a candidate improvement to Reticuli.

Repository evidence for this report comes principally from the frozen source tree, especially research/harness/, src/reticuli/assess.py, src/reticuli/heldout.py, and the authority and basin-contraction proposal. Recorded experiments are treated as repository evidence; their full paid reconstruction campaigns were not independently repeated for this report.

## 3. Formal model

Let a subject's frozen acceptance boundary be C, and let p denote an implementation.

Define the admitted set: A(C) = { p | Gate(C, p) = pass }.

Membership in this set does not imply that every admitted implementation behaves identically. Nor does it imply suitability for every consumer.

Let O be an independently justified obligation, evaluated under environment E. A specification-gap witness establishes:

    p in A(C)  and  O(p, E) = fail.

A disagreement between implementations establishes less:

    p, q in A(C)  and  Observe(p, x, E) != Observe(q, x, E).

It identifies a question. Deciding whether the difference matters requires an obligation, consumer, standard, or explicit authority decision.

Now define a discovery instrument: D(S, B) -> W, where S is an authorized subject package; B is its resource budget; W is a collection of candidate witnesses.

An external procedure J replays, classifies, and deduplicates those witnesses:

    J(S, W) -> {confirmed, allowed, unresolved, invalid}.

The instrument is itself software. It therefore has its own claim C_D, concrete implementation d, and reconstruction procedure.

Two results must remain separate:

- Conformance: d in A(C_D).
- Investigative effectiveness: d performs well on an evaluation distribution.

A conforming implementation can still be an ineffective investigator. Performance measurements must accompany the claim rather than being inferred from its root.

## 4. Three nested experimental loops

The system should separate three loops because they answer different questions.

**Subject refinement.** Freeze the investigative tools. Reconstruct a subject, investigate its behavior, and propose corrections to its requirements. This tests whether the subject's acceptance boundary becomes more adequate.

**Instrument improvement.** Freeze the evaluation tasks and judgment procedure. Generate candidate investigative tools and compare their effectiveness. This tests whether investigation becomes better.

**Reconstruction of investigative capability.** Freeze a candidate instrument's claim. Reconstruct independent implementations and evaluate whether they retain its measured advantage. This tests whether the specification preserves the useful capability.

    Frozen subject claims -> Discovery instruments -> Replayable witnesses
    -> Independent adjudication -> Subject corrections -> (back to subjects)
    adjudication -> Candidate method improvements -> Fresh task evaluation
    -> Blind instrument reconstruction -> External promotion decision
    -> (back to instruments)

The distinction prevents a common experimental error: crediting an improved instrument when its targets simply became easier, or claiming specification convergence because the investigator stopped finding defects.

## 5. The discovery instrument as a first-class artifact

An instrument should be a small executable component before it becomes an open-ended agent.

Examples include: a checker for unexercised public API consumption; a probe generator for paired serialization and deserialization; a consumer-substitution runner; a stateful sequence generator for migration and recovery; a reducer that preserves an independently verified failure; a scheduler that chooses among available investigations.

Each instrument needs five declared properties:

- **Input contract.** What kinds of subjects, interfaces, implementations, and observations can it use?
- **Execution contract.** What dependencies, permissions, budgets, and randomness does it require?
- **Output contract.** What constitutes a well-formed witness, abstention, or infrastructure failure?
- **Capability contract.** What known positive and negative examples must it handle?
- **Applicability limits.** Under what conditions is its result meaningful?

The contract should preserve externally useful behavior while allowing different implementations. It should not encode one detector's source structure or a fixed list of memorized answers.

A proposed interface (internal, not an existing Reticuli API):

    class DiscoveryInstrument:
        def investigate(self, subject: SubjectBundle, budget: ResourceBudget,
                        observations: ObservationStore) -> InvestigationResult: ...

LLMs can propose strategies, generate adapters, or interpret evidence. The replay and observation path should remain executable independently of their narrative explanations wherever possible.

## 6. Witnesses and obligations

The witness is the unit that connects investigation to accumulated knowledge. A proposed witness record should include:

| Field | Purpose |
|---|---|
| Subject root | Identifies the frozen acceptance boundary |
| Implementation digests | Identifies the exact programs observed |
| Instrument root and digest | Identifies the detector contract and execution |
| Environment digest | Binds relevant runtime and dependency conditions |
| Input or action sequence | Reproduces the triggering conditions |
| Raw observations | Preserves outputs before normalization |
| Observation policy | States which differences were ignored |
| Obligation reference | Explains why a result matters |
| Replay recipe | Re-executes the observation |
| Resource measurements | Records discovery and replay costs |
| Evidence references | Binds logs, fixtures, and reports |
| Adjudication reference | Links the later decision |

These fields should refer to immutable content-addressed objects. A signature over a summary that omits the actual tested implementation or measurement artifacts would leave the evidence chain incomplete.

**Observation policy is part of the experiment.** The contraction pilot collapses different exceptions into a single rejected outcome. That can be appropriate for a codec contract that cares only about acceptance. It would be inappropriate for a consumer that distinguishes retryable errors from permanent failures. Canonicalization therefore needs its own versioned policy. Preserve raw observations so later investigators can revisit whether normalization erased a consequential distinction.

**Defect identity requires adjudication.** The partition "implementations A and B agree; C differs" is a useful clustering key. It is not a durable identity for the underlying defect. Different defects can create the same partition; adding another implementation can change the partition; different minimal inputs can expose one defect. Use two levels: mechanical clustering to reduce review volume, and adjudicated obligation identity to count distinct findings. The instrument must not earn additional credit merely by generating more examples of the same failure.

## 7. From individual failures to transferable methods

The recipe-writing failure provides a concrete starting point. The recorded reconstruction emitted JSON into a file named reticuli.toml, then failed when that file was consumed along the modern rebuild path. The local repair is a test for valid room materialization. The reusable investigative hypothesis is broader:

> Systems with paired production and consumption operations can have branches that are tested separately but never exercised together under the same format and environment.

An instrument for this hypothesis would:

1. Identify producer–consumer operation pairs.
2. Enumerate declared formats, modes, and relevant state transitions.
3. Generate valid objects reaching those paths.
4. Execute production followed by consumption.
5. Compare results with the declared semantic relation.
6. Minimize failures while preserving both validity and consequence.

For serialization, the intended relation might be decode(encode(x)) ~ x, where ~ is the subject's specified equivalence relation. That relation cannot be assumed universally: a serializer might deliberately discard metadata; a migration might intentionally change representation. The instrument should obtain the relation from the subject's contract or raise a question for adjudication.

Useful transfer targets include checkpoint systems, configuration converters, archive tools, and data migrations. Success on those targets would establish that the instrument learned a class of investigation beyond the original Reticuli failure. The subsequent step-ordering overconstraint supplies an equally important negative control: valid alternative representations must remain accepted.

## 8. Automatic specification extraction

A way to construct candidate requirements from an existing codebase — a separate subsystem from reconstruction. Inputs: public interfaces and documentation; existing tests and examples; observed consumer calls; runtime traces and failure reports; standards and protocol definitions; source-level data flow and state transitions. Output: a set of candidate obligations with evidence, not an automatically authoritative specification.

Classify extracted behavior explicitly:

| Classification | Interpretation |
|---|---|
| Explicit requirement | Stated by a supported contract or standard |
| Consumer dependency | Demonstrably relied upon by a named consumer |
| Observed behavior | Present in this implementation, with no established obligation |
| Allowed variation | Alternatives are explicitly acceptable |
| Unresolved | Evidence is insufficient or conflicting |

This avoids preserving every historical accident as a permanent requirement. It also exposes the central limit of extraction: observing a program tells us what it does on those observations; it does not, by itself, establish what every future replacement must do. For scientific software, a legacy implementation may contain the numerical error that a replacement should correct; requirements may need to come from conservation laws, convergence behavior, analytical solutions, or independent scientific validation.

## 9. Improving the search policy

After several instruments work reliably, Reticuli can learn where to spend its investigative budget. The scheduler chooses actions: reconstruct another implementation; probe an untested format transition; substitute a dependency under a consumer; investigate a disagreement cluster; reduce a witness; seek an independent obligation; stop.

A practical early scheduler should use explicit heuristics: prioritize consumed interfaces, unexplored branches, high-impact dependencies, and cheap replayable experiments. Later, compare learned scheduling policies against that baseline. The reward should reflect confirmed, distinct findings and their total cost, including adjudication. Raw disagreement volume is a poor objective. Retain exploration budget. The scheduler is another reconstructible claim; its improvement should be tested separately from the instruments it schedules.

## 10. Evaluation design

A credible experiment must distinguish genuine improvement from additional compute, stronger underlying models, memorization, and changes to the evaluator.

**Use three task pools.** Development tasks may be inspected and used for construction. Selection tasks compare candidates with restricted feedback (repeated use makes them development data; they need retirement rules). Confirmation tasks are newly sampled or independently assembled after candidate selection; they support the final reported comparison. A public repository's historical bugs cannot be assumed unknown to a pretrained model — record that limitation and include newly constructed cases and prospective discoveries.

**Include positive and negative controls**: historical real failures; controlled injected defects; valid alternative implementations; underconstrained specifications; consumer failures shared by all reconstructions; stateful and environment-dependent behavior; cases where the correct outcome is abstention.

**Staged comparisons**: existing frozen instruments (what can the current system discover?); baseline with more compute (is the advantage just search?); candidate at equal budget (did the method improve?); independently reconstructed candidate (did the claim preserve the advantage?); candidate on a new subject family (does the method transfer?). Keep model families fixed within a comparison; log external model changes rather than crediting them as software improvement.

## 11. Metrics and statistical interpretation

Primary outcome: distinct, independently confirmed consequential gaps at fixed budget — F(D, T, B). Report separately: false-report rate; witness replay success; time to first confirmed finding; human adjudication time; consumer impact; reconstruction success; performance across reconstructed variants; total development and deployment cost. For a known-defect corpus report recall; for open-ended discovery do not label observed finding rate as recall. Compare parent and candidate on paired instances with repeated runs; estimate uncertainty at the project or defect-family level. Candidate selection creates bias: the best selection-set score alone is weak evidence.

**Reconstruction retention**: for submitted candidate D* and reconstructed variants, report the full distribution of per-variant deltas against baseline on fresh tasks, INCLUDING failed reconstructions. This separates one implementation's value from the specification's ability to transmit it.

**Count the discovery cost**: amortized K = (K_search + K_confirmation + K_reconstruction)/N + K_deployment, human review included.

## 12. Promotion and authority

Two promotion decisions: instrument promotion (which tools investigate) and boundary promotion (what a subject must do). A successful instrument must not automatically authorize its own proposed boundary changes. The repository's governance assigns signatures over moved roots to the keyholder; the authority-and-basin proposal separates reconstruction machinery from authority over its accepted boundary. Implement that separation.

Lifecycle: proposed → executable → replay validated → evaluated → independently reconstructed → freshly confirmed → approved for use. Keep the lineage append-only; record rejection and retirement. When evidence reveals genuinely ambiguous intent, the result remains unresolved until an authorized decision — discovering uncertainty is valuable even when the system cannot resolve it.

## 13. Composition and the evidence cache

Specifications alone do not make compatibility compositional; assumptions and consumer obligations must compose. For component i write A_i => G_i. Composition requires evidence that connected components and the environment satisfy the assumptions. The cache stores scoped results: "this implementation of dependency D satisfies the exercised obligations of consumer C under environment E and check set T", keyed by H(C_D, C_C, digest(p_D), digest(p_C), E, T, runner version). Implementation digests matter because Reticuli deliberately admits different implementations under one root. Invalidate conservatively; retain stale results as history; do not inherit compatibility from root equality alone — the substitution experiments are evidence against precisely that shortcut. Periodic full checks remain necessary because the dependency map itself can be incomplete.

## 14. Implementation architecture

First version in the research harness, outside the normative boundary:

    research/harness/instruments/
        schema.py runner.py replay.py adjudication.py
        evaluate.py reconstruct.py campaign.py
        instruments/ fixtures/ protocols/

Wrap existing silence/closure/contraction/substitution tools behind adapters first; rewriting them during baseline construction would make comparisons uninterpretable. Minimum persisted entities: subject snapshot; instrument claim and implementation; investigation run; witness; replay result; obligation decision; evaluation campaign; promotion event. Content-addressed immutable evidence, small query index. Parallel workers submit candidate evidence to a verifier; workers never confirm their own findings or update boundaries.

## 15. Failure modes that determine whether this works

| Failure mode | Misleading appearance | Required response |
|---|---|---|
| Shared model assumptions | Reconstructions agree, so the specification appears complete | Exercise independent consumers and externally grounded properties |
| Overconstraint | More tests reject more implementations | Include valid variants and justify every new obligation |
| Witness inflation | Finding counts grow rapidly | Deduplicate by adjudicated obligation |
| Evaluation leakage | Each generation scores better | Rotate tasks and use fresh confirmation |
| Cheap false alarms | Discovery is fast but review is expensive | Count adjudication time and false-report cost |
| Detector memorization | Known fixtures pass perfectly | Hold out subject and defect families |
| Reconstruction loses capability | Submitted instrument wins, descendants do not | Strengthen its contract or limit the inheritance claim |
| Stale compatibility cache | Old passes reused after meaningful changes | Bind dependencies and invalidate conservatively |
| Stronger underlying LLM | New generation improves for external reasons | Freeze or separately account for model changes |
| Correlated judges | Multiple judges confirm the same mistaken premise | Ground verdicts in replay and explicit obligations |
| Target exhaustion | Finding rate falls | Evaluate against fresh targets and stronger investigators |
| Environment failure | A timeout is counted as a software defect | Preserve separate failure classifications |

## 16. Relationship to prior work

Counterexample-guided synthesis alternates candidate construction with refutation against a specification; Reticuli's additional question concerns whether the specification itself omits consumer-relevant behavior. Differential testing (Csmith) uses divergent outcomes to expose defects; reconstruction changes how the population is obtained and recorded. Multiversion programming (Knight and Leveson) cautions against treating independently developed versions as statistically independent. Darwin Gödel Machine modifies its own software and evaluates successors empirically with an archive of candidates; Hyperagents extends self-modification to the mechanism generating future improvements — any novelty claim must engage both directly. The prospective contribution is the combination: behavioral claims with identity and provenance; consumer-relative evidence of specification inadequacy; independently replayable findings; reconstruction of the investigative tools themselves; experiments testing whether capability survives that reconstruction.

## 17. First experimental campaign

Test one mechanism: discovering unexercised relationships between producing and consuming structured data. (1) Freeze the baseline — versions of instruments, tools, models, fixtures, limits. (2) Build the task interface — producer-consumer pairs, permitted observations, obligation sources. (3) Establish replay — reproduce known witnesses, reject malformed ones, include allowed ordering differences and intentionally lossy transforms. (4) Develop the candidate instrument from the room-recipe failure. (5) Compare at equal budget — baseline, baseline+search, candidate, on withheld subjects, tracking confirmed findings and review costs. (6) Reconstruct the candidate blind from its claim. (7) Confirm on fresh tasks — submitted instrument and reconstructions. (8) Publish the complete outcome including failed rebuilds, unresolved reports, false alarms, total cost.

The pilot succeeds if the candidate shows a useful advantage that persists across new subjects and reconstructed variants without unacceptable false-report or cost growth. It does not establish sustained recursive improvement; it establishes one transferable improvement and a mechanism for testing inheritance.

## 18. Evidence required for stronger claims

| Claim | Evidence needed |
|---|---|
| A specification gap was found | Gate-passing implementation plus independently justified failing obligation |
| A detector improved | Better results on fresh tasks under comparable resources |
| The improvement was preserved | Independent reconstructions retain the advantage |
| Improvement is recursive | Improved tools contribute causally to generating or selecting better successors |
| Improvement compounds | Repeated cycles outperform a fixed-tool process at matched cumulative cost |
| Software repairs itself | Prospective failures trigger validated repairs that preserve other obligations |
| Composition reduces remaining work | New tasks need less fresh investigation after integration and revalidation costs |

The causal test for recursion: keep a control process using the original tools across all generations, same budget, same access to accumulated subject findings. If the evolving process improves faster, identify which inherited tool changes produced the gain. "Takeoff" would require evidence about sustained growth rates and resource constraints beyond these experiments.

## 19. What could make the economics compound

With V_n work avoided through validated reuse, I_n new integration work, M_n catalog maintenance: net reuse is beneficial when V_n > I_n + M_n. Necessary, not sufficient, for acceleration — which additionally requires that improvements to discovery make valuable future improvements cheaper or likelier, after search and confirmation costs. Possible limits: new domains needing new human judgments; stateful interactions outgrowing component reuse; numerical obligations resisting cheap oracles; revalidation costs rising with density; remaining defects getting harder. Preserve enough evidence to determine which limit binds.

## 20. Recommended next development

Build the witness and instrument harness first. Use one existing failure to derive one generalized detector. Demonstrate that its advantage survives fresh targets and blind reconstruction. That result would establish:

> Reticuli can discover an improvement to its investigative machinery, express enough of that machinery in a claim to reconstruct it independently, and retain a measured advantage in subsequent investigation.

The longer-term research object is a growing collection of reconstructible methods for exposing consequential assumptions; its value depends on how effectively those methods transfer, compose, and reduce the cost of establishing new software behavior.
