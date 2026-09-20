# Revision: cli.py splits into a _cli/ subpackage — the surface decomposition begins

The repository claim moved on 2026-09-20, `ecb41d6f…` → `382f4b8c…`, and the
surface layer with it (`25dda33b…` → `44bbfb6b…`; only surface moved). This
starts the decomposition of the last oversized module, mirroring the kernel.

## Why

The whole-tool rebuild left one holdout: `surface` did not regrow because
`cli.py` is 2,574 lines — the twin of the old monolithic `kernel.py`, which also
would not regrow until it was decomposed. The remedy is the one that already
worked: split `cli.py` into a chain of smaller modules a producer can regrow.

## What moved (stage 1: the module split)

`cli.py` split into **`src/reticuli/_cli/`**, seven role modules on a clean
bottom-up DAG (the seams are architectural roles, not the five help-groups —
the concept groups cut across the dispatch switch, not along a dependency
boundary):

- `output.py` (134) — the output contract: silence / `-v` / the `--json`
  envelope, git-shaped errors, the tty progress spinner.
- `views.py` (182) — read claim state into plain dicts; verdict words; the ladder.
- `report.py` (491) — the terse/`-v` renderers for the action verbs.
- `statusview.py` (256) — the status / draft / tree / claims render family.
- `handlers.py` (194) — session setup, the traced run, producer preflight.
- `parser.py` (776) — the argv grammar, the verb map, man-page help, completion.
- `dispatch.py` (798) — `main` and the composite dispatches: the verb switch.
  This is the irreducible hub (the analog of the kernel's `crosscheck.py`); it
  is one flat dispatch over the verbs and does not divide further along a real
  boundary.

`cli.py` is now a **pure facade** re-exporting all seven, so `reticuli.cli.X`
stays stable (`__main__.main is cli.main` still holds, and `surface_check` drives
the assembled CLI through the facade, unchanged). The surface layer now generates
the `_cli` modules; `selfclaim`'s surface `adds` and the generated glob list them,
`reticuli.toml` declares them. `surface_check.py` is unchanged — it is ~95%
integration (it calls `cli.main` end to end), so like `kernel_check.py` it stays
the comprehensive top suite.

## Verification

`selfclaim` builds all thirteen layers fresh; `gate.py` passes; `ret verify .`
holds at `382f4b8c…`; `ret audit .` earns it cold in a seatbelt sandbox (1m3s);
`ruff` clean; `pytest` 93 passed (the known `test_streams` flake aside;
`test_selfcontained`'s structural-path whitelist gained `_cli/`, a free test
change).

## Stage 2 (same day, repo root → 3fe14432): the surface layer becomes six sub-claims

The surface layer split into **six sub-claims** so each piece regrows
independently — the economy the kernel chain already has:

- **measure** (assess + heldout + reuse) — `measure_check`.
- **cli-base** (output + views) — `base_check` (the envelope shape, the error
  voice, the claim-view keys, the ladder).
- **cli-render** (report + statusview) — `render_check` (the renderer surface is
  whole; exact output stays pinned by `surface_check`).
- **cli-handlers** (handlers) — `handlers_check` (init, and `run`'s exit-code
  passthrough).
- **cli-parser** (parser) — `parser_check` (the fourteen-verb grammar,
  `verbs()`==parser, retired verbs, completion carries the grammar).
- **surface** (dispatch + `cli.py` facade + `__main__`) — `surface_check`, the
  comprehensive top gate for the irreducible dispatch hub.

The repository is now **eighteen layers**. Grouping (`measure`, `cli-base`
= output+views, `cli-render` = report+statusview) keeps every regrown piece under
~800 lines — the size the kernel run showed is regrowable. `selfclaim` builds all
eighteen fresh; `gate.py` passes; `ret verify .` holds at `3fe14432…`; `ruff`
clean; `pytest` 93 (the known flake aside; `test_selfcontained` gained `_cli/`).

Note on speed: a *direct* `selfclaim`/`gate.py` build is slow on macOS because
`surface_check`'s ~50 subprocesses each spawn under seatbelt; under `ret audit`
(jailed) and on CI's Linux/bubblewrap they run unwrapped and fast. The roots are
identical either way.

Every oversized module in reticuli is now a small, independently checkable claim.
The payoff — regrowing the `_cli` sub-claims with a producer, now that each is
small — is the same experiment the kernel chain passed, and the natural next run.
