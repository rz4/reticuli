# Verified Open-Ended Scientific Capability Acquisition
### A HARD/SOFT Multimodal Foundation Model Architecture with Reticuli-Governed Tool Evolution

**Status:** Research proposal (ongoing research work as of 2026-10-15)
**Date:** October 2026
**Research horizon:** 12 months for the initial experimental program

> Kept in-repo verbatim as the standing statement of the larger program
> reticuli and zeta serve. The measured companion is
> `scientific-capability-acquisition-methods.md`, which replaces several of
> this document's assumptions with numbers from the 2026-10-15 experiments.

---

## Abstract

Contemporary foundation models are primarily trained to process language, images, audio, and other widely available modalities. Scientific workflows require substantially different representations, including multidimensional numerical tensors, irregular meshes, continuous physical fields, instrument measurements, spatially resolved time series, and heterogeneous experimental records. Directly representing these objects as text or conventional images can discard numerical precision, dimensional relationships, coordinate information, and physical structure.

We propose an architecture for scientific foundation models based on two complementary forms of multimodal intelligence.

**SOFT multimodality** uses learned neural representations to encode scientific data and perform reasoning across modalities. **HARD multimodality** uses executable computational instruments to transform scientific data into quantities and representations that a reasoning model can analyze.

We hypothesize that coupling these approaches through an open-ended capability-acquisition process will enable a specialized scientific model to improve beyond the competencies provided by its initial pretraining.

When the system encounters a task that its existing model and tools cannot adequately solve, an external population of foundation models may propose, implement, reconstruct, and challenge new scientific operators. Reticuli provides content-addressed software claims and reproducible acceptance procedures, while its companion Zeta identifies insufficiently constrained behavior through independent implementations and adversarial probes. Scientific validation operates as an additional, independent gate.

Successfully admitted operators accumulate in a versioned scientific instrument library. Their execution records provide supervision for subsequent teacher-student distillation, enabling selected external computational capabilities to become part of the model's learned behavior.

The resulting architecture separates the evolution of the model, instruments, and specifications. It aims to convert externally supplied model intelligence into persistent, reusable scientific capabilities while retaining independent validation, provenance, and human authority over specification changes.

The principal research question is whether this arrangement produces sustained, transferable improvements in scientific problem-solving, rather than merely accumulating software tools.

---

## 1. Research motivation

### 1.1 The representation problem

Scientific data differ from common foundation-model inputs in several important respects.

A three-dimensional fluid simulation, for example, may produce a field

`X ∈ R^(T × D × H × W × C)`

where T denotes time, D/H/W spatial dimensions, and C the physical channels.

These channels could represent velocity, pressure, temperature, density, or other physical quantities. Their meaning depends on metadata that ordinary tokenization does not preserve: coordinates, units, sampling intervals, boundary conditions, mesh geometry, discretization, and numerical precision.

A language model given a textual serialization of such a field is not necessarily capable of reasoning about its physical structure. An image-based representation may preserve some spatial patterns but conceal quantitative relationships and temporal dynamics.

A scientific reasoning system must therefore determine both **what information to extract** and **how that information should be represented**.

### 1.2 The specialization hypothesis

A general-purpose frontier model may possess broad scientific knowledge but relatively weak native representations of specialized numerical data.

A smaller scientific model, equipped with domain-specific encoders and reliable computational instruments, may outperform it on selected tasks despite having less general reasoning capacity.

This leads to the first hypothesis:

**H1 — Specialization advantage:** Under controlled inference and development budgets, a scientific model combining native representations and executable tools will achieve greater accuracy or efficiency than a general-purpose model using conventional scientific-data interfaces on selected held-out scientific tasks.

The comparison must account for total system cost, including tool execution, model inference, and amortized model training. A smaller model cannot be declared more efficient merely because its external computations are omitted from the accounting.

### 1.3 The acquisition hypothesis

Scientific domains are too diverse for developers to anticipate every useful operator.

The system might initially support Fourier transforms, temporal statistics, gradient computation, and feature extraction. A new scientific question may require a computational method that is absent from its library.

This motivates the second hypothesis:

**H2 — Capability acquisition:** A model supported by verified dynamic tool acquisition can solve novel scientific tasks that remain unsolved by an otherwise equivalent system restricted to a fixed tool library.

The contribution must be cumulative. Generating disposable code for an individual question is not sufficient. Acquired operators should remain discoverable, reusable, and scientifically validated across subsequent tasks.

### 1.4 The internalization hypothesis

Not every useful computation needs to remain external.

Repeated use of computational instruments generates structured supervision relating raw scientific measurements, intermediate transformations, and scientifically meaningful outputs.

Such records may permit the model to learn when to use an operator, approximate portions of its behavior, or develop new representations of the underlying phenomena.

**H3 — Capability internalization:** Distillation from verified tool-supported workflows will improve the scientific model's performance on held-out tasks, while reducing external tool dependence for a measurable subset of those tasks.

Exact calculations, expensive simulations, and high-stakes numerical operations may continue to require external execution.

### 1.5 The recursive improvement hypothesis

The strongest hypothesis concerns repeated cycles of acquisition and learning.

**H4 — Cumulative improvement:** Successive acquisition, verification, and distillation cycles will produce increasing scientific task coverage and transferable performance improvements under fixed evaluation protocols and explicitly accounted computational budgets.

This is an empirical claim, not an assumed consequence of the architecture.

---

## 2. System overview

The system consists of three persistent assets supported by a distributed computation and evaluation environment.

### 2.1 Persistent assets

**A. Scientific foundation model**

Responsible for understanding scientific questions, interpreting raw or encoded observations, selecting computational operations, synthesizing evidence, and producing analytical conclusions.

Its weights, modality adapters, training data, and evaluation results are independently versioned.

**B. Scientific instrument library**

