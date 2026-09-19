# Revision: the surface gate pins what a rebuild showed it could drop

The repository claim moved twice on 2026-09-19, in one self-rebuild pass:
`c1f98059…` → `2bc22b95…` (the two mutation-proven regressions) → `fa75cc33…`
(the three looser schema items). The surface layer moved with each step,
`0bc4cc84…` → `bde24987…` → `1e865511…`; kernel (`fac55f89…`) and the four
layers between held throughout. Both are **hardenings**, not corrections:
`surface_check.py` now rejects implementations that passed before — so each is
an identity-bearing transition, and the intermediate roots are retired in favor
of `fa75cc33…`.

## What prompted it

The trigger was the "rebuild all of reticuli with gpt-5, see what differs" pass.
The full-tool and full-kernel rebuilds are not completable in this environment
(kernel.py and cli.py are ~2,560 lines each and exceed a ten-minute foreground
wall; background rebuilds are killed; and `ret rebuild -o` does not carry a
claim's component store into the blind room, so a middle layer cannot resolve
the layers below it — recorded here as a real operational limit, separate from
the claim). But one faithful, converging rebuild told the whole story.

Given `agents_check.py` and the surrounding modules as read-only context, gpt-5
regrew `hooks.py` from scratch in ~2 minutes for ~$0.06, landing on our exact
root. Its `hooks.py` was 140 lines to our 179, and it had **dropped `consume()`
entirely** — the function `cli.py` calls for the `ret hook` command — because
`agents_check` never exercises it. A generative rebuild writes the *minimal*
code that satisfies the gates it is judged against, and discards every behavior
those gates do not check. (In the full claim `surface_check`'s `ret hook` test
re-pins `consume()`, so the whole is tighter than any one layer — but the
principle was now demonstrated live, not argued.)

That is exactly the failure mode the 2026-09-18 self-rebuild completeness audit
mutation-proved for two behaviors the surface gate did not exercise. This
revision pins them.

## What moved, and why the root moved with it

`criteria/surface_check.py` is a pinned input, so adding to it moves the root —
which is the point. Two assertions were added:

- **The `--json` refusal envelope.** A `--json` verb that refuses (no claim at
  the target — the first thing automation hits) must still speak the envelope on
  stdout: `ok:false`, `status:"error"`, the fact under `data.error`, stderr
  empty, exit 1. The suite only ever built the envelope on success paths, so a
  rebuild judged only on success could print refusals as a bare stderr line and
  certify clean — breaking `ret <verb> --json | jq`. Mutation-proven: reverting
  this on a copy of `src` still passed the *old* suite.
- **`run`'s exit-code passthrough.** `ret run` must return the child's exit code
  unchanged, so a session can use it as a predicate. The suite only ran `run`
  with a passing command, so a rebuild could swallow every failure and turn a
  red run green. Mutation-proven the same way.

Then the second step folded the three items the audit had left as policy, since
the keyholder asked for them:

- **The per-verb `--json` `data` key sets.** `verify`, `audit`, `assess`, and
  `status` each now pin the documented keys automation reads (so a rebuild
  cannot rename `deciding` or drop `discovery`), plus `audit`'s per-gate
  `quarantine` spelling (the record says `sandbox` — a deliberate seam, now
  pinned as one).
- **The envelope `status` vocabulary.** `verify→fresh`, `audit→earned`,
  `assess→measured`, and a claim-state word for `status` — the words a caller
  switches on, previously free below `verify`/`crosscheck`.
- **The exit-2 seam.** An invalid invocation (a `--json` call that never reaches
  a verb) stays a plain `ret: <verb>: <fact>` stderr line with no envelope,
  distinct from the exit-1 refusal that does speak one.

`criteria/self_check.py` is also pinned; its `PINNED` lockfile carries the
surface layer's root, bumped to `bde24987…` then `1e865511…`, each with a dated
note in the same ratchet log the prior ten surface moves use.

## Verification

- `python3 gate.py` — all criteria pass, including `self_check` rebuilding the
  six layers and matching the updated `PINNED`, and the tightened
  `surface_check`.
- `ret verify .` silent (holds at `fa75cc33…`); `ret audit .` `earned` at that
  root, cold in a seatbelt sandbox, 48.4s. (Both steps were earned this way; the
  first held at `2bc22b95…`.)
- `ruff check` clean; `pytest` 94 passed, 1 failed — the pre-existing
  `test_streams` audit-under-sandbox flake on this machine (unrelated root
  `27a8fc16…`, identical on the prior root, green in CI).

## Left open

The surface machine contract is now fully pinned; what remains is the full-scale
producer rebuild of the kernel and surface layers (kernel.py and cli.py, ~2,560
lines each). That is infrastructure-blocked here, not thesis-blocked — it needs
an environment without the ten-minute foreground wall and the background-kill,
and it needs the component-store gap in `ret rebuild -o` worked around. The
scaffolding for that second run — a flat-claim builder that sidesteps the
component gap, and a runbook — is prepared under `research/harness/`.
