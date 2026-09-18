# Design note: the capture engine (Phase 3)

*Research/design record — a proposal, not yet built and not normative. Scoped by
[the six-strangers audit](../audits/six-strangers-2026-09-18.md).*

The goal of this phase, from the "Next Pass" direction: turn reticuli from "seal
the tidy project I hand you" into "watch a workspace and assemble an honest
record of whatever happened in it." The target experience is Git-shaped:

```
cd project
ret init            # this workspace is now watched
...arbitrary work by humans, agents, scripts, over any span...
ret pack            # reticuli assembles the honest record of it
```

## What is already true (grounded in the code)

- **Capture is already workspace-scoped, not session-scoped.** Hooks and
  `ret run` append to one `.reticuli/draft.jsonl`; independent processes across
  "sessions" all land in the same trace, surviving session-end, new processes,
  and multiple harnesses (confirmed empirically in the audit). §1 is
  substantially built.
- **The trace has zero authority.** `authoring.build_claim` re-runs every gate
  cold in a clean workspace and seals only if the pinned verdicts reproduce
  (`authoring.py:237-315`). A noisy or wrong trace cannot smuggle a false result
  into a claim — it just fails to certify. This is the spine of the design and
  must not change.
- **An observation vocabulary already exists** — in `feedback.advise`
  (`feedback.py`): per file, `observed` (read|write|command|-), `declared`
  (input|generated|validated|-), `evidence` (hook|shell|gate|trace|-), plus
  `covered`/`sealable`. It is a read-only advisor, separate from `pack`.
- **The record's honesty principle already exists:** in `spec/record.md`, an
  absent cost key means *unmeasured* and is never written as zero, so a reader
  can always tell "free" from "unknown". This is the model to extend to capture.

## What is missing (the real gaps)

1. **`pack`/`propose` is silent about what it could not establish.** It
   *includes*, *silently drops*, or *hard-refuses* — no middle "observed but not
   sealable, and here is why" path (`authoring.py:168-234`). A traced write to a
   file that no longer exists is dropped with no word (`_names_a_file`,
   `authoring.py:35-58`); a present-but-untraced file becomes nothing.
2. **`ret run` and subprocesses capture only the command string.** `run` appends
   `{event:bash, cmd, via:shell, ts}` and nothing about file effects or exit
   code (`cli.py:205-215`). Any work done through a subprocess is outside the
   closure. This is the biggest coverage hole.
3. **Only Claude Code is wired.** `ret init` rejects any other harness
   (`cli.py:197`); `hooks.py` speaks Claude Code's exact event vocabulary.
4. **The ledger has no durability or causal structure.** Both `draft.jsonl` and
   `ledger.jsonl` are plain text-mode appends — no lock, no fsync, no
   atomic-rename, no event/parent identity (only wall-clock `ts`). It relies
   solely on `O_APPEND`. Fine for one process writing short lines; unproven
   under the concurrent subagent trees the direction envisions.
5. **The wired hook command is bare `ret hook`**, assuming `ret` is on PATH;
   running via `python3 -m reticuli` gives silently no-op hooks (audit #4).

## The load-bearing verdict: this phase moves no root

Every gap above is fixed in `src/` or in residue (the trace, the cost ledger,
CLI output) — all outside the sealed identity:

- `hooks.py`, `cli.py`, `authoring.py`, `feedback.py`, `kernel` ledger helpers →
  `src/`, generated, excluded from the root.
- `.reticuli/draft.jsonl` and `.reticuli/ledger.jsonl` → residue, gitignored,
  never root inputs.

The **one** way Phase 3 could become identity-bearing is a deliberate choice to
put capture provenance *into the sealed record* (`spec/record.md`, pinned) or
the claim recipe (`spec/claim-format.md`, pinned). The recommendation is **not
to**: capture is about how a claim was *arrived at*, which the design already
holds separate from what the claim *is*. Keep provenance as residue and
advisory; let the cold re-earn remain the only authority. That keeps the whole
phase free of the ratchet. (If we ever want a *signed* statement of provenance,
that is a record-format decision to take on its own, later, as one transition.)

## Proposed increments

Ordered cheapest-and-most-certain first. Each is independently shippable and
CI-gated; none reseals.

### A. Honest pack — the warnings block (§3/§5) — FREE

Wire `feedback.advise`'s observed/declared vocabulary into the `pack` path so a
pack **states what it could not establish instead of dropping it silently**, and
still packs (the honest-partial principle). Extend the triad to the fuller set
the direction names — observed / declared / sealed / inferred / **unobserved** —
and emit a warnings block on stderr, e.g.:

```
packed  4e7c…
  warnings
    1 observed write dropped: app.py no longer on disk
    2 present files not observed: config.yaml, data/seed.json
    producer cost not established (no transcript in window)
```

Smallest, highest-value move: it makes today's capture honest and makes the
value of increments B/C concrete. Pure wiring of existing logic + a renderer.

### B. File-effect capture for `ret run` and subprocesses — FREE

Give `ret run` a before/after workspace scan (path → content hash) and derive
`write` events for created/modified files, recording the exit code too. Reads by
a subprocess cannot be derived portably without tracing, so they stay
**unobserved** and the taxonomy (A) says so rather than guessing. This closes
the "arbitrary work, including scripts" gap without strace/dtrace and without
platform-specific machinery. This is the largest genuine build of the phase.

### C. Multi-harness adapters — FREE

Generalize `hooks.py` from Claude-Code-only to a small set of payload adapters
(map a harness's event payload → reticuli's canonical event vocabulary), with
`ret init --agent <name>` selecting one and a documented `generic` contract for
harnesses we don't special-case. Also fix the bare-`ret hook` wiring (gap 5) to
a form that works without a PATH install. Composes with A/B.

### D. Ledger durability and causal structure (§4) — FREE

Make the append survive concurrency and crashes, and record causality:

- Give each event an `id`, a `run`/process id, and a `parent` where known; keep
  `ts` as informational only (causal order must not depend on wall-clock).
- Prefer **per-process fragment files** (`.reticuli/draft.d/<run>.jsonl`) that a
  reader merges deterministically, over locking one shared file — no cross-
  process interleaving, crash-safe, and it matches the direction's "independently
  appendable fragments that merge." Readers (`authoring._events`,
  `kernel.ledger_events`) learn to merge the directory.

Needed before heavy concurrent-subagent use; not before A/B are useful.

### E. Formalize `ret init` as the workspace boundary (§1) — FREE

Mostly documentation and small polish: state the Git-shaped lifecycle, confirm
capture's cross-session durability in the docs, and land the gap-5 wiring fix.

## Sequencing and stopping

A → B → (C, D in either order) → E, each its own CI-green `src` change. Nothing
in this phase reseals, so there is no transition ritual and no signing — the
identity stays exactly where the ratchet put it. If the reference-corpus work
(Phase 4) starts consuming capture data, it reads this residue; it does not
change it.

## Out of scope / reserved

- Putting capture provenance into the sealed record or claim (identity-bearing;
  deliberately deferred, see the verdict above).
- The paid blind proof, the signing ceremony, the public adoption experiment,
  and the license — all owner's acts, unchanged by this phase.
