# Second full self-rebuild with gpt-5: the layers, what converged, what didn't

*Research record — what was tried and what it showed. Not normative.*

The second attempt to rebuild reticuli from its own criteria with a real
producer (`--producer openai`, gpt-5, agentic: read/write/run-gate loop). It used
the flat-claim scaffolding from `research/harness/` to sidestep the
component-store gap, ran the six layers detached in parallel (surviving the
agent-turn wall that blocked the first attempt), and metered cost per layer.

## What ran, and what it cost

| layer | modules regrown | verdict | root | cost |
|---|---|---|---|---|
| agents | `hooks.py` | **converged** | `76cb7e40…` = ours | $3.47 |
| launcher | `launcher.py` | **converged** | `cb198e87…` = ours | $5.02 |
| authoring | `render, authoring, feedback, pack` | **converged** | `9d402b39…` = ours | $7.83 |
| exchange | `_util, registry, transfer, attest, record` | **converged** | `3ecf0e1d…` = ours | $25.82 |
| surface | `assess, heldout, reuse, cli, __main__` | capped (cost) at ~5 min | — | unrecorded |
| kernel | `__init__, kernel` | **did not converge**, killed at ~48 min | — | unrecorded |

Recorded total **$42.14**; the two killed layers wrote no ledger (the producer
reports usage only on a passing gate or a clean finish), so the true total is
higher — a realistic estimate is ~$75–100, kernel being the bulk of the
unrecorded spend. `surface` was capped deliberately (highest cost, lowest
marginal value — the CLI surface is already well pinned); `kernel` was given a
15-minute cost cap on top of its ~33-minute grind.

## Finding 1 — the equivalence class is genuinely wide

All four completed layers regrew to our **exact roots**, so each passes its
layer's acceptance check byte-for-byte — while being structurally very different
code. gpt-5 rewrote every module with its own factoring, usually far leaner and
exposing a fraction of the public surface: `render.py` 214L/13 public → 87L/1;
`_util.py` 126L/14 → 42L/5 (renamed); `launcher.py` 365L/22 public → 480L/5
(inlined); `hooks.py` 179L/7 → 141L/2. Same identity, different program. That is
the thesis working hard: the root names the criteria, not the code.

## Finding 2 — same root is not the same tool

The rebuilt modules are **not drop-in**. Assembling gpt-5's eleven converged
modules with our kernel/cli and running the full CLI battery fails at import:

```
ImportError: cannot import name 'STORE' from 'reticuli._util'
```

Each rebuild is internally self-consistent but invents its own internal API and
drops any internal surface its layer's gate never exercises — gpt-5's `hooks.py`
has no `consume()` (which `cli.py` needs), its `render.py` exposes 1 of the ~10
helpers `cli.py` imports, its `_util.py` omits `STORE`/`safe_path`/`hash_bytes`
that six other modules import. **The per-layer gates are looser than the
assembled tool needs.** A layer conforms to its own check and then cannot support
the layer above it. This is the same species of gap the 2026-09-19 tightening
closed at the surface, one level up — only much wider at the per-layer level.

The consequence: the meaningful identity boundary is the **whole-repo self-claim**
(all criteria at once, where `surface_check` drives `cli → render`,
`ret hook → consume`, the whole pipeline), not the layer chain. Only a single
rebuild satisfying every criterion together is forced to make the internal
surface rich enough to compose.

## Finding 3 — the kernel does not one-shot-regrow

The flagship. `kernel.py` is 2,562 lines; `kernel_check.py` is 1,865 lines and
includes byte-exact golden vectors (the producer must reproduce exact SHA-256
preimages, not just correct behavior). Blind — nothing supplied beneath it — gpt-5
iterated for ~48 minutes toward its 250-turn cap and never got the gate green. It
had built a 703-line partial `kernel.py` (valid Python, ~27% of ours) when the
cost cap killed it. `surface` (cli.py, 2,566 lines) was similar: a 794-line
partial when capped at ~5 minutes.

So at this scale the criteria are **re-earnable but not one-shot-regrowable** by a
single agentic gpt-5 loop in a bounded budget. This is not a thesis failure — the
smaller layers prove re-growth works — it is a statement about producer strength
vs. target size and check tightness. Regrowing the kernel would need a different
strategy: far more turns (and money), guidance (`--without-guidance` off), a
stronger or more patient loop, or decomposing the kernel itself into checkable
sub-claims.

## Takeaways

- The wide equivalence class is real and now demonstrated across 11 modules and
  ~3,500 lines, cross-vendor.
- "Independent rebuild" as a trust primitive holds cheaply at module scale and
  does **not** hold cheaply at kernel scale — worth stating plainly in any
  adoption claim.
- The next producer experiment (research thread #1) is better spent on the
  tightness/re-earn curve across many small claims than on brute-forcing the
  kernel; the kernel wants its own decomposition or a guided run, budgeted
  deliberately.
