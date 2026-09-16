# Kernel API (v2 names)

**Status: decided 2026-09-15, pinned by the seed claim's acceptance check
(`examples/kernel/checks/kernel_check.py`). The regrown kernel implements exactly this
surface; the check is the enforceable form of this table.**

The v2 kernel is `reticuli/kernel.py` (package `reticuli`). Renames from v1,
one row per public symbol the acceptance check exercises:

| v2 | v1 | contract |
|---|---|---|
| `root(recipe, d)` | `claim` | the identity hash — see `spec/identity.md` |
| `seal(d, …)` | `seal` | compute root, write `.reticuli/manifest.json` |
| `verify(d)` | `verify` | identity + gates re-run on present bytes |
| `rebuild(d, producer, into, …)` | `realize` | regrow generated outputs until gates pass; ledger appended |
| `crosscheck(…)` | `three_machine` | the three-machine test — see `spec/verification.md` |
| `audit(d, …)` | `audit` | deep re-earning; earned vs. carried |
| `phase(d)` | `phase` | `"draft" / "sealed" / "signed"` (v1: vapor/liquid/solid) |
| `load_recipe(d)` | `load_recipe` | parse + validate `reticuli.toml`; refusals, not crashes |
| `read_manifest(d)` | `read_manifest` | `{name, root}`; malformed bytes refused |
| `cost(d)` | `cost` | ledger totals per unit (usd/tokens/calls/seconds); `None` if nothing was measured. Totals carry only the keys the ledger names — an unmeasured machine is reported, never guessed at. A producer may *report* usd/tokens/calls; `seconds` is the kernel's own measurement and is never accepted from a usage payload. **The check does not pin the unit set**, so a conforming kernel may omit wall-clock — see the layered-claims note in `spec/verification.md` |
| `sign_node(root, digest, links)` | `mint_node` | signature-chain node computation |
| `build_digest(d)` | `realization_digest` | digest over concrete bytes incl. generated |
| `mutation_score(d, …)` | `teeth` | deterministic mutants from the root; kill rate |
| `vacuous_gates(recipe)` | `vacuous_gates` | gates whose every decider is generated |
| `gate_deciders(recipe)` | `gate_deciders` | which files decide each gate |
| `record_proof(m1, m2, m3)` | `freeze_dry` | run the crosscheck; on a pass, seal the proof onto M1 as residue (never phase) |
| `run_gate(…)` | `run_gate` | one gate: scrubbed env, sandboxed, bounded |
| `sandbox()` | `jail` | functional probe of the host sandbox |
| `preflight(recipe)` | `preflight` | environment contract: missing `requires` |
| `independence(…)` | `independence` | declared producer independence of a crosscheck |
| `ClaimError` | `ReticuliError` | a refusal with a reason — the only kernel error |
| `_hash_file(path)` | `_hf` | file hashing rules of `spec/identity.md` |

Constants the check pins: `RECIPE = "reticuli.toml"` (v1: `reticuli.toml`),
`STORE = ".reticuli"`, `LEDGER`, `NAMESPACE = "reticuli"`, `SIGN_DIR` (v1:
`MINT`), `SIGN_NAMESPACE = "reticuli.mint"` (v1: `MINT_NAMESPACE`), `_JAILED`.
The namespace *values* are carried from v1 for signature interop while the
namespace question in `spec/claim-format.md` stays open; the constant names
speak v2. Environment variables are unchanged from v1 (`RETICULI_*`);
`RETICULI_JAILED` remains the internal already-inside-a-sandbox signal.

`rebuild` keyword arguments: `produce_from` (unchanged) and `input_from`
(v1: `seed_from`).

On-disk format (v2 speaks v2): signature statements end in `.sign.json`
(v1: `.mint.json`) and their packet key for the concrete-bytes digest is
`build_digest` (v1: `realization_digest`); mutation residue is
`mutation_score.json` (v1: `teeth.json`).

Recipe/result vocabulary carried through the API: step class
`generated`/`pinned`/`validated` (v1: `free`/`exact`/`validated`),
`[claim] mutation_floor` (v1: `teeth`), crosscheck result field
`mutation_score` (v1: `teeth`). Failure classes, cost units, and the ledger
key `quarantine` are unchanged (`spec/verification.md`; `quarantine` is a
candidate for a later key decision, deliberately not renamed by the seed).
