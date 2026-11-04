# Make a claim

*Informational — a hands-on guide. The normative contract is in [`spec/`](https://github.com/rz4/reticuli/tree/main/spec/).*

This is authoring, from the other side of the table. [The
quickstart](quickstart.md) receives and judges a claim someone else made;
this page makes one. It covers the whole life of a claim in about fifteen
minutes, from an empty directory to a signed, independently rebuilt result.
No API key is needed to follow along, and the one step that spends money is
called out where it appears.

## Install

Reticuli is not yet on a public index, so install from a clone into a
virtualenv:

```
git clone https://github.com/rz4/reticuli.git && cd reticuli
python3 -m venv .venv && source .venv/bin/activate
pip install .
ret --version
```

Standard library only, macOS or Linux. If you would rather not install it,
the fact that the tool is pure stdlib means you can run it from a checkout:
every `ret …` below becomes `python3 -m reticuli …` with `PYTHONPATH=src`
set.

One note on output. A check that passes exits 0 and stays quiet, the Unix
way. Piped, redirected, or in CI, a passing command prints nothing and the
exit code is the whole answer. In an interactive terminal you also get a
one-line confirmation on stderr, so you can tell "passed" from "nothing
happened", and it never touches stdout or the exit code. The fuller blocks
shown here appear under `-v`.

## 1. Start a project

An ordinary directory, made a git repo, made a reticuli workspace:

```
$ mkdir primes && cd primes && git init -q
$ ret init --agent claude
initialized  .  agent=claude
```

That wires the Claude Code hooks and marks the workspace, and `ret init -v`
spells out each file it touched. Working without an agent, `ret init --agent
generic` prints a short contract for wiring any other harness to `ret hook`.

`ret init` marks a workspace the way `git init` marks a repo, rather than
starting a session. Work here for minutes or months and the same trace keeps
filling. `--agent claude` wires the observation hooks now, before you launch
the agent, so the session is captured, because Claude Code reads its settings
at startup. For any other harness, use `--agent generic` and point it at `ret
hook`; see [`capturing.md`](capturing.md).

## 2. Do the work

Write a test, and let the implementation be written for you. With the hooks
wired, run `claude` and work. It writes `solver.py`, reads your `check.py`,
and the hooks record all of it. Here is a test to start from:

```python
# check.py
from solver import is_prime
assert [n for n in range(20) if is_prime(n)] == [2, 3, 5, 7, 11, 13, 17, 19]
```

Then ask the agent for the implementation. Point it at the check as the
contract rather than describing the function in prose, for example:

> Implement `solver.py` so that `python3 check.py` passes. Read `check.py`
> first: it is the entire specification, and anything it does not demand is
> your choice. Write only `solver.py` — never modify `check.py` — and run
> the check to confirm before you stop.

That prompt is the method in miniature. The check is the specification, the
implementation is the agent's to choose, and the pinned file is off limits.
It is also, deliberately, the same shape as the prompt the automated producer
builds from a sealed claim's recipe, which `RETICULI_DRY_PROMPT=1` prints for
any claim, so the discipline you practice here is the one `ret rebuild` will
later enforce.

When a check is worth keeping, run it through reticuli. That gives an
explicit execution boundary which captures the command and the files it
touched, even for scripts no hook sees:

```
$ ret run "python3 check.py && printf ok > OK"     # silent: exit 0
```

If you are following along without a live agent, nothing wrote `solver.py`
under observation: no editor hook fired, and the file existed before your
`ret run`, so the file scan saw no change. That is fine. Reticuli only seals
what it can account for, and it tells you exactly what is missing. You can
declare the implementation at pack time with `--generated solver.py`, as in
the next step, or author it through `ret run`, using `ret run "curl -s … >
solver.py"` or any command that writes it, so the scan captures it. `ret
status` flags a `hidden` file, meaning one a gate imports but nothing
observed, before you ever reach pack.

## 3. Pack — seal the session into a claim

```
$ ret pack . --accept OK -o ../primes.claim
  warnings
    producer cost not established (no harness transcript in the session window)
packed  c83d61870b9d…
```

With no live agent, `solver.py` was never observed, so add `--generated
solver.py`: `ret pack . --accept OK --generated solver.py -o
../primes.claim`. If you forget, pack does not seal a claim that cannot
rebuild. It names the missing file and the flag rather than failing
obscurely.

`pack` proposes a recipe from what was observed. Your written `solver.py`
becomes a generated output, the read `check.py` a pinned input, and the
command that writes `OK` the gate. It then re-earns the gate cold in a clean
workspace and seals only if it passes. The trace has no authority, so a wrong
proposal simply fails to certify.

It is also honest about what it could not establish rather than hiding it.
The warning above is real: a simulated session has no agent transcript, so
the production cost is unmeasured, and unmeasured is never written as zero. A
real `claude` session supplies the transcript and the cost rides into the
claim.

## 4. The name, and re-earning it

```
$ cd ../primes.claim
$ ret verify .        # milliseconds — are these the sealed bytes? silent exit 0
$ ret audit .         # minutes — re-run the tests in a sandbox; silent exit 0 = earned
```

`verify` checks identity and `audit` checks that the claim still holds. A
stored "tests passed" is never trusted.

## 5. What the name means

Rewrite the implementation however you like:

```
$ vim solver.py          # trial division → a sqrt-bounded loop
$ ret verify .           # exit 0 — same root, different code
```

Change one byte of a test, and the name moves:

```
$ echo 'assert is_prime(97)' >> check.py
$ ret verify .
ret: verify: broken — 1 pinned file(s) changed
  check.py
```

The identifier names the criteria rather than the code: the set of every
implementation that passes this exact check. Restore `check.py` before going
on.

## 6. Measure how much the tests prove

```
$ ret assess . --mutants 10 -v
mutation     0.90   9 of 10 injected faults detected; sampled 10 of 48 sites (21%)
-            0.00   return: 0 of 1 detected, 3 sites
-            survivor  solver.py:5: return <value> → None
```

`assess` injects faults and sees whether the tests catch them. The survivor
is the actionable part. Here the tests never check that the function returns
something, so a mutant that returns `None` slips through, and that is where
the boundary is thin. Mutation sampling varies run to run. `--corpus <file>`
records the run and places it against a population once you have assessed a
few claims.

## 7. Rebuild it, from the tests alone

If the tests truly determine the software, someone else can regrow it. The
strong producer is a language model, reached with `--producer openai`, which
spends money. But a producer is just any program that writes the withheld
implementation into its working directory, so the point can be made offline
with a script. `rebuild` runs it with its working directory set to a blind
workspace, where the criteria are present and `solver.py` is not, and the
script's only job is to write `solver.py` into that directory. Because it
runs there, name it by an absolute path, `$PWD/producer.py`, rather than a
bare `producer.py`:

```
$ cat > producer.py <<'PY'
# A stand-in for a model. rebuild runs this in the blind workspace; it writes
# the withheld implementation — a different one (sqrt-bounded) than we started
# with, to prove the root names the criteria, not the code.
src = '''import math
def is_prime(n):
    return n > 1 and all(n % d for d in range(2, math.isqrt(n) + 1))
'''
open("solver.py", "w").write(src)
PY
$ ret rebuild . --producer "python3 $PWD/producer.py" -o ../m3
rebuilt  c83d61870b9d…
$ diff solver.py ../m3/solver.py         # a different implementation…
$ ret crosscheck . ../m3 --record-proof   # silent exit 0: one root, and recorded
```

One root surviving an independent rebuild, from a different producer and in a
different shape, is what the tool is for. `--record-proof` files the result so
`ret status` advances past this rung; without it the crosscheck still decides
and prints, it just leaves nothing behind. `ret help rebuild` states the
producer contract in full.

## 8. Freeze the evidence, and stand behind it

```
$ ret record . -o primes.record.json      # this machine's results, the one parseable file
$ ret sign . --key ~/.ssh/id_ed25519 --as you@example.org    # human authorization
$ ret sign . --check --signers allowed_signers               # anyone can verify it
```

A record is a machine's observation, that these gates produced these results.
A signature is a person's authorization, that they reviewed this and stand
behind it. One never substitutes for the other. Signing is the keyholder's
act, always with their own key.

```
$ ret status .
claim      primes
root       c83d61870b9d…
identity   fresh
audited    …on this machine
deciding   mutation 0.90 (10 mutants)
proof      recorded
signed     1 statement(s)
next  share it: push with the CI workflow (M2), or ret export
```

Every `ret status` ends with `next`, the first rung this claim has not yet
earned. Each command you run advances it: audit, then assess, then the
recorded proof, then a signature, until the only rung left is sharing it.

## Where to go next

- [`capturing.md`](capturing.md) — the capture lifecycle in depth (agents, `ret run`, honest packing)
- [`spec/identity.md`](https://github.com/rz4/reticuli/blob/main/spec/identity.md) — exactly what the root hashes
- [`spec/verification.md`](https://github.com/rz4/reticuli/blob/main/spec/verification.md) — what each verdict means, and the three-machine test
- [`../examples/tomli/`](https://github.com/rz4/reticuli/blob/main/examples/tomli/README.md) — a claim over a real TOML parser that mechanically caught a shipped release drifting from TOML 1.0.0
- [`../CONTRIBUTING.md`](https://github.com/rz4/reticuli/blob/main/CONTRIBUTING.md) — the one non-obvious rule if you edit this repository
