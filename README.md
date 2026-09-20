<p align="center"><img src="docs/assets/logo.png" alt="reticuli" width="160"></p>

<h1 align="center">reticuli</h1>

<p align="center"><em>Name software by what it must do: the name is a SHA-256 over its tests, and any implementation that passes them keeps it.</em></p>

<p align="center">
<a href="https://github.com/rz4/reticuli/actions/workflows/ci.yml"><img src="https://github.com/rz4/reticuli/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
</p>

---

The constellation Reticulum is named after the reticle, the net of fine lines
in a telescope's eyepiece. Astronomers put it there so they could measure what
they were looking at. There is also an old thought experiment about a
civilization that couldn't survive the distance, so it sent a seed instead: a
specification and a proof, on the bet that anything able to re-earn the proof
could rebuild the rest. And there is a folk story about a cave full of
treasure, with one condition at the mouth: whatever wasn't earned turns to
dust on the way out. This tool is built on the same suspicion. Nothing you
make is really yours until somebody else has rebuilt it from its description,
on a machine you've never touched.

## What it is

A **claim** is a directory: the tests and fixtures that decide whether the
software is correct, a recipe saying which files are which, and an
implementation. Its **root** is a SHA-256 over the first two. The
implementation is left out, so the root names every program that passes this
exact check on this exact data, not any particular one.

Rewrite the implementation however you like; if it still passes, the name does
not change. Change one byte of a test, and it does.

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

The full lifecycle — install, assess, record, and sign — is in
[`docs/quickstart.md`](docs/quickstart.md).

## When you'd use it

- You accept code a model wrote. You can't audit the author, so you audit the
  gate: the code is admitted when its tests re-earn their verdict on your
  machine.
- Your results have to reproduce. A computation is worth what a stranger's
  machine can re-derive from its description.
- You review other people's work, and "re-earn it here" should be one command
  with an exit code.

## Install

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install git+https://github.com/rz4/reticuli
```

Pure standard library. macOS or Linux (gates run under `sandbox-exec` or
`bwrap`). `ret --version` prints the version — and, run from a source tree, the
tool's own claim root beside it, since reticuli is itself a claim.

New here and want to run it rather than read about it?
[`docs/quickstart.md`](docs/quickstart.md) — ten minutes, no API key, no model.

## The commands

Fourteen verbs, one concept each. `ret -h` prints this map, `ret help <verb>`
the detail.

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
was written, M2 a byte copy proving the record travels, and M3 an independent
rebuild from the criteria alone. M3 is the leg that matters. If someone else
can regrow a passing implementation from your tests, the tests really do
determine the software.

Locally it is two commands. The byte-copy leg is materialized for you and the
report says so; call it a soft proof:

```bash
ret rebuild . --producer openai -o ../m3
ret crosscheck . ../m3
```

The hard proof is public. Push the claim to GitHub, add three lines, and M2
becomes a machine you don't control, re-earning your verdicts on every push:

```yaml
jobs:
  claim:
    uses: rz4/reticuli/.github/workflows/verify.yml@main
```

## What this does not prove

**Not that the code is correct.** A claim is exactly as strong as its tests,
and an implementation that passes a weak check is admitted by that check,
backdoor and all. The root names an equivalence class; a thin check defines a
wide one. This repository ships a claim that is bad on purpose
(`examples/weak/`) to show exactly that. `ret assess` measures how much a
check actually constrains its code.

**Not independence.** The tool can distinguish byte reuse from a genuine
rebuild, and nothing more; whether a producer ever saw the original is a
declaration, not a finding.

**Not what it cannot sandbox.** Where no sandbox exists, the fact is recorded
rather than faked. Every report states what was established, with dates, and
prints `unknown` for the rest.

## The standing invitation

This repository is a claim about itself, and the whole claim is open. Regrow
the tool — the harness that computes identity, re-earns verdicts, rebuilds,
and crosschecks — from its frozen boundary alone: the recipe, the
specification, the nine acceptance suites, and the conformance vectors, with
no implementation in the room. The branch `room/reticuli` is that room; it
tracks this repository's current claim, and its own manifest names the target
root (`git show room/reticuli:.reticuli/manifest.json`, or `ret verify` after
checkout). Bring any producer, open a pull request, and this repository's own
machinery re-runs every gate on your bytes; a submission that crosschecks
lands in the provenance ledger with your record's digest and signer.

The claim is **free of any particular producer.** What it promises is the
fixpoint of the rebuild operator: a conforming reticuli reproduces a claim's
root given *any* producer, so the vendor adapters under
`src/reticuli/producers/` — which chase specific models and will age with
them — are shipped as bundled tooling, deliberately outside the equivalence
class. Regrow the harness; the producer is yours to bring.

The kernel is the tractable first rung. It is now being decomposed into a chain
of small sub-claims — core, recipe, identity, seal, and the execution layers
above — so each piece is cheap enough for a producer to regrow and the reuse
primitive rebuilds only what changed. The whole tool is the frontier. Rules,
the going rate, and the honest caveats:
[`research/open-call.md`](research/open-call.md).

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
