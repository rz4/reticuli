# The succession run

*Research tooling — not normative, not pinned.*

The repository's root excludes `src/` by design: the implementation is the
equivalence class, not the identity. This harness takes that promise to its
end — **the implementation dematerializes**. A complete generation-1
`src/reticuli` is grown in rooms that never contain the original: each of
the nineteen layers (`scripts/selfclaim.py`) is regrown blind from its
acceptance check, with the layers beneath it supplied as pinned context
**from the generation-1 tree, never from the original** — so the finished
tree stands entirely on regrown ancestry. One lineage per producer family.

Scaffolding, honestly labeled: each layer gets a throwaway flat claim
sealed entirely from the original source (check + lower modules pinned;
the layer's own modules generated, withheld from rooms). At rebuild time
`input_from` threads the gen-1 lower modules into the room in place of
the originals — kernel-ledgered, inside the tamper snapshot — so the
room never holds an original implementation byte of this or any lower
layer's regrown replacement. Threaded inputs move the scaffold root by
design; those roots are construction jigs. The judgments that matter
come after (`judge_gen1.py`):

- **identity** — the repository's own claim audited with all 37 generated
  modules substituted from the lineage: `REPO_OK` re-earned means the
  repository's root admits the regrown implementation;
- **confidence / drift** — `tests/` is deliberately outside the root, so
  it doubles as a held-out probe battery for the surface the criteria do
  not pin; every failure is a measured divergence, and every divergence a
  candidate pin (the ratchet's input);
- **succession** — the regrown tool run *as the tool*: verify the
  repository, refuse a tampered claim, audit the repository cold, and
  drive a generation-2 rebuild of the core layer through its own kernel.

A scaffold seal that fails warm is itself a finding: original layer
modules that do not pass their own gate on generation-1 lowers expose a
seam the layer criteria fail to pin.

    python3 run_succession.py --lineage claude     # resumable, ledgered
    python3 run_succession.py --lineage codex
    python3 run_succession.py --status
    python3 judge_gen1.py --lineage claude --full-gate --tests --bootstrap
