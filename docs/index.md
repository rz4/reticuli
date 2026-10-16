# reticuli

Reticuli names software by a SHA-256 root over its **criteria, specification,
and recipe — deliberately excluding the implementation**. The implementation
is generated: one member of an equivalence class, rebuilt blind by any
conforming producer from the acceptance criteria alone, and judged by a gate
that is re-earned cold in a sandboxed room. `verify` compares the root;
`audit` re-earns it. A verdict is three-valued — accept, reject, or
*incomplete* — and an unmeasured declared condition never accepts.

Two claims live in this repository, in separate orbits:

- **The primary claim** (`src/`, `criteria/`, `spec/`, `reticuli.toml`) —
  the slow half. Every change to what is pinned moves the root, retires the
  population of qualifying reconstructions, and costs a keyholder signature.
- **Zeta** (`zeta/`) — the companion, the fast half. It puts pressure on the
  equivalence class: probes populations of implementations, reads what the
  criteria failed to say, and queues each finding for a signature. Nothing
  the primary root depends on may reach into zeta; the pinned
  `boundary_check` enforces exactly that.

The only bridge between the two speeds is a human signature.

## How to read this site

**[The implementation, woven](book/index.md)** is the heart of it: every
module of both claims rendered in the old style — full source in reading
order, with the code's own narration (module docstrings, `#:` attribute
notes, the why-comments) lifted out beside it. The pages are *derived from
the bytes*, never written about them, because the implementation can be
regrown at any time and hand-written API docs would lie within a week.
Regenerate with `python3 docs/weave.py`.

A suggested reading order for a first pass through the kernel:

1. `reticuli._kernel.core` — vocabularies and constants: what a verdict,
   a cost, a confinement level *are*.
2. `reticuli._kernel.recipe` — the pinned recipe: inputs, steps, gates.
3. `reticuli._kernel.identity` — the root itself: what is hashed, what is
   deliberately not.
4. `reticuli._kernel.build` — rooms, materialization, the environment
   scrub, rebuild.
5. `reticuli._kernel.run` / `attest` — execution, the ledger, and the
   record: the one file format third parties may parse.
6. `reticuli._kernel.crosscheck` — independent realizations compared;
   where a declared floor is re-earned.
7. Then the surface (`reticuli.kernel`, the CLI) and the companion
   (`zeta.lib.*`), which reads best starting from `zeta.lib.probe` and
   `zeta.lib.split`.

**The guides** (quickstart, producers, receiving, threat-model, …) are the
hand-written operational docs. **What is deliberately not rendered**: the
pinned bytes themselves — `criteria/`, `spec/`, zeta's criteria — because a
rendering of a pinned input is a place for a reader to be misled; read those
bytes directly, they are the identity.
