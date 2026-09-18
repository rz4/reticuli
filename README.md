<p align="center"><img src="docs/assets/logo.png" alt="reticuli" width="160"></p>

<h1 align="center">reticuli</h1>

<p align="center"><em>Name software by what it must do: the name is a SHA-256 over its tests, and any implementation that passes them keeps it.</em></p>

<p align="center">
<a href="https://github.com/rz4/reticuli/actions/workflows/ci.yml"><img src="https://github.com/rz4/reticuli/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
</p>

---

The constellation Reticulum is named for the *reticle* — the net of fine lines
set into a telescope's eyepiece so that looking could become measuring. This
tool takes the same turn. It borrows an old thought experiment, too: a
civilization that cannot survive the distance sends not itself but a seed — part
specification, part proof — and trusts whatever can rebuild the pattern from
that seed, and nothing that cannot. And it keeps faith with an older parable
still, of a cave whose treasure carries a single condition at its mouth:
what has not been earned turns to worthless dust the moment it is carried into
daylight. Reticuli is those three ideas made runnable. It fixes the crosshair
on the one thing worth measuring — *does this survive the crossing?* — and lets
nothing be called yours until it has been rebuilt from its description alone,
by someone who is not you, somewhere you have never been.

## What it is

A **claim** is a directory: the tests and fixtures that decide whether the
software is correct, a recipe saying which files are which, and an
implementation. Its **root** is a SHA-256 over the first two — the
implementation is deliberately left out. So the root names not one program but
*every* program that passes this exact check on this exact data.

Rewrite the implementation however you like; if it still passes, the name does
not change. Change one byte of a test, and it does.

## See it

```console
$ ret pack --accept PASSED --claim check.py -o ../primes
packed  db302fccb091...

$ ret verify          # milliseconds: are these the sealed bytes?
                      # silent, exit 0 — yes

$ ret audit           # minutes: re-earn the verdict in a sandbox
                      # silent, exit 0 — earned

$ echo "# faster" >> primes.py   # rewrite the implementation...
$ ret verify                     # ...the name does not move
                                 # silent

$ ret rebuild . --producer openai -o ../m3   # regrow it from the test alone
rebuilt  db302fccb091...                      # a different program, same root

$ diff primes.py ../m3/primes.py             # trial division vs a sieve
4,9c4,9
<     i = 2
<     while i * i <= n:
...

$ ret crosscheck . ../m3 --record-proof
                      # silent, exit 0 — one root across three machines

$ ret status
claim      primes
root       db302fccb091...
identity   fresh
audited    2026-09-18T03:06:32Z on this machine
proof      recorded
signed     none

next  measure the tests: ret assess .
```

Break a test and `verify` does not just say no — it says which file moved:

```console
$ ret verify
ret: verify: broken — 1 pinned file(s) changed
  check.py
hint: restore them, or reseal deliberately — a moved criterion is a different claim
```

## When you'd use it

- **You accept model-written code.** Audit the gate, not the author: a claim
  lets you take an implementation you didn't write once its tests re-earn their
  verdict on your machine.
- **Your results must reproduce.** A computation that "worked" is worth what a
  stranger's machine can re-derive from its description — not what your cache
  remembers.
- **You review other people's work.** "Re-earn it here" becomes one command,
  sandboxed, with an exit code, instead of an afternoon.

## Install

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install git+https://github.com/rz4/reticuli
```

Pure standard library. macOS or Linux (gates run under `sandbox-exec` or
`bwrap`). `ret --version` names the tool by its own claim root.

## The commands

Fourteen verbs, one concept each; `ret -h` prints this map, `ret help <verb>`
the detail.

```
Authoring          init        start a workspace (wires agent hooks if present)
                   run         run a command and observe it
                   status      where am I, and what's next
                   pack        create a claim from a project

Composition        pull        add another claim as a dependency
& transport        export      write a portable claim archive
                   import      restore one

Verification       verify      identity, in milliseconds — no execution
                   audit       re-earn the verdicts, cold and sandboxed
                   assess      measure how much the tests constrain the code

Reconstruction     rebuild     regrow an implementation from the claim alone
                   crosscheck  compare realizations: one root, or not

Evidence           record      freeze a run's results as a portable document
                   sign        stand behind a claim with your key
```

Output is quiet by design: a check that passes says nothing and exits 0, the
Unix way. `-v` explains, `--json` is the stable machine envelope, and every
`ret status` ends with `next` — the one command that advances the claim.

## The three-machine test

A claim is worth something when one root survives three machines: **M1** where
it was written, **M2** a byte copy proving the record travels, and **M3** an
independent rebuild from the criteria *alone*. M3 is the one that matters — if
someone else regrows a passing implementation from your tests, the tests really
do determine the software.

Locally it is two commands (the byte-copy leg is materialized for you, and the
report says so — a *soft* proof):

```bash
ret rebuild . --producer openai -o ../m3
ret crosscheck . ../m3
```

The *hard* proof is public. Push the claim to GitHub and add three lines, and
M2 becomes a machine you do not control, re-earning your verdicts on every push:

```yaml
jobs:
  claim:
    uses: rz4/reticuli/.github/workflows/verify.yml@main
```

## What this does not prove

**Not that the code is correct.** A claim is exactly as strong as its tests. An
implementation that passes a weak check is admitted by that check, backdoor and
all — the root names an equivalence class, and a thin check defines a wide one.
This repository ships a claim (`examples/weak/`) that is bad on purpose, to show
exactly that. Run `ret assess` to measure how much a check actually constrains
its code.

**Not independence** — only byte-reuse distinguished from a genuine rebuild.
**Not what it cannot sandbox**: where no sandbox exists the fact is recorded,
never faked. Reticuli reports what it established, with dates, and prints
`unknown` for the rest. It itemizes confidence; it does not sell it.

## The standing invitation

This repository is a claim about itself, and its kernel claim is open. The root
is `82a813574c5f231d4e8be277da5dace4d79add8c6025171589a48f2f825e5ebc`; the
branch `room/kernel-82a81357` is the blind room — the acceptance suite and no
implementation. Regrow `reticuli/kernel.py` from the suite alone, by any
producer, and open a pull request: the gates are re-run here, on your bytes, and
a submission that crosschecks lands in the provenance ledger with your record's
digest and signer. The rules and the honest caveats are in
[`docs/open-call.md`](docs/open-call.md).

## More

- [`spec/identity.md`](spec/identity.md) — the root, defined exactly, with a worked example
- [`spec/claim-format.md`](spec/claim-format.md) — the recipe, the cost envelope, the format versions
- [`spec/verification.md`](spec/verification.md) — what each verdict means
- [`spec/record.md`](spec/record.md) — the one file other programs may parse
- [`docs/cli-style.md`](docs/cli-style.md) — the output and error contract
- [`docs/receiving.md`](docs/receiving.md) — what to do when someone hands you a claim
- `spec/vectors/` — conformance vectors any implementation, in any language, can be held to

The format has moved deliberately, and every move is recorded. From v2.0.0 the
compatibility promise stands: formats are append-only, every past format stays
readable, and the identity computation changes only with a format bump and an
attested migration.

## Development

```bash
git clone https://github.com/rz4/reticuli && cd reticuli
python3 gate.py          # runs every acceptance suite the way CI does
```