A growing collection of executable computational capabilities, including data transforms, numerical algorithms, feature extractors, statistical procedures, simulation utilities, and learned surrogates.

Each instrument exposes a typed interface and independently reproducible evidence of its accepted behavior.

**C. Specification and evidence corpus**

A repository of behavioral criteria, scientific reference cases, tolerances, negative tests, adversarial findings, reconstruction records, and authorization decisions.

The specification corpus determines what has actually been established about an instrument. It must not be conflated with the instrument's implementation.

### 2.2 Operational architecture

The complete system contains two interconnected loops.

**Inner loop — Scientific reasoning**

Scientific data → modality representation → scientific reasoning model → tool selection and execution → evidence interpretation → scientific answer.

This loop performs ordinary analytical work using the currently available capabilities.

**Outer loop — Capability acquisition**

Capability gap → tool proposal → implementation → independent reconstruction → Reticuli acceptance → Zeta specification pressure → independent scientific validation → authorization → instrument-library registration.

Accepted instrument behavior and execution traces then become candidates for SOFT distillation.

The loops operate at different timescales.

The inner loop may execute thousands of times without changing the system. The outer loop is triggered only when there is credible evidence of an unmet computational need.

Distillation occurs through scheduled training experiments or model updates, not necessarily after every tool acquisition.

### 2.3 Architectural principle

The model may request a new capability, but it cannot unilaterally declare its own implementation valid.

The proposing agents, acceptance criteria, scientific reference evidence, and promotion authority must remain distinguishable.

This prevents software generation, software validation, and scientific truth claims from collapsing into a single self-referential process.

---

## 3. Scientific data architecture

### 3.1 Typed scientific data objects

The system should not require all observations to pass through a textual representation.

Instead, scientific objects are stored in native formats and exposed through a common metadata interface.

A Scientific Data Object (SDO) contains:

- A reference to the underlying data asset.
- Shape, dtype, and storage format.
- Named dimensions and coordinate systems.
- Physical units and dimensional relationships.
- Spatial and temporal sampling metadata.
- Boundary conditions, masks, and missing-data indicators.
- Dataset provenance and access restrictions.
- Experiment, instrument, or simulation identifiers.
- Optional uncertainty and measurement-error descriptions.

For example, a velocity field may declare dimensions `(time, z, y, x, vector_component)`, spatial units in meters, temporal units in seconds, and velocity components in meters per second.

These descriptions are not interchangeable with raw tensor values.

### 3.2 Native storage

The initial implementation should support formats common in scientific computing, including HDF5, Zarr, NetCDF, and NumPy arrays.

Further adapters can support tabular time series, particle systems, irregular meshes, images, spectral measurements, and domain-specific formats.

Large scientific objects should remain in external object stores or scientific databases. Agents should manipulate references, subsets, and derived results rather than repeatedly copying entire arrays into their context windows.

### 3.3 Data access and computation

A scientific data-access service provides:

- Lazy loading and chunked reads.
- Coordinate-aware slicing.
- Spatial and temporal resampling.
- Data provenance and checksum verification.
- Unit normalization and dimensional analysis.
- Numerical precision preservation.
- Distributed execution on CPUs and GPUs.

A shared interface allows different scientific encoders and operators to access the same underlying data without introducing incompatible ad hoc serialization conventions.

### 3.4 Scientific semantics

Scientific validity depends on more than array shape.

A requested derivative, for example, may be mathematically defined but inappropriate when the sample spacing is unknown, the mesh is nonuniform, or boundary conditions are incompatible with the selected numerical method.

The system should treat units, coordinates, discretization, sampling assumptions, and numerical error as first-class objects.

Invalid operations should produce explicit diagnostic results rather than silently returning plausible-looking numerical arrays.

---

## 4. SOFT multimodal architecture

### 4.1 Initial model strategy

The first research stage should adapt an existing open-weight language or reasoning model rather than train a foundation model from scratch.

A 3-8B parameter model is a reasonable experimental starting range, conditional on available hardware. Its purpose is to establish whether the proposed capability loop is effective before scaling pretraining expenditure.

The model acts as the scientific reasoning and orchestration core.

Modality-specific encoders supply representations of numerical and physical observations.

The initial system should be described as an adapted scientific model. The broader foundation-model claim would require subsequent evidence of transfer across diverse tasks and modalities.

### 4.2 Modality-specific encoders

Different scientific modalities may require distinct encoder families.

For temporal volumetric fields, candidate architectures include 3D convolutional encoders, spatiotemporal transformers, spectral encoders, and neural operators.

For irregular meshes and particle systems, graph-based or geometry-aware encoders may be more appropriate.

For time series, appropriate architectures may include temporal attention, state-space models, frequency-domain representations, or combinations of these.

For spectral data, encoders should preserve physically meaningful frequency coordinates and measurement calibration.

The goal is not to force every modality into the same preprocessing pipeline. Rather, heterogeneous scientific representations should connect to a shared reasoning space.

### 4.3 Neural projection

Each modality encoder produces latent representations that are aligned with the reasoning model through a trainable projection or cross-attention interface.

A generic projection can be written:

`Z_m = P_m(E_m(X_m, M_m))`

where:

- `X_m` is the native scientific observation.
- `M_m` is its associated metadata.
- `E_m` is a modality-specific encoder.
- `P_m` projects its output into the reasoning interface.
- `Z_m` is the resulting scientific representation.

The interface should retain links between latent tokens and their source regions, time intervals, physical coordinates, and uncertainty where feasible.

### 4.4 Scientific reasoning objective

The model should learn to:

1. Identify relevant phenomena and quantities.
2. Select or request appropriate computations.
3. Interpret observations and numerical results.
4. Distinguish measured evidence from inference.
5. Recognize uncertainty and unresolved assumptions.
6. Produce testable hypotheses and analytical explanations.

