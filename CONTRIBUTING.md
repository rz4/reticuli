# Contributing

## Layout, and the one rule that is not obvious

```
src/reticuli/     the package
tests/            ordinary tests — edit freely
conformance/      acceptance suites and sealed claims — see below
spec/             the format and its semantics
examples/         worked claims
scripts/          developer scripts
```

**Files under `conformance/` are identity-bearing.** Their bytes are hashed
into claim identities, so editing one does not fix a test — it renames a
claim, and every proof, signature and lineage link naming the old root is
orphaned. Never run a formatter over `conformance/kernel/` or
`conformance/kernel-2.0/` (ruff is configured to skip them), and expect
`tests/self_check.py` to fail loudly if a suite's bytes change, because it
pins the resulting roots as a lockfile.

If a change to a suite is intended, re-pin with `python3 scripts/selfclaim.py`
and say in the commit message what behavior changed and why — the roots moving
is the point, not a nuisance.

## Running everything CI runs

```
for f in conformance/*_check.py tests/*.py; do python3 "$f"; done
for c in conformance/kernel conformance/kernel-2.0 examples/*; do
  python3 conformance/reference_seal.py verify "$c"
done
ruff check .
```

`conformance/reference_seal.py` is deliberately a *second* implementation of
`spec/identity.md`, independent of `src/reticuli/kernel.py`. The two must
agree on every root; that disagreement would be a real finding.

## Sandboxes

Gates run sandboxed where the platform supports it (seatbelt on macOS, bwrap
on Linux). If your shell is already sandboxed, prefix commands with
`RETICULI_JAILED=1` so the kernel inherits rather than trying to nest — never
disable sandboxing to make something pass. Note that a real sandbox is applied
on far fewer hosts than you would expect, so bugs in that path tend to appear
only in CI.
