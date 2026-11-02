# The audit learns ownership: R33 becomes a warning lane

2026-11-02. The first item of the APEIRON campaign's feedback
(`research/proposals/2026-11-02-apeiron-campaign-feedback.md`), landed
audit-side exactly as staged: a warning class, no identity cost, nothing
refuses.

## What landed

`kernel.ownership(claimdir)` — pinned criteria whose imports reach a module
the claim is *supplied* (`from = "<component>"`) rather than owns. The gate
validates the producer's copy of a supplied file and assembly discards that
copy for the owning room's, so a criterion asserting a property of a supplied
module constrains bytes that never ship. That was the campaign's single
largest failure class: 11 of 50 upstream-test failures (ledger R33).

Every `audit` now carries the lane (`ownership` in the result, on all three
return paths, environment-refusals included), the CLI prints each crossing to
stderr in pack's warning idiom, the json envelope carries it under `data`,
and a `--reuse`d verdict still recomputes it — the receipt cached gates, not
this advisory. The lane never touches `ok`.

## Measured against the campaign's own claim set

The prototype (`claims/scripts/ownership_audit.py`, regex over `test_*.py`)
reports **28** criterion files. The port reports **34** files, 70 crossings,
and the delta decomposes exactly:

- **−2 regex false positives.** `model_harness/test_import_surface.py` and
  `updaters/test_import_surface.py` match the prototype's regex only inside a
  quoted ImportError traceback in a docstring and string literals like
  `node.module.startswith("apeiron.")`. The port parses with `ast`, which
  reads imports, not prose.
- **+8 genuine reaches** the prototype's `test_*` filename filter skipped:
  six `conftest.py` and two other pinned criterion files that import supplied
  modules. A fixture file can assert too; the lane reads every pinned `.py`
  input.

The port also catches `from pkg import mod` reaching a supplied `pkg/mod.py`
— the imported name as a module, not an attribute — which the prototype's
regex could not express.

## What deliberately did not land

- **The seal-side stage** (a `constrains = [...]` declaration validated at
  seal) is format-bearing — it moves roots — and stays staged for the
  keyholder, batched with whatever format bump carries items 2 and 4.
- **Items 2–4** of the handoff (the assembly claim, declared-shape
  divergence, the carried class) are design work and format changes; the
  handoff's own ordering holds.
- The handoff doc and `compare_v2.py` are committed verbatim as received.
  One correction to its provenance belongs here rather than in it: the
  campaign workspace is not a sibling of this repository — it lives at
  `LBNL/ModCon/prototype/repos/apeiron_reticuli` on the machine that ran the
  campaign.

## The line it respects

`src/` is generated and `tests/` is unpinned, so the primary root
(f2d49443…) does not move; this is the same channel the first campaign's
R-findings used (`tests/test_campaign_feedback.py`). Import-reach
over-approximates "constrains" — importing a supplied `Config` to build a
fixture constrains nothing — which is why this is a warning and the refusable
form waits for the keyholder's seal-side declaration.
