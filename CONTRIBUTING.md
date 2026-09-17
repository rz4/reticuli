# Contributing

## Layout, and the one rule that is not obvious

```
src/reticuli/     the package
tests/            ordinary tests — edit freely
criteria/      acceptance suites and sealed claims — see below
spec/             the format and its semantics
examples/         worked claims
scripts/          developer scripts
```

**Files under `criteria/` are identity-bearing.** Their bytes are hashed
into claim identities, so editing one does not fix a test — it renames a
claim, and every proof, signature and lineage link naming the old root is
orphaned. Never run a formatter over `examples/kernel/` or
`examples/kernel-2.0/` (ruff is configured to skip them), and expect
`criteria/self_check.py` to fail loudly if a suite's bytes change, because it
pins the resulting roots as a lockfile.

If a change to a suite is intended, re-pin with `python3 scripts/selfclaim.py`
and say in the commit message what behavior changed and why — the roots moving
is the point, not a nuisance.

## Running everything CI runs

```
python3 gate.py                                   # the criteria
pytest tests/                                     # the tests
for c in examples/kernel examples/kernel-2.0 examples/quirkcalc \
         examples/tomli examples/make examples/weak; do
  PYTHONPATH=src python3 -m reticuli.reference verify "$c"
done
ruff check .
```

The gate, not a loop over `criteria/*.py`: `kernel_check.py` is a claim's
gate and only runs staged, which `gate.py` handles and a bare loop does not.
The claims are named rather than globbed because `examples/self` holds prose,
not a claim.

`reticuli.reference` is deliberately a *second* implementation of
`spec/identity.md`, independent of `src/reticuli/kernel.py`. The two must
agree on every root; that disagreement would be a real finding.

## Sandboxes

Gates run sandboxed where the platform supports it (seatbelt on macOS, bwrap
on Linux). If your shell is already sandboxed, prefix commands with
`RETICULI_JAILED=1` so the kernel inherits rather than trying to nest — never
disable sandboxing to make something pass. Note that a real sandbox is applied
on far fewer hosts than you would expect, so bugs in that path tend to appear
only in CI.

## The repository is itself a claim

`reticuli.toml` at the root pins `spec/` and `criteria/` as criteria and
declares `src/reticuli/` generated. So:

```
PYTHONPATH=src python3 -m reticuli verify .    # hashes only, milliseconds
PYTHONPATH=src python3 -m reticuli audit .     # re-run every criterion, cold
```

**If you edit anything pinned, the root moves and you must re-earn it**, or CI
fails on the `verify` step:

```
PYTHONPATH=src python3 gate.py    # the gate must pass first
python3 -c "import sys; sys.path.insert(0,'src'); from reticuli import kernel; kernel.seal('.')"
```

Commit the updated `.reticuli/manifest.json` with your change. Editing
`tests/`, `docs/`, or this file does not move the root — none of them decides
what the repository claims.

Comments and formatting inside a `reticuli.toml` are free: the hash covers the
recipe's parsed content, not its bytes.
