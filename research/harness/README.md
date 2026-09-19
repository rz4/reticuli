# Harness: a second full self-rebuild run

*Research tooling — not normative, not pinned.*

The first full-rebuild pass (2026-09-19) proved the machinery works — gpt-5 regrew
a small claim and reticuli's own `hooks.py` from criteria alone, both to the
right root — but could not complete a whole-tool or whole-kernel rebuild in that
environment. This directory prepares a second run that gets past the two blocks.

## The two blocks, and how this gets past them

1. **Wall clock / background kill.** `kernel.py` and `cli.py` are ~2,560 lines
   each; regrowing them takes far longer than a ten-minute foreground turn, and
   backgrounded rebuilds were killed early in the agent environment. **Fix: run
   the commands below in a real terminal** (your shell, `tmux`/`nohup` if you
   want to detach). No tool timeout applies there.
2. **Component store not carried.** `ret rebuild -o` does not copy a claim's
   component store into the blind room, so a layer built the `scripts/selfclaim.py`
   way cannot resolve the layers beneath it — rebuild then asks the producer to
   regrow the entire stack from one layer's check. **Fix: flat claims.**
   `build_flat_layers.py` declares each layer's lower modules as pinned INPUTS
   (present, read-only) and only that layer's own modules as `generated`, so
   `ret rebuild` withholds just those and supplies the rest as context.

## Path A — per-layer (recommended, converges)

Build the flat claims and get one rebuild command per layer:

```
PYTHONPATH=src python3 research/harness/build_flat_layers.py --into /tmp/flat
```

It prints a command per layer. Run them in a terminal, smallest first — `agents`
and `launcher` (one module) converge in minutes for pennies; `exchange` and
`authoring` are moderate; `kernel` and `surface` (cli.py) are the long, dear
ones. Each command sets cost metering:

```
PYTHONPATH=src RETICULI_AGENT_TURNS=120 RETICULI_PRICE="1.25,10" \
  RETICULI_USAGE=/tmp/flat/agents.usage.json \
  python3 -m reticuli rebuild /tmp/flat/agents --producer openai -o /tmp/flat/agents-rebuilt
```

`RETICULI_AGENT_TURNS` caps the tool-loop (raise it for the big layers, but each
turn costs); `RETICULI_USAGE` drops a `{tokens, usd}` ledger; `RETICULI_PRICE`
is gpt-5's "$in,$out per Mtok" (update if the rate changes). `agents` was
validated this way (converged, ~$0.06, same root).

The kernel layer's flat claim has nothing beneath it, so it is the **true blind
kernel rebuild** — gpt-5 writing `kernel.py` from `kernel_check.py` alone. That
is the flagship and the hardest; give it the most turns and expect it to be the
one that either lands the whole thesis or shows exactly where the check
under-determines the kernel.

## Path B — the whole tool, blind

The purest "rebuild all of reticuli": the repo self-claim is self-contained (all
18 modules are plain `generated`, no components), so it rebuilds directly.

```
PYTHONPATH=src RETICULI_AGENT_TURNS=200 RETICULI_PRICE="1.25,10" \
  RETICULI_USAGE=/tmp/repo.usage.json \
  python3 -m reticuli rebuild . --producer openai -o /tmp/reticuli-rebuilt
```

This asks gpt-5 to regrow all of `src/` and pass every criterion including
`self_check` — which requires the regrown tool to self-host (seal the six
layers). It is the hardest target and most likely to hit the turn cap; treat a
partial result (which criteria pass, where it stalls) as the finding. Costliest
by far — watch the usage ledger.

## After a rebuild — what differs

For any layer or the whole repo that produces an output dir:

```
# same identity? (the root names the criteria, not the code — this should accept)
PYTHONPATH=src python3 -m reticuli crosscheck <flat-claim> <rebuilt> -v

# what varies within the equivalence class (confirms free variation), and
# whether anything the criteria DON'T pin was dropped (a tightening target):
diff -ru <flat-claim>/reticuli <rebuilt>/reticuli
```

A converged rebuild that lands the same root but drops behavior the gate never
checked is exactly the signal that folded G1/G6/G2/G3/G4 this pass (see
`research/provenance/revision-2026-09-19-self-rebuild-tightening.md`). Record
new ones the same way: mutation-prove, then tighten the owning criterion.

## Notes

- `OPENAI_API_KEY` must be set (it is, in the owner's environment). Named
  producers preflight the credential before spending.
- Nothing here is pinned; `research/harness/` is outside the repository root.
- The scratch claims and rebuilt trees are disposable — build them under `/tmp`.
