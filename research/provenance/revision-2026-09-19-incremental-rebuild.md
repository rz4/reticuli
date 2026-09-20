# Revision: rebuild reuses sealed components — the incremental build for large software

The repository claim moved on 2026-09-19, `fa75cc33…` → `45726d9f…`, and the
exchange layer with it, `94cb93b5…` → `eef4a89c…` (only exchange moved; the
layers above it name it, they do not pin its root). A hardening: `exchange_check`
now rejects a rebuild that fails to reuse a sealed component.

## What prompted it

The second full gpt-5 self-rebuild (`rebuild-gpt5-2026-09-19-layers.md`) hit a
scaling wall: the kernel would not regrow in one shot, and the tractable path is
to build large software the way `make` does — as a stack of verified pieces,
reusing what is already built and regrowing only the new part. Reticuli almost
supported this and did not:

- `ret rebuild --recursive` exists, but it **regenerates the whole stack**
  leaf-first (`registry.rebuild_chain`). That is the full-trust redo — and it is
  exactly what made the kernel intractable (reproduce all 2,562 lines).
- Plain `ret rebuild` on a composed claim did **neither** — it did not carry the
  component and wrongly asked the producer to reproduce it. The missing mode was
  **reuse**: carry the already-sealed component in as fixed bytes, regrow only
  this layer. And no criterion caught the gap — a cooperative producer that knew
  how to write the component masked it.

## What moved, and why the root moved with it

The behavior is implemented in `src/` (outside the root, a free change) and
pinned by a criterion (inside the root, so identity moves):

- **`src/reticuli/registry.py`** — `rebuild_chain` gains a `reuse` mode: instead
  of recursively regenerating each component, it threads the sealed component's
  bytes up unchanged (via `produce_from`/`input_from`) and regrows only the top
  layer. Also threads `guidance` through, which the recursive path had dropped.
- **`src/reticuli/cli.py`** — plain `ret rebuild` on a claim that has components
  now uses the reuse path; a bare claim still rebuilds directly, and
  `--recursive` still regenerates the whole stack.
- **`criteria/exchange_check.py`** (pinned — moves the root) — pins it: a
  producer that can write only `app.py`, with no rule for the component's
  `lib.py`, must still rebuild the composed claim to its own root, because
  `lib.py` is reused from the sealed `libcode` and never asked of the producer.
  Closes the coverage gap.
- **`criteria/self_check.py`** — `PINNED["exchange"]` bumped to `eef4a89c…` with
  a dated note in the ratchet log.

## Verification

- `python3 gate.py` passes; `ret verify .` holds at `45726d9f…`; `ret audit .`
  `earned` cold in a seatbelt sandbox, 42.9s.
- The reuse path proven directly: a composed layer rebuilt with a producer that
  wrote only the top modules landed the sealed root (crosscheck accept), and the
  component's bytes were byte-identical to the sealed original (reused, not
  regenerated). `--recursive` (regenerate) still works — `exchange_check` green.
- `ruff` clean; `pytest` 94 passed, 1 failed (the known `test_streams` sandbox
  flake).

## Where this sits

This is Stream A of the layered-build work the scaling wall called for: the
**incremental primitive** — reuse verified layers, regrow only the new one. Stream
B, decomposing the kernel into sub-claims so `--recursive` can regrow *it* in
tractable steps, builds on this and is the next piece. Together they are the
"build large software as a verified stack" workflow.