Training should include scientific task supervision, numerical interpretation, tool-use trajectories, and carefully selected modality-alignment objectives.

A language-only explanation of scientific concepts is not adequate evidence of competence on native scientific data.

---

## 5. HARD multimodal architecture

### 5.1 Executable scientific instruments

HARD multimodality provides computational operations over native scientific data.

An instrument may be an ordinary deterministic function, a complex numerical workflow, a simulation interface, or a separately trained model.

The initial instrument library should include established scientific operators such as:

- Fourier and wavelet transforms.
- Interpolation and filtering.
- Gradient, divergence, curl, and Laplacian operators.
- Temporal derivatives and statistical summaries.
- Connected-component and feature tracking.
- Regression, parameter estimation, and uncertainty propagation.
- Numerical integration and equation solvers.
- Domain-specific detection and measurement procedures.

Existing trusted scientific libraries should be wrapped and reused before generating replacement implementations.

### 5.2 Typed interface contract

Every tool must publish a machine-readable interface describing:

- Tool identifier and version.
- Accepted scientific object types.
- Input dimensions and physical units.
- Required numerical parameters.
- Preconditions and supported operating regimes.
- Output types and dimensions.
- Error and exception behavior.
- Computational and memory requirements.
- Declared determinism and numerical tolerances.
- Execution environment.
- Associated Reticuli claim and scientific validation records.

For example, a vorticity operator should identify its velocity-field input, coordinate requirements, differentiation method, boundary assumptions, and output units.

The contract should allow a reasoning model to determine whether the tool is applicable before execution.

### 5.3 Execution environment

Tools should execute through a constrained scientific computation service.

Capabilities include resource quotas, timeouts, network restrictions, dependency isolation, reproducible environments, and execution tracing.

The execution service returns typed results, logs, metadata, provenance references, and error estimates where applicable.

The reasoning model receives the information required for analysis without unnecessarily receiving the full data object.

### 5.4 Tool composition

Scientific operations are frequently useful as compositions.

A workflow might perform:

Velocity field → vorticity → thresholding → connected structures → temporal association → trajectory statistics.

The system should maintain a typed directed acyclic graph of operations.

Each intermediate output retains its data lineage, numerical assumptions, and tool provenance.

Such workflows can themselves become reusable, versioned instruments after acceptance.

---

## 6. Detecting capability gaps

The outer loop begins when the inner loop cannot adequately resolve a scientific question using existing capabilities.

A capability gap should not be inferred solely from the model stating that it needs a tool.

Potential signals include:

- No registered instrument supports the required operation.
- A tool's preconditions do not match the data.
- Existing tools return inconsistent or invalid results.
- A benchmark or scientific oracle demonstrates inadequate accuracy.
- The available workflow exceeds resource constraints.
- Repeated human interventions reveal a missing reusable operation.
- A validated task cannot be completed under a prescribed tool budget.

The system must first search the existing library and relevant authorized external packages.

It should prefer reuse, then adaptation, and only then synthesis of a new implementation.

### 6.1 Capability request

A capability request specifies:

**Scientific objective:** What question or measurement requires the capability?

**Input domain:** What data structures and physical regimes must it handle?

**Expected output:** What numerical or structured result should it produce?

**Existing limitations:** Why do current instruments fail?

**Evaluation basis:** How can successful behavior be independently tested?

**Scientific justification:** What established theory, reference computation, or observational evidence supports the requested operation?

Requests without a defensible evaluation plan enter an exploratory state rather than automatic acquisition.

### 6.2 Capability-gap registry

A registry groups similar requests to identify repeated unmet needs.

Prioritization can consider estimated scientific utility, frequency of demand, novelty, expected validation cost, and potential reuse.

A capability repeatedly requested across unrelated datasets may justify more development resources than one required for a single narrowly defined example.

---

## 7. Heterogeneous external model population

A central architectural feature is the use of third-party foundation models as interchangeable contributors to the acquisition process.

External models can propose algorithms, generate implementations, reconstruct programs from frozen criteria, produce adversarial tests, and analyze specification ambiguities.

These activities need not be performed by the same model family.

### 7.1 Model roles

**Proposers**

Generate candidate approaches for an unmet scientific capability. Proposals may involve mathematical algorithms, existing software adaptation, numerical methods, or learned approximations.

**Implementers**

Produce executable software that attempts to satisfy the approved capability specification.

**Reconstructors**

Independently create implementations from the declared criteria without access to the implementation being reconstructed.

**Challengers**

Develop tests, perturbations, metamorphic relations, and counterexamples designed to expose unspecified or incorrect behavior.

**Reviewers**

Summarize evidence, identify unresolved assumptions, and recommend further experiments. Model-generated reviews are advisory and cannot substitute for independent validation or authorized promotion.

### 7.2 Independence requirements

Distinct API providers do not necessarily imply independent reasoning or errors.

The system should track model identity, version, sampling parameters, shared dependencies, information access, and lineage.

Reconstruction trials must follow explicit information-separation rules. For example, a reconstructor evaluating the completeness of a specification must not receive the reference implementation.

Challengers should have access to relevant public specifications and artifacts but not the private final evaluation set.

The proposal should distinguish model diversity from genuine independence of evidence.

### 7.3 Contribution protocol

Each external contribution is recorded with:

- Provider and model version.
- Role and input references.
- Prompt and available context, subject to privacy constraints.
- Produced code, tests, or analysis.
- Execution and evaluation records.
- Compute and monetary cost.
- Dependencies and licensing obligations.
- Whether the contribution was accepted, rejected, or left unresolved.

The long-term value resides in the admitted artifacts and evidence, not in preserving indefinite access to their originating models.

### 7.4 Model selection

Provider selection can be treated as a cost-constrained experimental design problem.

