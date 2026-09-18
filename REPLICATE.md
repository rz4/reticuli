# The replication protocol

*Informational — the operational protocol `LICENSE` refers to. It grants no
rights; the terms are in [`LICENSE`](LICENSE).*

Reticuli exists so that a claim can be re-earned by someone who did not make
it. This file is the protocol for doing that: taking a claim in this repository
and establishing, on your own machine, that it holds — and, if you want the
strong result, that its criteria alone determine the software.

You need only Python 3.11+ and a POSIX host (macOS or Linux). No API key and no
model are required for the first three steps.

## 1. Get the tool

```
git clone https://github.com/rz4/reticuli.git && cd reticuli
pip install .            # or run in place: PYTHONPATH=src python3 -m reticuli …
```

Pure standard library; see [`docs/quickstart.md`](docs/quickstart.md).

## 2. Verify identity (milliseconds, no execution)

```
ret verify examples/quirkcalc
```

This recomputes the claim's root from its bytes and checks it against the
sealed manifest. It answers only "are these the sealed bytes?" — it runs
nothing. Silent exit 0 means the identity holds.

## 3. Re-earn the verdict (cold, sandboxed)

```
ret audit examples/quirkcalc
```

`audit` re-runs the claim's gates in a sandbox and requires the recorded
verdict to reproduce on *your* machine. A stored "it passed" is never trusted.
Silent exit 0 means the claim still holds here. What a passing audit does and
does not establish is stated exactly in
[`docs/threat-model.md`](docs/threat-model.md).

## 4. The strong result: rebuild and crosscheck

The point of a reticuli claim is that its criteria — not any particular
implementation — name the software. To test that, regrow the implementation
from the claim alone and confirm it lands on the same root:

```
ret rebuild examples/make --producer "make" --into /tmp/rebuilt
ret crosscheck examples/make /tmp/rebuilt
```

For a claim meant to be re-derived rather than compiled, the producer can be a
language model; the producer is yours to bring. The three-machine test (M1 the
original, M2 a byte copy, M3 an independent rebuild) is defined in
[`spec/verification.md`](spec/verification.md), and the standing public
invitation — regrow the whole tool from its frozen boundary — is
[`research/open-call.md`](research/open-call.md).

## What replication establishes

A successful replication establishes that the claim's criteria re-earn their
verdict on a machine its author never touched, and — with step 4 — that an
independent producer can satisfy those criteria. It does **not** establish that
the code is correct, that the check is strong, or that a producer worked
without ever seeing the original. Those limits are stated plainly in
[`docs/threat-model.md`](docs/threat-model.md) and measured by `ret assess`.
