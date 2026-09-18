# Six-strangers audit — 2026-09-18

*Research record — what was tried and what it showed. Not normative.*

A read-only audit of the repository from six newcomer perspectives, per the
"Next Pass" plan (§11). Each persona tried to accomplish that stranger's actual
goal against the tree and flagged where the operational path failed — and, as
the acid test, whether answering an operational question forced them into
`research/`.

## Method

Six independent agents, one per persona, each read the relevant docs/spec/code
and exercised the CLI (`PYTHONPATH=src python3 -m reticuli …`) without
installing, on commit `4e9e5d2`. No repository files were modified during the
audit.

## Headline result

All six returned **partial**: the tool works, the architecture is sound, but it
carried documentation and spec-label debt. The most important positive: the
**research/operational separation held**. No persona was forced into `research/`
to answer an operational question. The one apparent exception (future
maintainer) was the *spec contradicting the recipe*, not a research leak.

## Findings, by whether the fix moves the root

### Free (docs/src, no root move) — addressed in this pass

1. Quickstart's `pack` example was unrunnable (`ret pack myclaim …` parsed
   `myclaim` as the path). Fixed to `ret pack . --name myclaim …`.
2. Quickstart's recommended `pytest` gate sealed warm but failed `audit` cold
   (no pytest in the sandbox). Switched to a stdlib `unittest` gate + a
   self-contained-gate callout.
3. Docs showed `-v` output as if it were the default; bare commands are silent.
   Added `-v` to the block examples + a silence note.
4. Install path led with a git+https URL against a private repo, no fallback.
   Clone route made primary, with a `PYTHONPATH=src` no-install option.
5. `compatibility.md` said "the claim format is version 1", contradicting its
   own format-2/3 paragraphs. Reworded (maturity framing left untouched).
6. The `--json` `data` payload and `status` value set were undocumented. Added
   a `--json` payload section to `cli-style.md`.
7. `quarantine` (audit `--json`/ledger) vs `sandbox` (record) naming seam —
   documented (a rename is *not* free: `quarantine` is pinned vocabulary in
   `kernel_check.py`, `launcher_check.py`, `spec/kernel-api.md`).
8. `docs/` files carried no normative/informational tier marker. Added one to
   each; `threat-model.md` marked load-bearing.
9. `LICENSE` referenced a missing `REPLICATE.md`. Added the file (the protocol;
   the legal text is untouched, and stays under LBNL review).
10. The sharpest non-guarantees lived only in `threat-model.md`, filed under
    "using it". Promoted it into the README's normative doc-map.

Deferred free item: argparse errors and the `record` refusal bypass the
`ret: <verb>: <fact>` error contract (script author #4/#5) — minor `src`
polish, blast radius unchecked, left for a later pass.

### Identity-bearing (edits pinned `spec/*.md`, needs the transition ritual)

Batchable into one transition, anchored on the first:

- `spec/record.md:4-5` still says "Not yet pinned … not declared in
  `reticuli.toml`", but it **is** pinned (`reticuli.toml:59`, commit `92c51ef`).
  A maintainer would treat editing the record spec as ordinary when it is now
  identity-bearing. The one true correctness defect.
- The `crosscheck` accept threshold is not a single normative value (cost-band
  tolerance "v1 default 2.0" but implementation-defined across `[1.5, 4.0)`).
- `spec/verification.md:239-246` embeds unresolved open questions in the
  normative doc.
- `spec/layers.md:2-3` references an undefined "phase 4" (minor).
- Optional: promote the threat-model non-guarantees into `spec/verification.md`.

Held for a decision: the `Status: draft` markers on `spec/identity.md`,
`claim-format.md`, `verification.md` contradict the standing v2.0.0
compatibility promise. Fixing them is identity-bearing and overlaps the
version/maturity question the owner is resolving separately.

### Reserved (owner's acts / blocked)

- LICENSE terms (blocked on LBNL review).
- A signing policy doc, and the publish/re-download release steps (tied to the
  signing ceremony).

## What it means for Phase 3 (the capture engine)

The agent-developer lens empirically confirmed capture is **already
workspace-scoped**: independent processes across "sessions" all append to one
`.reticuli/draft.jsonl`, surviving session-end, new processes, and multiple
harnesses. So the workspace-not-session boundary (§1) is substantially built.
The real Phase 3 gaps are narrower than the "Next Pass" doc implied:

- only Claude Code is wired (`cli.py:196` rejects other harnesses);
- `ret run` and Bash capture command strings, not file effects — subprocess
  work is outside the boundary (the big one for "compute the closure");
- the honest-partial `pack` with a warnings block and the
  observed/declared/sealed/inferred/unobserved taxonomy (§3/§5) does not exist;
- durability/concurrency (§4) is real but simpler, since single-ledger append
  already works.