The scheduler should allocate work according to observed proposal quality, implementation reliability, diversity, and cost.

However, some fraction of the evaluation budget should remain reserved for independent or less frequently used models. Otherwise, a high-performing provider could dominate the reconstruction population and weaken the value of cross-implementation comparison.

This creates a multi-model research environment without requiring third-party models to control the persistent scientific system.

---

## 8. Reticuli and Zeta integration

### 8.1 Reticuli as the software acceptance boundary

Reticuli identifies software through pinned acceptance criteria rather than implementation bytes.

An instrument claim should declare the behavioral obligations that an implementation must satisfy. Its implementation can subsequently be reconstructed or replaced while retaining the same claim identity, provided it continues to satisfy those frozen criteria.

The proposed integration uses Reticuli for:

- Content-addressed behavioral claims.
- Reproducible acceptance tests.
- Independent reconstruction trials.
- Cross-implementation comparison.
- Recorded execution evidence.
- Auditable claim signatures.

A passing claim establishes conformance to its declared criteria. It does not independently establish that the criteria fully describe the intended scientific behavior.

### 8.2 Zeta as a specification-pressure mechanism

Zeta maintains an exploratory population outside the frozen acceptance boundary.

Its role is to compare implementations, seek unpinned behavior, and generate evidence for possible specification changes.

The existing Zeta model distinguishes three relevant classes of finding.

**Contraction:** Candidate implementations agree on behavior not yet explicitly constrained. Additional criteria may formalize that agreement without excluding current members.

**Eviction:** Implementations disagree on observable behavior. Selecting one behavior excludes implementations that produce alternative outcomes.

**Repair:** An independently justified oracle rejects every member of the current population, indicating a potentially systematic defect.

The scientific system should retain this distinction. Consensus among reconstructions is not proof of scientific correctness.

Zeta's exploratory findings remain separate from signed specification changes.

### 8.3 Independent scientific validation

A separate Scientific Validation Gate (SVG) is required.

It may evaluate:

- Agreement with analytic or high-accuracy reference solutions.
- Conservation of physical quantities.
- Dimensional and coordinate consistency.
- Symmetries and invariances.
- Numerical convergence under refinement.
- Error bounds and uncertainty calibration.
- Behavior under noise, missing data, and changed sampling rates.
- Out-of-distribution performance.
- Stability and scientifically meaningful failure reporting.

Different scientific domains require different validation procedures.

A numerical approximation should not be required to produce bitwise-identical results across hardware when scientifically justified tolerances apply. Conversely, loose tolerances must not permit systematic physical errors.

### 8.4 Two independent acceptance questions

Every acquisition must answer:

**Software question:** Does this implementation satisfy its declared behavioral specification?

**Scientific question:** Is that specification adequate for the intended scientific task, within an explicitly defined operating domain?

Reticuli answers the first through its acceptance procedures.

Zeta exposes weaknesses in the first question's constraints.

The Scientific Validation Gate supplies independent evidence addressing the second.

The two questions must remain separate in the instrument's recorded status.

### 8.5 Instrument states

Proposed states are:

| State | Meaning |
|---|---|
| Proposed | Requested but not implemented |
| Experimental | Candidate exists; unverified |
| Software accepted | Reproducible behavioral criteria satisfied |
| Scientifically validated | Independent scientific criteria satisfied within a declared scope |
| Admitted | Authorized for specified use in the instrument library |
| Restricted | Available only for exploratory or limited use |
| Superseded | Replaced by a newer instrument or specification |
| Revoked | No longer admitted for use |

No external model should be able to sign a specification promotion or grant itself admission authority.

Authorization policies should be explicit, reviewable, and capable of supporting narrower scientific-use restrictions.

---

## 9. Instrument identity, lineage, and reuse

### 9.1 Multiple identities

A scientific instrument requires more than a single software hash.

At minimum, the system should distinguish:

1. **Behavioral identity:** The Reticuli claim root representing the frozen acceptance criteria.
2. **Implementation identity:** The content digest of the actual executable and its relevant dependencies.
3. **Scientific validation identity:** A versioned digest referencing the validation protocol and its supporting evidence.
4. **Deployment identity:** The approved execution environment, numerical configuration, and operating restrictions.

Two implementations may share behavioral identity while differing in speed, memory requirements, or numerical performance outside the tested domain.

### 9.2 Capability registry

A registry entry may conceptually contain:

- `capability_id`
- `behavioral_root`
- `implementation_digest`
- `scientific_validation_record`
- `supported_data_types`
- `physical_units`
- `operating_domain`
- `known_limitations`
- `approved_execution_profile`
- `reconstruction_evidence`
- `dependencies`
- `provenance`
- `admission_status`

The runtime should resolve an appropriate admitted implementation through this registry.

### 9.3 Selecting among equivalent implementations

Multiple implementations can satisfy a common behavioral specification.

They may nevertheless differ in execution time, memory demand, numerical stability, portability, and maintainability.

Selection should be based on measured, task-relevant criteria.

For example, a GPU implementation may be preferred for large volumetric datasets, while a lightweight CPU implementation is appropriate for smaller analyses.

The registry should retain alternative conforming implementations when their tradeoffs are meaningful.

Optimization must not silently broaden an implementation's scientific operating claims.

### 9.4 Persistent scientific knowledge

A verified instrument preserves executable behavior, interface meaning, scientific tests, and evidence of the circumstances under which it works.

This is a form of persistent computational knowledge.

However, the completeness of that knowledge is limited by its specifications, test coverage, scientific assumptions, and available reference evidence.

Those limits should remain visible to downstream model training and inference.

---

## 10. HARD-to-SOFT distillation

Distillation converts selected tool-supported capabilities into trainable supervision for the scientific model.

Three transfer mechanisms should be studied separately.

### 10.1 Tool-selection distillation

