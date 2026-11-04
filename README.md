<p align="center"><img src="docs/assets/logo.png" alt="reticuli" width="160"></p>

<h1 align="center">reticuli</h1>

<p align="center"><em>Name software by what it must do: the name is a SHA-256 over its tests, and any implementation that passes them keeps it.</em></p>

<p align="center">
<a href="https://github.com/rz4/reticuli/actions/workflows/ci.yml"><img src="https://github.com/rz4/reticuli/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
</p>

<p align="center"><strong><a href="https://rz4.github.io/reticuli/">The reticuli manual</a></strong> — install, tutorials, task guides, and the full command reference.</p>

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

To run it rather than read about it, the manual's
[quickstart](https://rz4.github.io/reticuli/quickstart/) takes ten minutes and
needs no API key and no model.

## The commands

Fourteen verbs, one concept each. `ret -h` prints this map and `ret help
<verb>` the detail; the
[full reference](https://rz4.github.io/reticuli/cli/) is in the manual.

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

Locally it is two commands, and the byte-copy leg is materialized for you,
which the report says, making it a soft proof:

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

## What has been measured

Three findings, each with its method and its limits, in
[`findings/`](findings/). Two of them contain a prediction this project made
and then falsified.

- **[Self-hosting](findings/self-hosting.md)** — the tool regrew itself from
  its own frozen boundary three times, three generations deep, at about 0.12
  text similarity between realizations. The arm is nonetheless **open**: 0 of
  3 at the current root, and no trial has ever been re-earned outside this
  environment.
- **[The jq external target](findings/jq.md)** — three independent human
  implementations disagree on 28.5% of jq's own official test corpus, and the
  first blind rebuild passed 465 of 465 cases by being a lookup table.
  Recall against the human divergence surface was 17.6% against a
  preregistered 30%, so that prediction is falsified.
- **[Substitution](findings/substitution.md)** — six blind rebuilds from two
  model families all passed the parser's gate, all differed by bytes, and all
  six broke the consumer identically. Agreement between independent rebuilds
  is not safety.

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

The full boundary is
[what a claim proves, and what it does not](https://rz4.github.io/reticuli/threat-model/).

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

Rules, the going rate, and the honest caveats are in
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

## The material you can check

The manual carries the prose. What follows is what the manual deliberately
does not render — the bytes themselves, which are the identity, and the
working record behind the findings.

**The contract, normative and pinned**
- [`spec/identity.md`](spec/identity.md) — the root, defined exactly, with a worked example
- [`spec/claim-format.md`](spec/claim-format.md) — the recipe, the cost envelope, the format versions
- [`spec/verification.md`](spec/verification.md) — what each verdict means
- [`spec/record.md`](spec/record.md) — the one file other programs may parse
- [`spec/vectors/`](spec/vectors/) — conformance vectors for any implementation, in any language

**The evidence**
- [`findings/`](findings/) — what has been measured, with its limits
- [`research/`](research/) — the open call, the ledgers, the preregistrations, the provenance records

**Worked claims**
- [`examples/`](examples/) — including `examples/weak/`, a claim that passes everything and is still nearly worthless

**The project**
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
