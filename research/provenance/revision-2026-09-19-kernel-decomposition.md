# Revision: the kernel becomes a chain — kernel-core carved from the kernel (pilot)

The repository claim moved on 2026-09-19, `45726d9f…` → `d5911abd…`, and **every
layer root moved with it** — the deepest transition in the tree. The kernel, one
monolithic claim since the beginning, is now **two** sub-claims:

- **kernel-core** (`35bba64f…`) — the identity machinery: the constants, the path
  and bytes boundaries, recipe parsing, the canonical root and build-digest, and
  seal/verify. Everything the kernel needs *before* it ever runs a gate. Judged
  by the new `criteria/kernel_inner_check.py`. It is the sealed claim at
  `examples/kernel/`.
- **kernel** (`c70343…`) — the outer kernel built on the core: execution, the
  sandbox, audit, rebuild, records, cost, crosscheck. `src/reticuli/kernel.py` is
  now the outer implementation *and* a facade that re-exports the core, so the
  ~1,000 `reticuli.kernel.X` references across the tree keep working unchanged.

## Why

The second full gpt-5 self-rebuild showed the kernel does not one-shot-regrow:
2,562 lines against 1,865 lines of checks (including byte-exact golden vectors)
is too big a step for a bounded producer loop. The tractable path is to build
large software as a chain of smaller verified pieces — which needs both the
incremental *reuse* primitive (landed earlier today, `1b98a5c`) and the target
itself decomposed into checkable sub-claims. This is the **pilot**: a two-way
split proving the whole approach — the facade, the `selfclaim`/`self_check`/
`kernel_parity` plumbing, and the lockfile growing from six roots to seven — with
the identity core carved out first because it is the best-specified piece (its
serialization has a second implementation in `reference.py` and a golden-vector
suite).

## What moved, and why the root moved with it

- **`src/reticuli/_kernel/inner.py`** (new) + **`src/reticuli/kernel.py`** (facade
  + outer) — the module split. Free (src is outside the root).
- **`criteria/kernel_inner_check.py`** (new, pinned) — the core's acceptance
  suite: the canonical root and build-digest golden vectors, seal/verify, the
  root-moves-on-input invariant, and the path/bytes boundaries, all against
  `reticuli._kernel.inner`. Also a net-free/stdlib-only wall over the core
  modules.
- **`scripts/selfclaim.py`** — the kernel `LAYERS` entry split into `kernel-core`
  + `kernel`; nested `_kernel/` module copying; the generated glob widened to
  `reticuli/_kernel/*.py`; the format-3/envelope ceiling moved to `kernel-core`.
- **`criteria/kernel_check.py`** — `KERNEL_LAYER` and the nested-kernel audit
  extended to the `_kernel` modules.
- **`criteria/kernel_parity.py`** — stages the full split package and runs *both*
  kernel suites against the living kernel; the drift anchor now guards the inner
  suite against `examples/kernel`.
- **`criteria/self_check.py`** — `PINNED` grows to seven roots; the
  `examples/kernel` comparison repoints to `kernel-core`.
- **`gate.py`** — both kernel suites are staged claim-gates.
- **`reticuli.toml`** — declares the `_kernel/*.py` generated outputs and the new
  `kernel_inner_check.py` input.
- **`examples/kernel/`** — re-sealed as the `kernel-core` claim (`35bba64f…`).
- **`tests/test_selfcontained.py`** (free — tests are outside the root) — its
  structural-path whitelist recognizes `_kernel/`, the kernel's subpackage, the
  same package-internal shorthand `reticuli/` already was.

## Verification

- `python3 scripts/selfclaim.py` builds **7 layers, all verify fresh**.
- `python3 gate.py` passes — every criterion, including `self_check` (7 layers,
  deep audit re-earns 6 beneath surface) and `kernel_parity` (both suites against
  the living kernel).
- `ret verify .` holds at `d5911abd…`; `ret audit .` `earned` cold in a seatbelt
  sandbox, 43.1s.
- The facade exposes the full surface (public names + the poked-private
  `_hash_file`, `_inputs`, `_JAILED`, `_safe`, …). `ruff` clean; `pytest`
  94 passed, 1 failed (the known `test_streams` sandbox flake).

## What's next

This is the two-way pilot. The full decomposition — subdividing further into
recipe / identity / seal / run / build / attest / crosscheck (eight sub-layers on
a clean DAG, no cycles) — is the follow-up, and each sub-layer then becomes small
enough for a producer to regrow. With the reuse primitive already in place, that
is the path to rebuilding the kernel, and eventually the whole tool, as a stack
of independently verified pieces.

## Stage 1 of the 8-way (same day, repo root → 8c0977bd)

The inner half is now done: `kernel-core` subdivided into **four** layers on the
clean inner DAG — **core** (constants, the path/bytes boundaries, atomic IO),
**recipe**, **identity** (the canonical root/build-digest serialization), **seal**
— each a small `_kernel/*.py` module with its own suite
(`core_check`/`recipe_check`/`identity_check`/`seal_check`). `kernel.py` re-exports
the whole chain. The kernel is now 5 layers (core→recipe→identity→seal→kernel),
the repository 10; `selfclaim` builds all 10 fresh, `gate.py` passes, `audit .`
earns `8c0977bd` cold. `examples/kernel` was retired during the churn (it is
unpinned; `self_check`/`kernel_parity` skip it conditionally, and the reference-
agreement test drops it) — it will be re-sealed as the settled core once the outer
half lands. **Remaining:** the outer subdivision of `kernel.py` into
run / build / attest / crosscheck (the harder half — sandbox, execution, the
order-coupled crosscheck suite), which completes the 8-way.