The student learns when to invoke an existing instrument and which parameters to supply.

Training examples contain:

- Scientific question and relevant data metadata.
- Available tool interfaces.
- Valid tool-selection decisions.
- Arguments and preconditions.
- Execution results.
- Correct analytical outcomes.

The objective is to reduce invalid tool calls and unnecessary computation while improving task completion.

This mode does not require the student to replicate the numerical operator internally.

### 10.2 Computational surrogate distillation

For certain expensive transformations, the student or a specialized neural module may learn a surrogate approximation.

Given a validated instrument `f`, a student approximation `f_theta` is trained on examples of the form:

`input scientific object → validated computational output`

Its suitability depends on error bounds, calibration, and out-of-distribution behavior.

Surrogates should operate only within validated regimes and defer to the original tool when confidence or accuracy requirements are not satisfied.

This mechanism is especially relevant to repetitive numerical procedures with favorable approximation properties.

### 10.3 Representation distillation

The most ambitious transfer mechanism uses instrument outputs to teach a modality encoder to recognize scientifically meaningful structure.

Consider a volumetric fluid simulation.

The HARD pathway might compute vorticity, coherent structures, and temporal tracking measurements.

The SOFT pathway learns representations of the original velocity field that predict, summarize, or otherwise exploit these derived physical features.

The student is not merely imitating the final answer. It receives structured supervision connecting native observations to physically interpretable quantities.

The experimental objective is to determine whether this produces transferable scientific representations rather than narrow memorization of instrument outputs.

### 10.4 Training objective

An illustrative training objective is:

`L = λ_task L_task + λ_tool L_tool + λ_rep L_rep + λ_phys L_phys + λ_ret L_ret`

where:

- `L_task` measures task-answer performance.
- `L_tool` supervises tool selection and arguments.
- `L_rep` aligns learned and instrument-derived representations.
- `L_phys` penalizes violations of applicable physical constraints.
- `L_ret` measures retention of previously acquired competencies.

The weights and applicable terms depend on the selected modality and task.

The training objective should not substitute for independent validation.

### 10.5 Training-data admission

Only traces that satisfy declared quality requirements should enter the primary distillation corpus.

Examples should preserve:

- Data lineage.
- Instrument versions.
- Scientific validation status.
- Teacher model provenance.
- Intermediate results.
- Numerical uncertainty.
- Final task outcomes.
- Relevant failure cases.

Failed or exploratory traces may be useful as negative examples, but they must be labeled accordingly.

The distillation pipeline itself should be versioned and reproducible.

### 10.6 Distillation eligibility

Not every admitted tool should be internalized.

A tool is a candidate when it is used frequently, its outputs provide stable supervision, and the student can plausibly learn useful behavior within available computational resources.

Exact numerical solvers and highly specialized scientific instruments may be better retained as external tools.

The decision should depend on empirical benefit rather than a requirement to eliminate the HARD pathway.

---

## 11. Experimental research program

### 11.1 Initial scientific domain

We propose temporal three-dimensional fluid dynamics as the first experimental domain.

It provides multidimensional data, well-defined physical quantities, established numerical methods, and opportunities to construct reference solutions.

The initial research should use synthetic flows with known properties, together with selected datasets from the Johns Hopkins Turbulence Database where permitted by access and usage terms.

A controlled domain makes it easier to distinguish real capability acquisition from fluent but ungrounded scientific explanation.

### 11.2 Representative tasks

The benchmark should include:

**Basic characterization:** Determine properties such as kinetic energy, enstrophy, divergence, and statistical moments.

**Spatial analysis:** Identify vortical structures, gradients, localized extrema, and connected regions.

**Temporal analysis:** Track structures, estimate rates of change, and detect transitions across timesteps.

**Physical interpretation:** Distinguish physically consistent phenomena from numerical artifacts.

**Novel derived measurements:** Request quantities or relationships unsupported by the initial tool library.

**Cross-resolution analysis:** Repeat measurements on data of different spatial or temporal resolutions and assess convergence.

Tasks should specify acceptable output types, scientific references, and evaluation criteria before model testing.

### 11.3 Experimental configurations

| System | Configuration |
|---|---|
| A | General-purpose foundation model with conventional data presentation |
| B | Specialized scientific model with SOFT encoders only |
| C | Specialized model with SOFT encoders and fixed HARD tools |
| D | Specialized model with dynamic, verified tool acquisition |
| E | Configuration D followed by HARD-to-SOFT distillation |
| F | Dynamic acquisition without independent reconstruction and Zeta pressure |

Configuration F is an important ablation. It helps determine whether the added verification machinery improves the reliability and scientific utility of acquired capabilities rather than merely increasing development cost.

A second ablation should compare one external model family against a heterogeneous model population.

### 11.4 Primary outcome

The primary evaluation should measure task success on a preregistered, held-out collection of scientific problems requiring generalization beyond the development set.

Success must be evaluated using scientific criteria, not only answer similarity or textual preference.

The study should report paired performance differences between configurations, uncertainty intervals, and total computational cost.

### 11.5 Secondary outcomes

Measurements should include:

- New tasks solved after each acquisition cycle.
- Number of scientifically validated tools acquired.
- Fraction of acquired tools reused on unrelated tasks.
- Time and cost required to resolve a capability gap.
- Cross-model reconstruction success.
- Defect detection and specification-gap discovery.
- Scientific error rates and numerical stability.
- Performance on unseen physical regimes.
- Distillation retention and catastrophic forgetting.
- Reduction in tool calls after distillation.
- Generalization to changed resolutions and sampling rates.

### 11.6 Experimental contamination

A strict separation should be maintained among development prompts, public acceptance criteria, scientific-validation evidence, and the final held-out evaluation.

The system should not be allowed to refine its instruments directly against the final benchmark.

The study should also distinguish genuinely novel tool construction from retrieval or repackaging of known software.

