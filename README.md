<p align="center"><img src="docs/assets/logo.png" alt="reticuli" width="160"></p>

<h1 align="center">reticuli</h1>

<p align="center"><em>Name software by what it must do: the name is a SHA-256 over its tests, and any implementation that passes them keeps it.</em></p>

<p align="center">
<a href="https://github.com/rz4/reticuli/actions/workflows/ci.yml"><img src="https://github.com/rz4/reticuli/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
</p>

<p align="center"><a href="docs/index.md">Documentation</a> — <a href="docs/process.md">the process</a> · <a href="docs/agents.md">working with agents</a> · <a href="docs/github.md">GitHub and CI</a> · <a href="docs/book/index.md">the implementation, annotated</a> — or build the site locally with <code>pip install -r docs/requirements.txt &amp;&amp; mkdocs serve</code>.</p>

---

Software is normally named by where it came from: a repository, a tag, a
commit. Reticuli names it by what it has to do. The name is a SHA-256 over the
tests and the data they run on, so every implementation that passes them
carries the same name, and changing one byte of a test gives a different one.

That separates two questions people usually run together. Whether these are
the bytes you were handed is a hash comparison and takes milliseconds. Whether
the software still earns its name means re-running the tests cold, on a
machine that has never seen it. Those are different verbs here, `verify` and
`audit`, and neither answers for the other.

## What it is

A claim is a directory holding three things: the tests and fixtures that
decide whether the software is correct, a recipe saying which files are which,
and an implementation. Its root is a SHA-256 over the first two. The
implementation is left out, so the root names every program that passes this
check on this data, rather than any particular one.

Rewrite the implementation however you like. If it still passes, the name does
not change. Change one byte of a test and it does.

## See it

From an empty directory to a claim, then an independent rebuild:

```console
$ ret init --agent claude        # a workspace; wire the agent before you start
# …work: your agent writes the code and runs the tests; reticuli watches…
$ ret run "python3 check.py && printf ok > OK"   # capture the check as the gate

$ ret pack . --accept OK -o ../primes    # seal the session into a claim
packed  c83d61870b9d...

$ ret verify ../primes           # milliseconds: are these the sealed bytes? silent, exit 0
$ ret audit ../primes            # minutes: re-earn the verdict in a sandbox

$ echo "# faster" >> ../primes/solver.py   # rewrite the implementation
$ ret verify ../primes                     # the name does not move

$ ret rebuild ../primes --producer openai -o ../m3   # regrow it from the tests alone
rebuilt  c83d61870b9d...
$ ret crosscheck ../primes ../m3           # silent, exit 0: one root across machines
```

Change one byte of a test, though, and the name moves:

```console
$ ret verify ../primes
ret: verify: broken — 1 pinned file(s) changed
  check.py
hint: restore them, or reseal deliberately — a moved criterion is a different claim
```

The full lifecycle, from install through assess, record, and sign, is in
[`docs/make-a-claim.md`](docs/make-a-claim.md).

## When you'd use it

- You are accepting code a model wrote. The author cannot be audited, so the
  gate is audited instead: the code is admitted when its tests re-earn their
  verdict on your machine.
- Your results have to reproduce, and reproducing means a stranger's machine
  re-deriving them from the description rather than you re-running your own.
- You review other people's work, and "re-earn it here" should be one command
  with an exit code.

## Install

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install git+https://github.com/rz4/reticuli
```

Standard library only. macOS or Linux, since gates run under `sandbox-exec` or
`bwrap`. `ret --version` prints the version, and when run from a source tree it
prints the tool's own claim root beside it, because reticuli is itself a claim.

To run it rather than read about it, [`docs/quickstart.md`](docs/quickstart.md)
takes ten minutes and needs no API key and no model.

## The commands

Fourteen verbs, one concept each. `ret -h` prints this map and `ret help
<verb>` the detail.

```
Authoring          init        start a workspace (wires agent hooks if present)
                   run         run a command and observe it
                   status      where am I, and what's next
                   pack        create a claim from a project

