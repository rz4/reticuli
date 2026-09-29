# The succession run — the implementation dematerializes

*2026-09-29. Research record — nothing here is normative, and no root
moved. Harness: `research/harness/succession/`.*

## The question

The repository's root excludes `src/` by design. This run takes the
promise to its end: grow a complete replacement implementation in rooms
that never see the original — each of twenty layers regrown blind from
its criteria with the layers beneath supplied **from the regrown tree,
never from the original** — then ask three questions of the finished
tree. Is it the same claim (identity)? Is it the same tool (drift)? Can
it carry the line (succession)?

## Construction

Flat scaffold claims per layer (the nineteen of `scripts/selfclaim.py`
plus `reference.py`, which the decomposition omits — judged by
`vectors_check`), sealed entirely from the original so the warm seal
always earns; at rebuild time the generation-1 lower modules are threaded
into the room via the kernel's `input_from` — ledgered, inside the tamper
snapshot — so no room ever holds an original implementation byte. Rooms
carry `spec/` exactly as the repository claim pins it (witnessed: a
producer stalled on the identity layer asking for `spec/identity.md`;
under-furnishing the room relative to the standing invitation is a
harness bug, not blindness). Every layer gate ran in the kernel's
sandbox; every accepted layer sealed.

The codex lineage (gpt-6-sol) completed all twenty layers: 37 modules,
4,118 lines against the original's 10,856. The claude lineage (sonnet)
was mid-climb when this record was first written; its ledger carries two
witnessed producer-environment limits (a session that asked for the spec
before rooms carried it; the claude CLI's 64k output-token ceiling on
the crosscheck layer, raised via its own knob).

## The verdicts (codex lineage)

**Drift — none the confidence surface can see.** `tests/` is outside the
root (confidence, not identity), which makes it a held-out probe battery
for exactly what the criteria never pin. Result: **102 of 102
environment-valid tests pass** against the regrown tree (the single
failure, `test_streams`, fails identically against the original in this
environment). At 38% of the size, the regrown tool is behaviorally the
tool.

**Identity — root yes, gate no, and the no is the discovery.** The
repository root recomputes unchanged under substitution of all 37
modules. But `REPO_OK` refuses: pinned `scripts/selfclaim.py` calls the
authoring layer's `pack` with keyword names and three features
(`component`, `envelope`, `claim_format`) that `authoring_check` never
exercises — the regrown, conforming pack has none of them. **The gate is
not closed over the equivalence class it names**: a member that passes
every layer suite cannot run the repository's own machinery. Four more
specimens of the same species were found and measured (sub-layer seams
riding on private names — `identity→recipe._inputs`, `recipe→core.KINDS`
— which is why original modules cannot stand on regrown lowers while
regrown ones can; `rebuild`'s keyword surface on which spec, checks, and
original disagree three ways; the declared `gate_timeout` that a
conforming kernel may cap from below — 60-second default with a `min`
combiner — leaving it structurally unable to audit the repository that
declares it; and the decomposition's missing `reference.py`). The staged
repair — five pins and a general closure check — is
`research/proposals/close-the-gate-over-its-class.md`; every click is a
root move and is held for the keyholder.

**Succession — holds.** Run as the tool (`PYTHONPATH` at the regrown
tree, the original package nowhere on the path):

- `--version`, then `verify .` — the regrown tool computes the
  repository's root and agrees it stands;
- a copied claim with one pinned byte flipped — **refused, exit 1**, with
  its own diagnostic; the regrown judge does not wave tampering through;
- `audit .` — the regrown auditor **re-earned `REPO_OK` on the original
  repository, cold, in its own sandbox** (with its own
  `RETICULI_GATE_TIMEOUT` raised — see the timeout specimen above);
- generation 2: the regrown kernel drove a blind rebuild of the core
  layer through the standard producer machinery and sealed it. Original
  core is 225 lines; generation 1 is 157; generation 2 is 110; three
  distinct realizations of one claim, each grown by the last.

## The reading

Behaviorally, the equivalence class did its job: a blind, transitive,
cross-vendor regrowth of the whole tool lands inside it, indistinguishable
to the entire held-out confidence suite, and verification authority
survives the trip — the regrown judge verifies, refuses, audits, and
reproduces. What failed is sharper and more useful: the repository's own
gate turns out to be a *consumer* of the implementation, and like every
consumer it depends on obligations the boundary never pinned. Stage 2
found this for a parser and its port-doubler; the ladder found it for
maintenance pressure; the succession finds it for the tool judging
itself. The convergence the criteria still owe is exactly the staged pin
set: after those clicks, a conforming implementation is not merely
gate-passing but substitutable for the shipped tool under the
repository's own machinery — consumer-relative sufficiency with the gate
as its own first consumer.

## Where everything is

- `research/harness/succession/` — runner, judges, both lineage trees
  and ledgers, `full_gate_codex.json`, `tests_codex.txt`,
  `bootstrap_codex.json`.
- `research/proposals/close-the-gate-over-its-class.md` — the staged
  ratchet clicks.
- Producers: codex/gpt-6-sol and Claude Code/sonnet, both un-metered;
  scaffolding and judging by the shipped kernel throughout.