Both are useful operationally, but they support different scientific claims.

### 11.7 Acquisition-specific tests

Three evaluation designs are particularly important.

**Removal test:** Remove an acquired instrument and measure whether previously solved tasks become unsolved.

**Transfer test:** Present a new task requiring the same computational principle in a different dataset, resolution, or physical regime.

**Persistence test:** Introduce later acquisitions and verify that earlier competencies remain available.

These distinguish durable capability accumulation from transient agent performance.

---

## 12. Measuring sustained improvement

The strongest claim requires repeated, controlled acquisition cycles.

Let `C_g` denote the set of validated scientific tasks solvable by generation `g`, using a fixed evaluation suite and bounded resources.

A simple coverage statistic is:

`coverage(g) = |C_g| / |C_all|`

However, increasing coverage alone may reflect the addition of increasingly narrow tools.

The study must also measure transfer to unseen tasks.

A useful capability-efficiency measure is:

`efficiency(g) = held-out tasks solved / total amortized system cost`

Cost includes external model inference, tool proposal and reconstruction, validation, numerical execution, and model training.

We also propose tracking:

**Acquisition yield:** Scientifically validated reusable capabilities divided by acquisition attempts.

**Specification pressure yield:** Actionable, nonredundant specification gaps discovered per unit of evaluation compute.

**Transfer yield:** New held-out task families solved per admitted capability.

**Distillation efficiency:** Retained capability improvement divided by additional training and inference cost.

**Retention:** Previously demonstrated competencies preserved after subsequent updates.

The analysis should report improvements per generation alongside cumulative expenditure.

### 12.1 Stopping and rollback

A generation should not be promoted merely because it contains more tools or newer weights.

Promotion should be conditional on:

- Satisfactory held-out performance.
- No disqualifying scientific regressions.
- Independent reproducibility checks.
- Accepted cost and reliability profiles.
- Authorized specification and deployment decisions.

Failed improvements remain useful experimental evidence.

The architecture should support rollback to earlier model and instrument-library versions.

---

## 13. First end-to-end demonstration

### 13.1 Scientific problem

Suppose a researcher asks:

"Identify coherent vortical structures in a time-resolved 3D velocity field, track them through time, and estimate their lifetimes and characteristic dimensions."

The initial system can load velocity fields and calculate local vorticity but lacks a reliable temporal structure-tracking instrument.

### 13.2 Gap identification

The reasoning model searches the existing library.

It finds spatial analysis tools but no suitable operator for associating evolving connected structures across timesteps.

A capability request is created.

The request specifies acceptable data types, coordinate assumptions, temporal continuity, output trajectories, and reference evaluation cases.

### 13.3 External proposal population

Independent third-party models propose candidate algorithms.

One may use connected-component overlap. Another may use motion prediction and assignment. Another may propose graph-based temporal association.

These proposals are evaluated for applicability, complexity, and scientific assumptions.

Promising methods are selected for independent implementation trials.

### 13.4 Reticuli reconstruction

A behavioral specification is frozen.

Independent implementations are generated from its acceptance criteria.

The implementations undergo reproducible acceptance audits and crosschecks.

A shared root demonstrates conformity to the same declared criteria, not equivalence in all possible behaviors.

### 13.5 Zeta challenge

Zeta compares behavior under perturbations such as:

- Structures merging or splitting.
- Changes in frame rate.
- Boundary crossings.
- Missing timesteps.
- Multiple equally plausible associations.
- Degenerate geometries.
- Noisy or threshold-sensitive structures.

Disagreement is recorded and classified.

Additional behavior is not silently added to the specification. Each proposed change requires a justified acceptance decision.

### 13.6 Scientific validation

The Scientific Validation Gate evaluates the operator on synthetic flows with known structure trajectories and on appropriately justified reference datasets.

Metrics may include trajectory association accuracy, lifetime error, split/merge correctness, and robustness under resolution changes.

Human scientific review determines whether the evidence supports the intended operating claims.

### 13.7 Acquisition

The accepted operator enters the instrument library with its behavioral identity, implementation reference, scientific validation record, and supported data regimes.

The foundation model can now use it in subsequent scientific workflows.

The system has acquired an external computational capability.

### 13.8 Distillation

Accepted execution trajectories become training examples.

The student learns to recognize when temporal structure tracking is needed and how to interpret its outputs.

Further experiments examine whether its native spatiotemporal representations improve sufficiently to support selected tracking-related reasoning tasks with reduced tool dependence.

The operator remains available for precise measurement or fallback.

### 13.9 Demonstrated result

A successful experiment would show:

1. The original fixed-tool system cannot solve the task adequately.
2. The acquisition system constructs and admits an independently validated operator.
3. The admitted capability generalizes to held-out cases.
4. The capability remains reusable by later tasks.
5. The distilled student retains a measurable part of the acquired competence.

This would provide a concrete demonstration of both HARD capability growth and partial HARD-to-SOFT transfer.

---

## 14. Implementation architecture

The proposed implementation separates eight services.

### Data Registry

Maintains references to scientific datasets, native formats, dimensions, units, and access policies.

### Scientific Model Runtime

Hosts the reasoning model and modality encoders, with typed interfaces for requesting scientific computations.

### Tool Execution Runtime

Runs admitted instruments in resource-limited, observable environments.

### Capability Planner

Detects unmet needs, searches existing tools, creates capability requests, and tracks acquisition progress.

### External Model Orchestrator

Routes proposal, implementation, reconstruction, and challenge tasks to approved third-party models while preserving role separation and provenance.

### Reticuli/Zeta Service

Runs reproducible software acceptance procedures, maintains reconstruction populations, performs specification pressure, and produces signed or reviewable evidence records under existing authorization rules.

### Scientific Validation Service