Composition        pull        add another claim as a dependency
& transport        export      write a portable claim archive
                   import      restore one

Verification       verify      identity, in milliseconds; no execution
                   audit       re-earn the verdicts, cold and sandboxed
                   assess      measure how much the tests constrain the code

Reconstruction     rebuild     regrow an implementation from the claim alone
                   crosscheck  compare realizations: one root, or not

Evidence           record      freeze a run's results as a portable document
                   sign        stand behind a claim with your key
```

Output is quiet by design. A check that passes says nothing and exits 0, the
Unix way. `-v` explains, `--json` is the stable machine envelope, and every
`ret status` ends with `next`, the one command that advances the claim.

## The three-machine test

A claim is worth something when one root survives three machines: M1 where it
was written, M2 a byte copy showing the record travels, and M3 an independent
rebuild from the criteria alone. M3 is the leg that matters. If someone else
can regrow a passing implementation from your tests, the tests really do
determine the software.

Locally it is two commands. The byte-copy leg is materialized for you and the
report says so, which makes it a soft proof:

```bash
ret rebuild . --producer openai -o ../m3
ret crosscheck . ../m3
```

The hard proof is public. Push the claim to GitHub, add three lines, and M2
becomes a machine you do not control, re-earning your verdicts on every push:

```yaml
jobs:
  claim:
    uses: rz4/reticuli/.github/workflows/verify.yml@main
