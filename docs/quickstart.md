# Quickstart

*Informational — a hands-on guide. The normative contract is in [`spec/`](../spec/).*

The whole life of a claim in about fifteen minutes, from an empty directory to a
signed, independently-rebuilt result. No API key needed to follow along; the one
step that spends money is called out where it appears.

## Install

The repository is currently private and reticuli is not yet on a public index,
so install from a clone into a virtualenv:

```
git clone https://github.com/rz4/reticuli.git && cd reticuli
python3 -m venv .venv && source .venv/bin/activate
pip install .
ret --version
```

Pure standard library, macOS or Linux. Prefer not to install? Because the tool
is pure stdlib you can run it from a checkout — every `ret …` below becomes
`python3 -m reticuli …` with `PYTHONPATH=src` set.

A note on output: **a check that passes exits 0 and stays quiet**, the Unix way.
Piped, redirected, or in CI, a passing command prints nothing — the exit code is
the whole answer. In an interactive terminal you also get a one-line
confirmation on stderr (so you can tell "passed" from "nothing happened"); it
never touches stdout or the exit code. The fuller blocks shown here appear under
`-v`.

## 1. Start a project

An ordinary directory, made a git repo, made a reticuli workspace:

```
$ mkdir primes && cd primes && git init -q
$ ret init --agent claude
# agent hooks wired: claude → ret hook
# ready: work, `ret run` your checks, `ret pack` when it holds
```

`ret init` marks a **workspace**, the way `git init` marks a repo — not a
session. Work here for minutes or months; the same trace keeps filling.
`--agent claude` wires the observation hooks *now*, before you launch the agent,
so the session is captured (Claude Code reads its settings at startup). For any
other harness, use `--agent generic` and point it at `ret hook`; see
[`capturing.md`](capturing.md).

## 2. Do the work

Write a test, and let the implementation be written for you. With the hooks
wired, just run `claude` and work — it writes `solver.py`, reads your
`check.py`, and the hooks record all of it. Here is a test to start from:

```python
# check.py
from solver import is_prime
assert [n for n in range(20) if is_prime(n)] == [2, 3, 5, 7, 11, 13, 17, 19]
```

When a check is worth keeping, run it through reticuli — an explicit execution
boundary that captures the command *and the files it touched*, even for scripts
no hook sees:

```
$ ret run "python3 check.py && printf ok > OK"     # silent: exit 0
```

**Following along without a live agent?** Then nothing wrote `solver.py` under
observation — no editor hook fired, and it existed before your `ret run`, so the
file scan saw no change. That is fine: reticuli only seals what it can account
for, and it tells you exactly what is missing. You can declare the
implementation at pack time (`--generated solver.py`, next step), or author it
*through* `ret run` (`ret run "curl -s … > solver.py"`, or any command that
writes it) so the scan captures it. `ret status` flags a `hidden` file — one a
gate imports but nothing observed — before you ever reach pack.

## 3. Pack — seal the session into a claim

```
$ ret pack . --accept OK -o ../primes.claim
  warnings
    producer cost not established (no harness transcript in the session window)
packed  c83d61870b9d…
```

(No live agent, so `solver.py` was never observed? Add `--generated solver.py`:
`ret pack . --accept OK --generated solver.py -o ../primes.claim`. If you forget,
pack does not seal a claim that cannot rebuild — it names the missing file and
the flag, rather than failing obscurely.)

`pack` proposes a recipe from what was observed — your written `solver.py`
becomes a generated output, the read `check.py` a pinned input, the command that
writes `OK` the gate — then **re-earns the gate cold in a clean workspace** and
seals only if it passes. The trace has no authority; a wrong proposal simply
fails to certify.

And it is **honest about what it could not establish** rather than hiding it.
The warning above is real: a simulated session has no agent transcript, so the
production cost is unmeasured — and unmeasured is never written as zero. A real
`claude` session supplies the transcript and the cost rides into the claim.

## 4. The name, and re-earning it

```
$ cd ../primes.claim
$ ret verify .        # milliseconds — are these the sealed bytes? silent exit 0
$ ret audit .         # minutes — re-run the tests in a sandbox; silent exit 0 = earned
```

`verify` checks identity; `audit` checks that the claim still *holds*. A stored
"tests passed" is never trusted.

## 5. What the name means

This is the whole idea. Rewrite the implementation however you like:

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

**The identifier names the criteria, not the code** — the set of every
implementation that passes this exact check. (Restore `check.py` before going on.)

## 6. Measure how much the tests prove

```
$ ret assess . --mutants 10 -v
mutation     0.90   9 of 10 injected faults detected; sampled 10 of 48 sites (21%)
-            0.00   return: 0 of 1 detected, 3 sites
-            survivor  solver.py:5: return <value> → None
```

`assess` injects faults and sees whether the tests catch them. A **survivor** is
the actionable part: here the tests never check that the function *returns*
something, so a mutant that returns `None` slips through. That is where the
boundary is thin. (Mutation sampling varies run to run.) `--corpus <file>`
records the run and places it against a population once you have assessed a few
claims.

## 7. The point: rebuild it, from the tests alone

If the tests truly determine the software, someone else can regrow it. The
strong producer is a language model — `--producer openai`, which spends money —
but a *producer* is just any program that writes the withheld implementation
into its working directory, so we can prove the point offline with a script.
`rebuild` runs it with its working directory set to a blind workspace (the
criteria are there; `solver.py` is not), and the script's only job is to write
`solver.py` into that directory. Because it runs *there*, name it by an absolute
path (`$PWD/producer.py`), not a bare `producer.py`:

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

That one root surviving an independent rebuild — from a different producer, in a
different shape — is the tool's whole thesis. `--record-proof` files the result
so `ret status` advances past this rung; without it the crosscheck still decides
and prints, it just leaves nothing behind. (`ret help rebuild` states the
producer contract in full.)

## 8. Freeze the evidence, and stand behind it

```
$ ret record . -o primes.record.json      # this machine's results, the one parseable file
$ ret sign . --key ~/.ssh/id_ed25519 --as you@example.org    # human authorization
$ ret sign . --check --signers allowed_signers               # anyone can verify it
```

A **record** is a machine's observation ("these gates produced these results");
a **signature** is a person's authorization ("I reviewed this and stand behind
it"). One never substitutes for the other. Signing is the keyholder's act,
always with their own key.

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

Every `ret status` ends with `next` — the first rung this claim has not yet
earned. Each command you run advances it: audit, then assess, then the recorded
proof, then a signature, until the only rung left is sharing it.

## Where to go next

- [`capturing.md`](capturing.md) — the capture lifecycle in depth (agents, `ret run`, honest packing)
- [`spec/identity.md`](../spec/identity.md) — exactly what the root hashes
- [`spec/verification.md`](../spec/verification.md) — what each verdict means, and the three-machine test
- [`../examples/tomli/`](../examples/tomli/README.md) — a claim over a real TOML parser that mechanically caught a shipped release drifting from TOML 1.0.0
- [`../CONTRIBUTING.md`](../CONTRIBUTING.md) — the one non-obvious rule if you edit this repository
