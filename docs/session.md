# A terminal session

Every block below is a real invocation, captured by `docs/transcribe.py` against the shipped `examples/make` claim and re-captured on every docs build. Normalizations, stated: the entry point is shown as `ret`, the claim directory as `~/demo`, the scratch directory as `~/work`; output longer than a screen is elided with a marker. The claim's producer is `make`, so every step runs offline.

The claim: a word-count program. Pinned: the acceptance gate (`check.sh`), its test cases, the `Makefile`, and the C source. Generated: the compiled binary.

This page is self-sufficient: after it you can verify, audit, rebuild, and record claims. Everything after it in the documentation is depth, not prerequisites.

## Verify: is this the claim it names?

`verify` recomputes the root from the pinned bytes and compares. Exit status is the machine-readable verdict.

```console
$ ret verify .                    # recompute the root; compare; exit status is the verdict
$ echo $?
0
```

## A claim travels without its implementation

`verify` passes above — identity is intact — but `audit` refuses: the gate has nothing to judge. Identity and membership are separate questions with separate instruments.

```console
$ ls                              # note: no compiled binary — the implementation is not part of the claim
Makefile
OK
README.md
cases
check.sh
reticuli.toml
wordcount.c
$ ret audit .                     # re-earn the gate in a sandboxed room: nothing to judge yet
ret: audit: failed — gate OK (failed)
hint: the gate's own words: ret audit -v
$ echo $?
1
```

## Rebuild: regrow the implementation from the claim

The producer here is `make`; for other claims, a coding agent — the contract is identical. The regrown claim lands at the same root: different bytes, same identity.

```console
# fresh room, declared inputs only; the producer writes the binary
$ ret rebuild . --producer make --into ~/work/M3
rebuilt  0996e1a5bead...
$ ret audit ~/work/M3             # the regrown claim re-earns its gate
$ echo $?
0
```

## What an agent producer is told

The rebuild above used `make`. When the producer is a model, this is the exact prompt the claim induces — built from the recipe, nothing hand-written. Note what it does not contain: no reference implementation, no hints beyond the pinned files, and an explicit prohibition on modifying them. `RETICULI_DRY_PROMPT=1` prints it for any claim without calling an API.

```console
# the prompt this claim induces; no API is called
$ RETICULI_OUTPUT=wordcount RETICULI_DRY_PROMPT=1 python3 -m reticuli.producers.openai
You are reconstructing the source files of a content-addressed claim so its check passes. There is NO reference implementation — infer the required API and semantics from the check files ALONE.

Your files to create (standard library only, correct over clever): ['wordcount']
The check/input files (already present — read them first, IN FULL): ['Makefile', 'check.sh', 'cases/expected.txt', 'cases/input.txt', 'wordcount.c']
Files supplied by lower layers (read, import from, do NOT modify): []
The gate command is:  sh check.sh
It must succeed and create:  OK

A check file may be much longer than one read chunk (20000 chars). read_file takes an optional integer `offset`; keep reading at increasing offsets until you reach end-of-file. Read the ENTIRE check before designing — its header docstrings specify exact byte-level serializations you must reproduce.

Use the tools: read_file to inspect, write_file to create your files, run_gate to test. Iterate until run_gate reports success, then stop. Never modify the check/input files.
```

## Tamper with a pinned byte

The root no longer matches: this is a different claim, and `verify` says so, naming both roots. Identity is the bytes, not the file's history.

```console
$ printf '#\n' >> check.sh        # append one byte to the PINNED acceptance gate
$ ret verify .                    # a different root: a different claim
ret: verify: broken — expected 0996e1a5bead..., got 7f5029c113ce...
$ echo $?
1
$ sed -i '' -e '$d' check.sh      # remove the byte
$ ret verify .                    # identity returns
$ echo $?
0
```

## Damage the generated output

`verify` still passes — the root covers pinned material only — but the gate judges the bytes present, and `audit` refuses.

```console
$ : > ~/work/M3/wordcount         # truncate the GENERATED binary
$ ret verify ~/work/M3            # identity intact: the root covers pinned bytes only
$ echo $?
0
$ ret audit ~/work/M3             # membership lost: the gate judges the bytes present
ret: audit: failed — gate OK (failed)
hint: the gate's own words: ret audit -v
$ echo $?
1
# discard the damaged member entirely
$ rm -f ~/work/M3/wordcount ~/work/M3/OK
# regrow a fresh member; same root again
$ ret rebuild ~/work/M3 --producer make --into ~/work/M3b
rebuilt  0996e1a5bead...
```

## Record: evidence that travels

A record freezes one machine's results in the canonical interchange format: identity, per-gate verdicts with the sandbox backend used, environment, measured cost.

```console
# freeze this machine's results, canonically
$ ret record ~/work/M3b --out ~/work/record.json
# identity, gates with the sandbox used, environment, cost
$ head -c 400 ~/work/record.json; echo
{"build_digest": "c0d14d72463f26ff016a66ca67f35aec131229e4b9dab0a35ff148dd0edc3f40", "claim": {}, "cost": {"calls": 1, "seconds": 0.22999999999999998}, "environment": {"machine": "arm64", "platform": "darwin", "runtime": "CPython 3.14.3"}, "gates": [{"output": "OK", "sandbox": "seatbelt", "status": "ok"}], "name": "wordcount", "producer": {"blind": true}, "record": 2, "root": "0996e1a5beadf17e5664
```

## Where to go next

[The process](process.md) for the lifecycle these commands walk; [mechanisms](mechanisms.md) for rooms, the scrub, and the sandbox tiers; [the CLI reference](cli.md) for every verb.
