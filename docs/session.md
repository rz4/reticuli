# A terminal session

Every block below is a real invocation, captured by `docs/transcribe.py` against the shipped `examples/make` claim and re-captured on every docs build. Normalizations, stated: the entry point is shown as `ret`, the claim directory as `~/demo`, the scratch directory as `~/work`; output longer than a screen is elided with a marker. The claim's producer is `make`, so every step runs offline.

The claim: a word-count program. Pinned: the acceptance gate (`check.sh`), its test cases, the `Makefile`, and the C source. Generated: the compiled binary.

## Verify: is this the claim it names?

`verify` recomputes the root from the pinned bytes and compares. Exit status is the machine-readable verdict.

```console
$ ret verify .
$ echo $?
0
```

## A claim travels without its implementation

The directory holds no compiled binary: the implementation is generated material, outside the identity, and this claim ships without it. `verify` passes above — identity is intact — but `audit` refuses: the gate has nothing to judge. Identity and membership are separate questions with separate instruments.

```console
$ ls
Makefile
OK
README.md
cases
check.sh
reticuli.toml
wordcount.c
$ ret audit .
ret: audit: failed — gate OK (failed)
hint: the gate's own words: ret audit -v
$ echo $?
1
```

## Rebuild: regrow the implementation from the claim

`rebuild` materializes a fresh room from the declared inputs and invokes the producer — here `make`; for other claims, a coding agent; the contract is identical. The regrown claim must re-earn its gate, and lands at the same root: a different set of bytes, the same identity.

```console
$ ret rebuild . --producer make --into ~/work/M3
rebuilt  0996e1a5bead...
$ ret audit ~/work/M3
$ echo $?
0
```

## Tamper with a pinned byte

One byte appended to the pinned acceptance gate. The root no longer matches: this is a different claim, and `verify` says so, naming both roots. Remove the byte and identity returns — identity is the bytes, not the file's history.

```console
$ printf '#\n' >> check.sh
$ ret verify .
ret: verify: broken — expected 0996e1a5bead..., got 7f5029c113ce...
$ echo $?
1
$ sed -i '' -e '$d' check.sh
$ ret verify .
$ echo $?
0
```

## Damage the generated output

Truncate the regrown binary. `verify` still passes — the root covers pinned material only — but the gate judges the bytes present, and `audit` refuses.

```console
$ : > ~/work/M3/wordcount
$ ret verify ~/work/M3
$ echo $?
0
$ ret audit ~/work/M3
ret: audit: failed — gate OK (failed)
hint: the gate's own words: ret audit -v
$ echo $?
1
$ rm -f ~/work/M3/wordcount ~/work/M3/OK
$ ret rebuild ~/work/M3 --producer make --into ~/work/M3b
rebuilt  0996e1a5bead...
```

## Record: evidence that travels

A record freezes one machine's results in the canonical interchange format: identity, per-gate verdicts with the sandbox backend used, environment, measured cost.

```console
$ ret record ~/work/M3b --out ~/work/record.json
$ head -c 400 ~/work/record.json; echo
{"build_digest": "c0d14d72463f26ff016a66ca67f35aec131229e4b9dab0a35ff148dd0edc3f40", "claim": {}, "cost": {"calls": 1, "seconds": 0.22999999999999998}, "environment": {"machine": "arm64", "platform": "darwin", "runtime": "CPython 3.14.3"}, "gates": [{"output": "OK", "sandbox": "seatbelt", "status": "ok"}], "name": "wordcount", "producer": {"blind": true}, "record": 2, "root": "0996e1a5beadf17e5664
```

## Where to go next

[The process](process.md) for the lifecycle these commands walk; [mechanisms](mechanisms.md) for rooms, the scrub, and the sandbox tiers; [the CLI reference](cli.md) for every verb.
