# The generation ladder — iterated rewriting under a fixed gate

*2026-09-29. Research record — nothing here is normative, and no root moved.*

## The question

Stage 2 showed what blind regrowth does to the surface a check is silent
about: every producer fills the silence with the same prior. This
experiment asks the maintenance-time version of that question. When an
agent rewrites a **working, visible** module generation after generation,
and the only enforced floor is the claim's gate, what happens to the
behavior the gate does not pin?

## The setup

Subject: `research/harness/ladder/claims/L` — a sealed config-parser claim
(`confparse`, root `5d781b08…`). Its check `C_0` pins the happy path only.
Generation 0 makes eight deliberate, **undocumented** choices on the
unpinned surface (int coercion, first-wins duplicates, `:` as a second
separator, key lowercasing, silent skip of malformed lines, literal
inline `#`, backslash continuation, `[section]` prefixing). A probe
battery (`probes.py`) fingerprints any implementation's behavior on all
eight; a bit survives when the probes still match generation 0.

Three conditions, two producer families (codex / gpt-6 models, Claude
Code / claude models), all through the kernel's own machinery:

- **blind** — the shipped producers regrow `parser.py` from the check
  alone (`guidance=False`), six models. This samples the prior.
- **faithful** — a chain: each generation the producer receives the
  previous implementation over the claim's format-3 guidance channel
  (which the root excludes — verified root-neutral on the sealed claim)
  and is asked to "rewrite it in your own style". Nothing is said about
  preserving behavior. One chain per family, 16 generations each.
- **minimize** — the same chain, but the ask is "as short and simple as
  you can while the project's check still passes". Ordinary engineering
  pressure, with the gate named as the floor.

Identity discipline: every accepted generation passed the gate in the
sandbox and re-earned the subject's root — the kernel refuses a producer
that touches pinned bytes — and the run ledger records `guidance: true`
for the chains, `blind` for the controls. 70 producer sessions (64 chain
generations, 6 blind controls), zero retries, and the root never moved
once.

## What happened

| condition | family | outcome (of 8 intent bits) |
|---|---|---|
| blind | codex ×3 | 1/8 alive — all three models |
| blind | claude ×3 | 1/8 (sonnet, opus), 2/8 (haiku) |
| faithful ×16 gens | codex | **8/8 alive at every generation** |
| faithful ×16 gens | claude | **8/8 alive at every generation** |
| minimize ×16 gens | codex | 1/8 after ONE generation, pinned to the floor |
| minimize ×16 gens | claude | 2/8 after ONE generation, then a fixed point |

Detail worth keeping:

- **The blind prior is near-unanimous and cross-family**: values stay
  strings, last duplicate wins, key case preserved, no colon separator,
  no continuation, no sections; four of six raise `ValueError` on
  malformed lines. The stage-2 prior, replicated on a new subject.
- **The faithful chains are genuine rewrites, not copies**: all 17 files
  in each chain are distinct bytes, and structure churns freely
  (generation 0 is 29 lines; later claude generations run 38–81). The
  mechanism that preserves behavior is visible in the diffs: generation 1
  **documents** the quirks — generation 0 carries zero comment or
  docstring mentions of them, generation 1 carries eighteen. A careful
  rewriter canonizes the behavior it observes; the chain then inherits a
  stated contract where the original had an accidental one.
- **The minimize collapse is a cliff, not a curve**: one generation, then
  the floor. claude-min holds the exact same behavioral fingerprint for
  all fifteen generations after the collapse; its generation 1 is nine
  lines. codex-min's only later motion is one bit toggling between the
  prior's own two treatments of malformed lines (skip vs raise), one of
  which happens to coincide with generation 0. No behavior specific to
  generation 0 — coercion, first-wins, colon, case, continuation,
  sections — ever came back in either family.
- **The minimize attractor IS the blind attractor**: codex-min's endpoint
  behavior is exactly the fingerprint of four of the six blind controls —
  including a claude one — and claude-min's matches the fifth. Under
  pressure, the code in context stops mattering; gate plus prior fully
  determine the endpoint.

The tool's own instrument agrees the check is thin: `ret assess` on the
subject reports mutation=0.54 with 11 surviving mutants, the first being
the coercion regex emptied — the same surface the ladder measured.

## The reading

The equivalence class named by a root has a gravitational field, and the
shared prior is its center. A blind producer starts there. A neutral
rewriter orbits — the visible artifact, not the gate, carries the
unpinned intent, and carries it indefinitely. An optimizing rewriter
falls straight in, in one step, because an instruction that needs license
to drop something promotes the check to the whole definition of "what
must keep working": **optimization pressure converts unverified into
unnecessary**, with the original code in full view.

For the protocol this sharpens the ratchet's necessity beyond stage 2.
Stage 2 said: a boundary's silence is filled with prior at rebuild time.
The ladder adds: the same silence is spent as slack at *maintenance*
time, by the most ordinary request in software — make it simpler — and
no signal marks the moment it happens, because the name, honestly, never
moves. A behavior a consumer relies on is a behavior the check must pin;
nothing else — not the source sitting in context, not sixteen
generations of faithful history — holds it against the first instruction
with a reason to spend it.

## The honest limits

One subject, one probe battery, one model per family per chain, sixteen
generations, one rewrite instruction per condition. The faithful result
is stability under a *neutral* ask, not a guarantee — a differently
phrased neutral ask, longer chains, or other subjects may erode; the
instruction wording is a measured condition, not a constant of nature.
The probes measure divergence from generation 0, not correctness. And
survival under the faithful condition depended on generation 1 choosing
to document what it saw — a choice, not a mechanism the protocol
provides. The protocol's own mechanism is the pin.

## Where everything is

- `research/harness/ladder/` — subject claim, probes, chain runner,
  guided-rewrite producer, all 34 chain generations, 6 blind controls,
  `fingerprints.json`, per-chain ledgers.
- Chains ran 2026-09-29 on M1 (this machine), claude/sonnet and
  codex/gpt-6-sol; blind controls used all six stage-2 models. Both
  families un-metered (subscription CLIs).
