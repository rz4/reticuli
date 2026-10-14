# A measured-improvement instrument

Research tooling, outside the repository's sealed boundary. Standard-library
Python, no model calls or API keys. This implements the first local instrument
from the self-improvement proposal: compare two probe generators under matched
budgets and retain evidence that another process can re-earn.

Run from the repository root, on Linux or macOS:

```bash
python3 research/harness/improvement/campaign.py run --out /tmp/improvement-campaign
python3 research/harness/improvement/campaign.py replay /tmp/improvement-campaign
python3 tests/test_improvement.py
```

An output directory must not already exist. Each campaign has seven controlled
targets in three families: config parsing, base64 decoding, and query parsing.
All fixture realizations pass their disclosed gates. Three targets have identical
realization behavior that breaks a consumer, and one is a negative control.
Consumer-backed omission labels are counted once per run, rather than counting
every input or implementation partition as a separate discovery.

The bundled strategies are deliberately simple: a generator restricted to
ordinary valid inputs, and a hand-written generator that adds boundary probes.
The latter recovers the planted obligations. **This calibrates the instrument;
it is not a learned successor, hidden evaluation, or evidence of recursive
self-improvement.** Promotion is explicitly incomplete in every summary.

## Automatic policy improvement

The next layer generates and selects its own successors:

```bash
python3 research/harness/improvement/evolve.py run --out /tmp/investigator-lineage --rounds 3
python3 research/harness/improvement/evolve.py replay /tmp/investigator-lineage
python3 tests/test_evolution.py
```

The initial investigator repeats ordinary examples from the public gate. Its
`--propose` mode emits extensions to its current probe policy, using its
development search history to order the proposals. The controller compiles each
extension into a standalone successor, evaluates every proposal under the same
per-run limits, and selects one using training scores only. The selected
successor then faces a second panel: different realization pools and a
different seed range, but the same omission labels as the training panel.
Local adoption requires a minimum gain on both panels, no validation-target
regression, and no failed candidate runs. A rejection keeps the parent active
and stops the search. An accepted successor becomes the program that proposes
the next round's extensions.

The second panel is therefore a check that the same probes still find the same
obligations when the implementations agree with each other. It is not a test of
transfer to unseen obligations, and it cannot detect a policy fitted to this
label set: in the recorded eight-round search the two panels agree to four
decimal places at every generation.

This is **automatic, bounded optimization of an investigator's probe policy**.
The seven mutation operations, compiler, learner and evaluator are human-authored.
It changes the generated investigator's source and inherits learned operations;
it does not invent new operations, change model weights, or improve its own
evaluation rules.

Read the ceiling of 1.0 as a property of that vocabulary rather than a
measurement. The seven operations are an exact minimal cover of the eight
planted omissions, with `duplicate` covering one per family and nothing left
over. Every operation therefore earns a positive gain, every one is adopted,
and recall reaches 1.0 in the same round the vocabulary runs out. Selection
never has to reject a proposal on its merits, because the vocabulary contains
no operation that finds nothing. Adding such distractors is the cheapest way
to make the selection rule carry evidence; until then
`test_high_threshold_leaves_parent_active` exercises the rejection path only by
setting a gain requirement no proposal can meet.

Public sibling fixtures test different realization pools;
they are not hidden tasks or independent software targets. Final results also
compare the active investigator with the frozen initial investigator on the same
panel. This comparison does not establish an advantage over a conventional
evolutionary-search baseline or a frozen successor-generation algorithm.

Search costs include every candidate's training runs, parent evaluations,
validation runs, and the final/frozen comparison. The search has bounded rounds,
seeds, probe counts, and candidate vocabulary. When the vocabulary is exhausted
or a challenger fails the conditions, it stops instead of declaring further
improvement. The output retains failed candidates, every adoption decision,
source digests, inherited policies, and the active generation. It never updates
the repository's product implementation or signs an external promotion.

Lineage replay regenerates proposals through each retained parent, checks source
inheritance, verifies that retained probes actually belong to the claimed
compiled policy, re-executes the observations, and recomputes selection and
adoption decisions. The output includes a Reticuli recipe whose gate writes
`LINEAGE_OK` after replay. Its self-contained source snapshot can replay without
the working tree:

```bash
python3 /tmp/investigator-lineage/evolve.py replay /tmp/investigator-lineage
(cd /tmp/investigator-lineage && python3 check_lineage.py)
```

