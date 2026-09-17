# Writing a producer

A **producer** is any program that regenerates a claim's generated outputs.
`ret rebuild` runs it, then re-runs the gates and seals. That is the whole
interface.

**A producer need not involve a model.** For an ordinary build it is a
compiler — [`examples/make`](../examples/make/README.md) uses `make`, and two
compiler settings produce different binaries that carry the same root. For
code meant to be *re-derived* rather than compiled, it is a language model
driving a tool-use loop. The kernel does not know or care which.

```
ret rebuild <claim> --producer "<command>" --into <dir>
```

## The contract

The command runs with **working directory set to the target**, which already
contains the claim's pinned inputs and recipe. It should write the generated
outputs and exit 0.

Nothing else is guaranteed. In particular the environment is **scrubbed**:
only `PATH`, `HOME`, `TMPDIR`, `LANG`, `LC_ALL`, `TZ` and `RETICULI_JAILED`
survive from the host, plus the variables below. A producer needing an API key
must be given it explicitly — the kernel will not pass your whole environment
into a program that writes code.

| variable | meaning |
|---|---|
| `RETICULI_CLAIM` | absolute path to the workspace being built |
| `RETICULI_OUTPUT` | absolute path of **one** output to write — the first not yet present |
| `RETICULI_OUTPUTS` | JSON array of every generated output the recipe declares |
| `RETICULI_REQUEST` | the `request` string from that output's produce step, if any |
| `RETICULI_USAGE` | absolute path where the producer may report what it cost |

**`RETICULI_OUTPUT` names one file, but the producer is invoked once.** It is
a convenience for the single-output case, not a loop: a producer for a claim
with several generated files should read `RETICULI_OUTPUTS` and write them
all. (The kernel calls the command once per rebuild.)

**Create parent directories.** `RETICULI_OUTPUT` may name a path inside a
directory that does not exist yet in a fresh workspace. A producer that
assumes otherwise fails with `FileNotFoundError` — which is, empirically, the
single most common way a new producer breaks.

## Reporting cost, honestly

Write a JSON object to `RETICULI_USAGE`:

```json
{"calls": 1, "tokens": 604930, "usd": 3.40}
```

Only `calls`, `tokens` and `usd` are accepted, and only as numbers. Anything
else in the file is ignored; junk, a JSON list, or unparseable bytes pollute
nothing — the file is untrusted input.

**Wall-clock is not accepted here.** `seconds` is measured by the kernel
around your process and cannot be self-reported: it is the one cost unit a
producer cannot inflate or understate. This matters because the cost envelope
in a three-machine crosscheck compares the strongest unit both machines
recorded, and wall-clock is its last resort.

Declare who you are with `RETICULI_VENDOR` and `RETICULI_MODEL` in the
environment you launch `ret rebuild` from; both are recorded on the ledger as
a declaration, and `ret assess` uses them to report how far apart two
producers were. They are never verified — independence cannot be established
from content.

## Failure

Exit non-zero and the rebuild refuses, reporting the tail of your stderr. Note
what this means for interpretation: a failed rebuild has **four** plausible
causes, and "the tests were too weak to rebuild from" is only one of them.

1. The producer program is broken. Check this first — likeliest, cheapest.
2. The tests genuinely under-specify the behavior.
3. The rebuild environment differs from the gate's.
4. The model was not capable enough.

`ret assess` prints all four rather than inviting the flattering reading. We
hit cause 3 twice in one afternoon while building this repository.

## A minimal example

```python
import os

path = os.environ["RETICULI_OUTPUT"]
os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
with open(path, "w") as f:
    f.write("def add(a, b):\n    return a + b\n")

usage = os.environ.get("RETICULI_USAGE")
if usage:
    with open(usage, "w") as f:
        f.write('{"calls": 1}')
```

## The shipped producers

`reticuli.producers.openai` drives a bounded tool-use loop against an OpenAI
endpoint: the model may read the claim's files, write outputs, and run the
gate until it passes or a turn cap is hit.

```
ret rebuild myclaim --producer "python3 -m reticuli.producers.openai" --into /tmp/m3
```

Environment: `RETICULI_MODEL` (default `gpt-5`), `RETICULI_AGENT_TURNS`,
`OPENAI_API_KEY`, `OPENAI_BASE_URL`, and `RETICULI_PRICE` as `"in,out"` USD
per million tokens if you want the ledger to carry a dollar figure.

`reticuli.producers.anthropic` is its sibling: the same room contract, the
same three tools, driving Claude through the Anthropic SDK.

```
ret rebuild myclaim --producer "python3 -m reticuli.producers.anthropic" --into /tmp/m3
```

Environment: `RETICULI_MODEL` (default `claude-opus-5`),
`RETICULI_AGENT_TURNS`, `ANTHROPIC_API_KEY`, and `RETICULI_PRICE`
(`"5,25"` for claude-opus-5; `"3,15"` for claude-sonnet-5). Two producers
from two vendors means a cross-vendor three-machine test needs nothing but
two keys.

`RETICULI_GATE_MATRIX=1` makes either producer run the gate under **every**
host condition rather than just the one it happens to be in. That exists
because a producer only ever sees the environment it runs in, while the
acceptance tests may pin behavior in several — we watched a model satisfy
the environment it was iterating in and break the other one, twice in
opposite directions, before adding it. With the matrix on, the same task
landed on the first attempt.

## Handing a producer its key

The kernel scrubs the environment, so `ANTHROPIC_API_KEY` or
`OPENAI_API_KEY` will not reach a producer on its own — hand it in through
the producer command. The pattern that survived three failed launches in
this repository's own provenance: a wrapper script sourcing a mode-600 env
file, run with Python's safe-path flag so nothing in the room shadows an
installed package.

```sh
#!/bin/sh
# run_producer.sh -- the producer command is: sh /path/to/run_producer.sh
. /path/to/producer.env          # exports the key, RETICULI_MODEL, RETICULI_PRICE
PYTHONPATH=/path/to/reticuli/src \
exec python3 -P -m reticuli.producers.anthropic
```

The command string lands on the ledger; the key, living in the env file,
never does.