Runs domain-specific reference comparisons, numerical tests, and scientific evidence assessments.

### Distillation and Evaluation Service

Produces admitted teacher datasets, trains model updates, evaluates transfer and regressions, and manages model versions.

These services communicate through durable, typed job records.

The architecture should avoid embedding Reticuli itself into the scientific foundation model. Reticuli and Zeta remain external verification infrastructure.

### 14.1 Acquisition transaction

A proposed capability transaction proceeds through the following records:

`CapabilityRequest → CandidateProposal → CandidateImplementation → BehavioralClaim → ReconstructionEvidence → ScientificValidationRecord → AdmissionDecision → LibraryRelease`

A separate distillation transaction proceeds through:

`AdmittedTool → QualifiedExecutionTraces → TrainingDataset → StudentCheckpoint → EvaluationRecord → ModelReleaseDecision`

These records should be independently inspectable.

### 14.2 Tool-library updates

Adding an instrument should not automatically alter the model weights.

Similarly, deploying a new student checkpoint should not change the tool specifications or scientific validation evidence.

Both operations should be versioned, auditable, and reversible.

This separation is essential for attributing improvements to the correct source.

---

## 15. Safety, governance, and scientific integrity

### 15.1 Untrusted generated code

Third-party model output must be treated as untrusted.

Candidate tools should not have unrestricted access to networks, credentials, private datasets, or deployment services.

Dependency installation and execution require explicit policy enforcement.

The system should record external package provenance, licenses, and supply-chain evidence.

### 15.2 Data governance

Scientific data may contain proprietary, export-controlled, personal, or otherwise restricted material.

External providers should receive only data they are authorized to process.

The system should prefer sending task specifications, metadata, synthetic fixtures, and appropriately de-identified examples when raw data transfer is unnecessary.

The acquisition infrastructure must enforce dataset-specific access restrictions.

### 15.3 Scientific epistemics

A reproducible numerical result may still be scientifically wrong.

A consensus of model-generated implementations may reproduce the same incorrect assumption.

A statistically successful neural surrogate may fail outside its tested regime.

Accordingly, the system must distinguish:

- Reproducibility.
- Behavioral conformance.
- Scientific validation.
- Statistical generalization.
- Authorization for use.

These are separate claims, supported by separate evidence.

### 15.4 Specification authority

External models may propose specification changes and submit supporting evidence.

They cannot independently alter accepted scientific obligations or authorize deployment.

Human scientific and technical reviewers retain authority over consequential changes until a separately justified governance process establishes otherwise.

### 15.5 Recursive system boundaries

The initial program should permit acquisition of scientific analysis operators, not unrestricted modification of the model-serving infrastructure, authorization system, or acceptance machinery.

Any future acquisition of infrastructure-modifying capabilities requires a distinct research protocol.

The goal is controlled scientific capability growth, not unconstrained autonomous system modification.

---

## 16. Research milestones

The program is organized into five work packages.

| Phase | Proposed period | Primary deliverable |
|---|---|---|
| WP1 | Months 1-2 | Scientific data contract, benchmark, and initial HARD tools |
| WP2 | Months 3-4 | SOFT encoder integration and fixed-tool scientific model |
| WP3 | Months 5-7 | Multi-model acquisition service with Reticuli/Zeta and scientific validation |
| WP4 | Months 8-9 | First closed-loop acquisition demonstration and controlled ablations |
| WP5 | Months 10-12 | HARD-to-SOFT distillation, multigeneration evaluation, and research release |

The periods are planning assumptions, not estimates based on measured implementation effort.

### WP1 — Scientific foundations

Deliverables:

- Native scientific data interface.
- Curated synthetic and real-data evaluation sets.
- Reference scientific oracles.
- Initial tool library.
- Baseline performance measurements.

**Decision gate:** Can the system correctly execute and evaluate representative scientific workflows using fixed tools?

### WP2 — SOFT model

Deliverables:

- Scientific modality encoder.
- Model-to-tool interface.
- Initial scientific reasoning adaptation.
- Encoder-only and fixed-tool baselines.

**Decision gate:** Does a learned scientific representation improve performance on appropriate held-out tasks?

### WP3 — Verified acquisition

Deliverables:

- Multi-provider agent orchestration.
- Capability request and proposal records.
- Reticuli reconstruction integration.
- Zeta specification-pressure integration.
- Independent Scientific Validation Gate.
- Instrument registry and admission workflow.

**Decision gate:** Can an unfamiliar computational operator be acquired with reproducible software evidence and independent scientific validation?

### WP4 — Capability growth

Deliverables:

- Repeated acquisition trials.
- Reuse and transfer experiments.
- Heterogeneous-model comparisons.
- Verification ablations.
- Cost and reliability analysis.

**Decision gate:** Does dynamic acquisition provide additional validated scientific capabilities beyond a fixed library and disposable code-generation baseline?

### WP5 — Internalization

Deliverables:

- Distillation corpus.
- Tool-selection and representation-distillation experiments.
- Student checkpoints.
- Retention and regression evaluations.
- Complete reproducibility package.

**Decision gate:** Does the trained student exhibit transferable improvements attributable to qualified HARD-derived supervision?

---

## 17. Resources and infrastructure

The initial program should prioritize research validity over large-scale pretraining.

### 17.1 Computing infrastructure

Required resources include:

- GPU inference and fine-tuning capacity.
- CPU resources for scientific numerical calculations.
- High-throughput storage for native scientific data.
- Isolated execution environments for candidate tools.
- External model API access.
- A reproducible artifact and evidence store.

Distributed job execution should distinguish routine scientific analysis, exploratory acquisition, independent audit, and model training.

These activities have different reliability, isolation, and scheduling requirements.

### 17.2 Staffing

A minimally viable research effort would benefit from expertise in:

- Foundation-model training and multimodal architectures.
- Scientific computing and numerical analysis.
- Agent orchestration and software infrastructure.
- Formal or empirical software verification.
- Domain science.
- Evaluation methodology and research reproducibility.

Some roles can overlap, but scientific validation should not depend exclusively on the agent developers.

### 17.3 Budget management

Compute expenditure should be recorded by capability-acquisition event.

Relevant categories are:

- Proposal inference.
- Independent implementation and reconstruction.
- Challenge generation.
- Software acceptance audits.
- Scientific validation.
- Tool execution.
- Distillation training.
- Benchmark evaluation.

This enables analysis of the marginal value of each external model and each acquired instrument.

The program should favor small, well-characterized experiments until acquisition yield and transfer benefit have been demonstrated.

---

## 18. Expected contributions

If successful, the research program could make five contributions.

**1. HARD/SOFT scientific multimodal architecture**

An explicit architecture combining learned scientific representations with native-data computational instruments.

**2. Verified scientific tool acquisition**

A method for acquiring and reusing computational capabilities through externally generated proposals and independent acceptance evidence.

**3. Specification-driven scientific capability evolution**

A mechanism in which reconstruction differences and adversarial tests provide evidence for refining computational specifications.

**4. Tool-to-model capability transfer**

A framework for distilling externally executed scientific operations into tool-selection policies, learned numerical approximations, and scientific representations.

**5. Evaluation of cumulative scientific capability growth**

An experimental methodology that measures whether successive acquisition cycles improve reusable scientific competence under controlled resources and held-out testing.

The strongest scientific contribution would not be a large number of generated tools. It would be evidence that **verified tool acquisition and internalization produce cumulative improvements that remain valid on novel scientific tasks**.

---

## 19. Limitations and failure conditions

The proposed architecture has several possible failure modes.

External models may generate many plausible tools but few scientifically useful ones.

Reconstructed implementations may share systematic errors.

Acceptance criteria may fail to constrain essential behavior.

Scientific validation may be expensive or impossible for some novel hypotheses.

The acquisition process may spend more compute than a conventional tool-development approach.

Distillation may produce task-specific imitation without transferable representation learning.

Repeated student updates may cause catastrophic forgetting.

A growing instrument library may also create retrieval, compatibility, and maintenance difficulties.

The research should therefore define conditions under which the central hypotheses are rejected.

Examples include:

- No improvement over fixed-tool baselines on held-out tasks.
- Acquired tools that cannot be reliably reused.
- Independent reconstruction that provides no measurable defect-detection benefit.
- Distillation that fails to preserve acquired competencies.
- Improvements explained entirely by increased compute or external model strength.
- A capability library whose maintenance and validation costs grow faster than its useful task coverage.

Negative findings would still clarify the limits of verified capability acquisition.

---

## 20. Long-term research trajectory

The initial system is a scientific reasoning model that can acquire new tools.

The next stage is a scientific model that learns from those tools.

A more ambitious stage would investigate the acquisition of new scientific representations.

For example, repeated analyses might reveal that a family of scientific tasks is best described using a derived representation absent from the system's initial modality architecture.

External models could propose the representation, construct the transformations needed to compute it, and develop tests that characterize its scientific meaning.

The system could then train a new encoder or representation module using the resulting data.

This would extend the research from tool acquisition toward representation acquisition.

Such a system might expand not only what computations it can execute, but also what structures it can recognize and reason about internally.

Whether that supports sustained open-ended improvement remains an unanswered question.

The essential requirement is that every claimed increase in capability be accompanied by evidence that distinguishes genuine scientific generalization from additional compute, benchmark adaptation, and accumulated implementation complexity.

---

## 21. Conclusion

This proposal describes a scientific AI architecture in which multimodal learning, computational tool use, software verification, and external foundation models participate in a common capability-development process.

HARD multimodality makes unfamiliar scientific data tractable through executable transformations.

SOFT multimodality provides learned representations and scientific reasoning over those data.

A heterogeneous external model population proposes and challenges new capabilities.

Reticuli and Zeta provide mechanisms for preserving behavioral claims, reconstructing implementations, and exposing weaknesses in specifications.

Independent scientific validation establishes whether acquired instruments are appropriate for their intended scientific applications.

Distillation creates a route for selected external capabilities to influence the model's learned competence.

These processes produce three separately evolving resources: model representations, computational instruments, and scientific specifications.

The central proposition is that a specialized scientific foundation model need not obtain every future capability through increasingly large pretraining runs. It may instead accumulate verified computational knowledge from external intelligence and selectively internalize it through subsequent learning.

**The research objective is to establish whether this process produces measurable, persistent, and transferable scientific capability growth.**

---

## Selected references

1. Wang et al. (2023). *Voyager: An Open-Ended Embodied Agent with Large Language Models.* https://arxiv.org/abs/2305.16291
2. Schick et al. (2023). *Toolformer: Language Models Can Teach Themselves to Use Tools.* https://arxiv.org/abs/2302.04761
3. Wölflein et al. (2025). *LLM Agents Making Agent Tools.* ACL 2025. https://arxiv.org/abs/2502.11705
4. Kang et al. (2025). *Distilling LLM Agent into Small Models with Retrieval and Code Tools.* https://arxiv.org/abs/2505.17612
5. Chen et al. (2025). *ScienceAgentBench: Toward Rigorous Assessment of Language Agents for Data-Driven Scientific Discovery.* ICLR 2025. https://proceedings.iclr.cc/paper_files/paper/2025/hash/f12b4df26344f3be803c06b555252efe-Abstract-Conference.html
6. Johns Hopkins Turbulence Database. https://turbulence.idies.jhu.edu/
7. Reticuli repository and technical specifications. https://github.com/rz4/reticuli
8. Zeta architecture and experimental research. https://github.com/rz4/reticuli/blob/main/zeta/README.md