Use the same development sealing and auditing commands below with the lineage
directory. The claim establishes that the recorded local optimization lineage
re-earns, while external promotion remains incomplete.

Two independent runs of the same search reach the same policies, the same
decisions and the same scores, yet seal to different roots, because every run
record retains its own `elapsed_seconds` and standard-error excerpt. The root
of a lineage directory therefore names one transcript, not the result. Strip
the timing out of the sealed set, and the root would name the result as well:
the content is already identical without it.

## The protocol

Supply a standalone Python candidate with `--candidate /absolute/path/worker.py`.
It runs in a temporary working directory with Python's `-I` flag. The controller
sends one JSON line containing `schema`, `event: start`, `target`, `seed`, and
`budget`. The target contains the public gate, family, realization names, and a
boundary digest. That digest names this fixture contract; it is **not** a
Reticuli claim root.

The worker sends one request at a time:

```json
{"op": "probe", "input": "a=12"}
```

The controller executes the probe against the fixed realization pool and replies
with `event: observation` and `observations`. It does not send omission labels
or consumer expectations to the worker. A worker may use previous observations
to select its next probe. Finish with `{"op": "finish"}`. The bundled
`investigator.py` is a complete protocol example.

Budgets are controller-enforced: maximum probe requests, maximum input bytes,
maximum response bytes, and a wall-time deadline. Probe and target-call counts
are recorded separately. A request beyond the probe cap stops the run with
`budget_exhausted`; crashing, invalid protocol, or timing out preserves earlier
witnesses but receives zero discovery credit in the assigned-run analysis.
The controller terminates the candidate process group after each run.

**Candidates must be trusted local development programs.** A temporary directory,
minimal environment, and subprocess boundary do not provide filesystem or
network confinement. The fixture code and labels are public. Do not use this
runner for untrusted code or claim it enforces a hidden benchmark. Platform
sandboxing and separate private evaluation service are required before the
proposal's confirmatory experiment.

## What the output establishes

The manifest pins the evaluator code, candidate source and strategy, budgets,
assigned targets and seeds, and individual run records. Each run retains every
input, realization observation, consumer expectation, discovered omission,
status, resource count, and score. The summary averages recall over runs within
each target and then over targets with planted omissions; controls are reported
separately and have no invented recall denominator. Failed assigned runs remain
in the means. Arm order alternates by seed.

Replay checks source and evidence digests, re-executes every fixture observation,
recomputes scores, checks that no assigned run was omitted or duplicated, and
recomputes the summary. It requires the recorded evaluator version; the output
includes a self-contained source snapshot:

```bash
python3 /tmp/improvement-campaign/campaign.py replay /tmp/improvement-campaign
```

Checksums detect alteration relative to the manifest. They do not authenticate
the author or prove that a process used its declared resources. Replay verifies
the retained deterministic evidence; rerunning a candidate is a new experiment.
The baseline is intentionally weak, both generators are authored by hand, and
all tasks are development fixtures. No statistical significance is reported.

## A Reticuli evidence claim

The campaign also emits `reticuli.toml` and `check_replay.py`. Every input record,
the candidate sources, evaluator sources, and summary are pinned. The gate
replays the evidence and writes `EVIDENCE_OK`. This claim says that the retained
observations and summary re-earn; it does not say the candidate is an improved
general-purpose investigator.

For the repository's development sealing path:

```bash
(cd /tmp/improvement-campaign && python3 check_replay.py)
PYTHONPATH=src python3 -c 'import sys; from reticuli import kernel; print(kernel.seal(sys.argv[1])["root"])' /tmp/improvement-campaign
PYTHONPATH=src python3 -m reticuli verify /tmp/improvement-campaign
PYTHONPATH=src python3 -m reticuli audit /tmp/improvement-campaign
```

Run the gate before sealing: `kernel.seal` computes identity and does not execute
acceptance tests. `audit` re-earns the gate under the platform's sandbox policy.
The artifact contains no producer outputs to reconstruct; it is an evidence
claim. The sources and retained records must travel with it.

## Next experiments

Add stronger property-based and generic model-guided baselines, measure the
engineering and candidate-search costs, implement independently administered
held-out evaluation, and preregister a cluster-aware analysis before confirming
one successor. Then compare successor production guided by the accepted
investigator with production guided by a frozen baseline. The current harness
provides the local instrumentation and failure checks for that work.