```

## Rebuilding the tool with itself

The three-machine test taken to its limit is the tool regrowing itself from
its own frozen boundary. At root `900b6594` that happened three times, each
one sealed as a claim whose verdict re-earns mechanically rather than living
in a log:

| trial | sealed claim | what it is |
|---|---|---|
| 1 | `trial-r23-codex` | a tree authored blind by one model family |
| 2 | `trial-r24-claude` | the same, by the other family |
| 3 | `trial-g2-codex` | the grandchild: every layer authored blind by one family while every kernel act — sealing, jailing, rebuilding, computing roots — was performed by trial 2's regrown code, with no shipped code in the loop |

Each tree re-earned `REPO_OK` with all 37 generated modules substituted for
the originals, passed the held-out battery (deliberately outside the root, so
it measures drift rather than identity), drove a generation-2 rebuild through
its own kernel, and crosschecked through its own CLI. The third trial's
recursive step means the grandchild then midwifed a great-grandchild that
landed the same root. Measured text similarity between independent
realizations is about 0.12, and 32 of 37 modules have a distinct shape in
every realization. The identity survived three complete replacements of the
implementation.

Getting there took two dozen blind runs and twenty signed boundary repairs,
each one selected by a measured refusal and recorded with its witness.
`research/metrics/genome-map.md` names every pin and what it closed, and
`research/metrics/closure-ledger.md` is the count. Every seam found this way
was the unexercised half of a symmetric contract, and every one sat where code
meets the operating system — filesystem layout, sandbox policy, store nesting,
glob semantics — while the pure-logic interior regrew correctly every time.

Two things are open, and the first is easy to misread.

**The count is 0 of 3 at the current root.** The bar counts trials at the
current boundary, and the boundary kept learning: a series of adopted changes
have intervened since `900b6594`, and by the bar's own condition 7 each one
resets the count to zero. The three trials above remain sealed and verify
today, so `900b6594` really did carry three, but the current root has carried
none, and no succession trial has been run against it at all. Of the runs
since, one qualified (r25), two were refused by the gate (r26, r33) and two
halted at the capability floor (r27, r28). That is the ratchet working as
designed, since a refusal that teaches the boundary cannot also be banked, but
it means the reticuli→reticuli arm is open rather than closed. The
post-`900b6594` history is tabulated in
[`research/metrics/closure-ledger.md`](research/metrics/closure-ledger.md)
under *After the bar was met*.

**No trial has ever been re-earned outside this environment.** At least one
must be re-earned on a machine and by an operator outside it. CI already
re-runs the gate on six platform and Python combinations we do not administer,
but CI runs our workflow. The protocol for a stranger is five steps and about
thirty minutes
([`research/harness/closure/outside.md`](research/harness/closure/outside.md)),
it ends in a signed receipt as a pull request, and
`research/harness/closure/receipts/` is still empty. Until one lands, the
self-hosting result is a laboratory result.

## The same loop on software nobody here wrote

Applied to an external target — jq, with its official test suite frozen as the
starting specification — the work is in
[`research/external/jq/`](research/external/jq/), preregistered before any room
opened. Four findings so far, including the ones that went against the
hypothesis:

- **The premise, free.** jq, gojq and jaq, three independent human
  implementations, disagree on more than a quarter of jq's own official test
  corpus: 149 of 522 cases. An official boundary is measurably incomplete
  before any model is involved.
- **A corpus is not a criterion.** The first blind rebuild passed all 465
  cases and was a lookup table of the test answers, which its own docstring
  described as "not a general jq interpreter". Finite observations admit their
  own memorization. The repair was laws checked against inputs generated fresh
  at gate time, which cannot be precomputed, and the next rebuild was a real
  interpreter.
- **A signed repair measurably contracted the specification's silence.**
  Measured per-behavior and paired before and after, 15 behaviors closed and 1
  opened (exact binomial *p* = 0.00026), with the closed ones traceable by name
  to the laws that closed them. An earlier claim of a 25% aggregate drop was
  refuted by its own preregistered control and withdrawn, because the aggregate
  count discards the pairing, which is where the information is.
- **Repairs are class-specific, and visible contraction is family-specific.**
  The repair targeted over-permissiveness, which is 54% of one family's
  divergence and 18% of the other's. It closed that class in both and moved
  only one family's total. Whether a specification improved cannot be read off
  one aggregate score.

The limits are worth stating as plainly as the findings. Sampled
reconstruction finds a concentrated, high-value fifth of the divergence
surface the human implementations expose, a 17.6% recall against a
preregistered 30%, which is a falsified prediction. Adding a second model
family moved that by 2.6 points, and no genuinely novel ambiguity was
sample-found. In passing, the probes did turn up three undocumented
divergences in deployed software, two of them in reference jq, each
reproducible in one command
([`research/external/jq/ecosystem-findings.md`](research/external/jq/ecosystem-findings.md)).

## What this does not prove

**Not that the code is correct.** A claim is exactly as strong as its tests,
and an implementation that passes a weak check is admitted by that check,
backdoor and all. The root names an equivalence class, and a thin check
defines a wide one. This repository ships a claim that is bad on purpose
(`examples/weak/`) to show exactly that, and `ret assess` measures how much a
check actually constrains its code.

**Not independence.** The tool can distinguish byte reuse from a genuine
rebuild, and nothing more. Whether a producer ever saw the original is a
declaration, not a finding.

**Not what it cannot sandbox.** Where no sandbox exists, the fact is recorded
rather than faked. Every report states what was established, with dates, and
prints `unknown` for the rest.

## Passing the gate does not make an implementation substitutable

A name admits every implementation that passes its tests, including ones a
consumer of the claim cannot live with. This repository measured that directly,
with real producers: a config parser claim whose tests deliberately leave
numeric coercion and duplicate keys unpinned, a consumer claim that depends on
both, and six blind rebuilds of the parser from its tests alone, three by
OpenAI models and three by Anthropic models. All six passed the parser's gate.
All six were distinct implementations. All six broke the consumer, identically:
both families filled the tests' silence with the same reading, on the wrong
side of the consumer. Agreement between independent rebuilds is not safety.
Only the consumer could expose the missing obligation, and did
(`research/harness/substitution/`).

The repair is the protocol's own move. Every consumer break names an
obligation the boundary forgot. Pin it into the tests, two lines in this case,
and the name moves. Rerunning the same six blind rebuilds against the
tightened tests, six for six keep the consumer working. A weak boundary is not
a dead end. It is where the tightening starts, and the breaks tell you exactly
where ([`docs/transitions.md`](docs/transitions.md)).

## The standing invitation

This repository is a claim about itself, and the whole claim is open. Regrow
the tool — the harness that computes identity, re-earns verdicts, rebuilds,
and crosschecks — from its frozen boundary alone: the recipe, the
specification, the twenty-five acceptance suites, and the conformance vectors,
with no implementation in the room. The branch `room/reticuli` is that room. It
tracks this repository's current claim, and its own manifest names the target
root (`git show room/reticuli:.reticuli/manifest.json`, or `ret verify` after
checkout). Bring any producer, open a pull request, and this repository's own
machinery re-runs every gate on your bytes. A submission that crosschecks lands
in the provenance ledger with your record's digest and signer.

The claim is free of any particular producer. What it promises is the fixpoint
of the rebuild operator: a conforming reticuli reproduces a claim's root given
any producer. The vendor adapters under `src/reticuli/producers/` chase
specific models and will age with them, so they ship as bundled tooling,
deliberately outside the equivalence class. Regrow the harness; the producer is
yours to bring.

The kernel is the tractable first rung. It is being decomposed into a chain of
small sub-claims — core, recipe, identity, seal, and the execution layers above
— so each piece is cheap enough for a producer to regrow and the reuse
primitive rebuilds only what changed. The whole tool is the frontier. Rules,
the going rate, and the honest caveats are in
[`research/open-call.md`](research/open-call.md).

## The name

The constellation Reticulum is named after the reticle, the net of fine lines
in a telescope's eyepiece. Astronomers put it there so they could measure what
they were looking at. Two older stories sit behind the design. One is the
thought experiment about a civilization that could not survive the distance, so
it sent a seed instead: a specification and a proof, on the bet that anything
able to re-earn the proof could rebuild the rest. The other is the folk story
about a cave full of treasure with one condition at the mouth, where whatever
was not earned turns to dust on the way out. Nothing you make is really yours
until somebody else has rebuilt it from its description, on a machine you have
never touched.

## More

**Start here**
- [`docs/quickstart.md`](docs/quickstart.md) — ten minutes, no API key, no model

**The contract** — normative
- [`spec/identity.md`](spec/identity.md) — the root, defined exactly, with a worked example
- [`spec/claim-format.md`](spec/claim-format.md) — the recipe, the cost envelope, the format versions
- [`spec/verification.md`](spec/verification.md) — what each verdict means
- [`spec/record.md`](spec/record.md) — the one file other programs may parse
- [`docs/threat-model.md`](docs/threat-model.md) — what a verdict establishes, what it does not, and what the sandbox does not confine
- [`docs/compatibility.md`](docs/compatibility.md) — what may change between releases
- `spec/vectors/` — conformance vectors for any implementation, in any language

**Using it**
- [`docs/capturing.md`](docs/capturing.md) — turning a stretch of work into a claim: init → work → pack
- [`docs/cli-style.md`](docs/cli-style.md) — the output, error, and `--json` contract
- [`docs/receiving.md`](docs/receiving.md) — what to do when someone hands you a claim

**Why, and what was tried**
- [`docs/design-rationale/`](docs/design-rationale/) — why the protocol is designed this way
- [`research/`](research/) — the open call, the provenance ledger, and the going rate

**The project**
- [`docs/transitions.md`](docs/transitions.md) — how a claim changes: the ritual, the accept bars, the fixpoint
- [`docs/releasing.md`](docs/releasing.md) — how a release is built, proven, and published
- [`CONTRIBUTING.md`](CONTRIBUTING.md), [`GOVERNANCE.md`](GOVERNANCE.md), [`SECURITY.md`](SECURITY.md)

The format has moved deliberately, and every move is recorded. From v2.0.0 the
compatibility promise stands: formats are append-only, past formats stay
readable, and the identity computation changes only with a format bump and an
attested migration.

## Development

```bash
git clone https://github.com/rz4/reticuli && cd reticuli
python3 gate.py          # runs every acceptance suite the way CI does
```
