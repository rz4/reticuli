# The substitution demonstrator — a build plan

*2026-09-23, forward-looking (proposal, not normative). The concrete next
experiment both models converged on, drafted into something buildable. It tests
the killer capability (credible exit / compositional substitution) and the one
metric that the completed quirkcalc curve does **not** establish: that
gate-passing replacements are equivalent **to a consumer**, not just to each
other on a frozen probe set.*

## Why this, now

The quirkcalc curve showed the basin contracts to a behavioral point on a frozen
probe set while structural diversity rises. It did **not** show that two
*gate-passing* implementations are safe to *substitute under a consumer* — the
property astra argued is the real ground floor ("consumer-relative
sufficiency"). This experiment measures exactly that, and folds in soundness
gaps A/B/C as prerequisites.

## Shape

Two layers, both reticuli claims:

- **Dependency claim `D`** — a bounded, property-rich component (a small
  structured-data parser: `parse(text) -> value | error`). A deliberately
  partial `C_0^D` (happy path pinned; strictness/edge surface open), exactly as
  quirkcalc was set up.
- **Consumer claim `P`** — a real user of `D` (e.g. a component that reads a
  config with the parser and computes a result). `P`'s gate exercises `D`
  through its interface on **consumer-relevant** inputs, and pins the consumer's
  observable result.

## What it must establish (astra's list, made testable)

1. **Swapping the dependency preserves both claim identities.** Replace `D`'s
   implementation with a different gate-passing one; `D`'s root and `P`'s root
   are unchanged. *(This is where composition-identity must be right — a parent
   commits to `D`'s claim, not `D`'s bytes; today it threads bytes into pinned
   inputs, registry.py:234, so this step will expose whether the fix is needed.)*
2. **Realization evidence changes appropriately.** `D`'s build digest and the
   bound execution evidence differ across the two implementations; identity does
   not.
3. **Consumer-relative sufficiency, measured.** Produce **two substantially
   different `D` implementations that both pass `C_0^D`, one deliberately
   exploiting the underspecified surface.** Run `P` against each. The metric is
   **downstream failure among gate-passing dependencies**: does a
   `C_0^D`-accepted-but-divergent `D` break `P`? Every break is a *missing
   obligation in `D`'s boundary that `P` depended on silently* — the exact
   failure the frozen-probe convergence cannot see.
4. **A locally-accepted candidate that violates a consumer assumption exposes
   the missing obligation** — and the ratchet closes it (pin the consumer-
   relevant behavior into `C^D`), then both `D` implementations are re-judged.
5. **Directory and record transports enforce identical obligations** (closes C).

## Prerequisites to fold in

- **A** (guidance in the judging room): materialize the stripped recipe, so `D`
  and `P` gates cannot be swayed by non-identity-bearing guidance. Repro exists
  (`research/audits/finding-a-repro/`).
- **B** (rebuild root-equality): assert a rebuilt `D` seals to `D`'s root, so
  "rebuilt the dependency" means what it says.
- **C** (record obligations): the substitution evidence must carry `D`'s
  declared obligations across the record transport.

## Harness reuse

The contraction instrument already supplies most of it: `boundary` (per-layer
`C`), the differential + partition classing + reducer (find where two `D`s
diverge), `structure` (confirm the two `D`s are genuinely different), and the
ground-truth-aware survey (here the "oracle" is `P`'s consumer contract, not a
reference `D`). New piece: a **consumer harness** that runs `P` against a
supplied `D` and reports consumer-observable pass/fail — i.e. `differential` one
level up, with `P`'s result as the outcome.

## What it would show, and the honest limit

Success = a `D` swap that preserves identities, changes evidence, and keeps `P`
acceptable on independently-designed consumer challenges — **and** a divergent
`D` that passes `C_0^D` but breaks `P`, whose repair is a single pinned
obligation. That demonstrates credible exit *with* consumer-relative sufficiency,
which is the real claim. Limit: like the quirkcalc curve, it shows sufficiency
against the consumer challenges *actually run* — not universal safety. The value
is the method (find the missing obligation before it ships), not a proof of
completeness.

## Decisions needed from the keyholder before building

- The dependency subject (recommend a small structured-data parser with a
  round-trip/property oracle) and the consumer.
- Whether to fix A/B/C first (root-affecting, keyholder transitions) or run the
  demonstrator against the current code and let it *exhibit* the gaps.
- Producer budget (codex un-metered + claude subscription; stop-on-quota).

Everything above is uncommitted `research/`; nothing here moves a real root.
