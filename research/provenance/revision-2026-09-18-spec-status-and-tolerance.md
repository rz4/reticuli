# Revision: the pinned specs say they are pinned, and the tolerance is stated once

The repository claim moved on 2026-09-18, `3ad6e0cc…` → `c1f98059…`. The
change edits five pinned specification files so that what they say about their
own status matches what `reticuli.toml` already does with them, and so that the
cost-envelope tolerance is stated one consistent way. It is corrective, not a
hardening: no acceptance criterion changed, so no previously conforming
implementation can be made to fail.

An intermediate reseal (`826d8c2f…`, pushed before CI ran) put a Markdown link
to `docs/transitions.md` in the new status markers.
`tests/test_pinned_files_are_self_contained` correctly rejected it: a pinned
spec is materialised into a blind rebuild room, which carries no `docs/`, so the
link dangled. The lesson is that `gate.py` alone is not the whole check — this
invariant lives in `tests/`, which must also be run after editing a pinned file.
The link was removed (a pinned spec should not point at an unpinned doc anyway),
the specs resealed to `c1f98059…`, and the full test suite re-run. Both roots
are in the history; `c1f98059…` is the one that holds.

## What moved, and why the root moved with it

Every `spec/*.md` file is a pinned input (`reticuli.toml` `[claim].inputs`), so
editing any of them necessarily moves the root — which is exactly the property
the edits now state out loud.

- **Status markers.** `identity.md`, `claim-format.md`, `verification.md`,
  `record.md`, and `layers.md` each carried a "Status: draft" (or, for
  `layers.md`, "the v2 map for the port (phase 4)") header. They are not draft:
  editing one moves everyone's root. Each now reads "Status: normative. Pinned
  in `reticuli.toml`; changing this file is an identity-bearing transition."
  This resolves a contradiction the six-strangers audit found — the specs
  backing the standing v2.0.0 compatibility promise were self-labeled draft.
- **`record.md`'s falsehood.** Its header claimed "Not yet pinned — this file
  is not declared in `reticuli.toml`, so the repository's root is unchanged."
  It has been pinned since commit `92c51ef` (`reticuli.toml:59`). The false
  clause is removed; the pointer to its Decisions section is kept.
- **The tolerance, stated once.** `verification.md` gave the cost-envelope
  tolerance three ways: "v1 default: 2.0" in the crosscheck section, "anywhere
  in `[1.5, 4.0)`" in the implementation-defined list, and an unresolved open
  question. It now states it once — default 2.0 is normative, and a claim or
  verifier may set any value in `[1.5, 4.0)` — and the open-question checkbox is
  closed with that resolution. `kernel.py` already defaults `TOLERANCE = 2.0`,
  so no behavior changed; only the prose was made consistent.
- **The `layers.md` "phase 4"** reference to an undefined phase is dropped.

Two genuinely-unsettled items in `verification.md` (whether `crosscheck`
subsumes `audit --deep`; signature-namespace strings) were left standing under
their "Open questions" heading. Honestly naming what is not yet decided is a
feature of the spec, not debt to clear.

## Direction and blast radius

Corrective. The changes are to prose describing the boundary, not to any
acceptance criterion; the tolerance edit matches the code's existing default.
The going rate for a rebuild does not rise, and the equivalence class is
unchanged in substance.

The six layer roots did not move: the edits touch `spec/` only, which the
layer claims do not share. `python3 gate.py` re-earned `repo-ok` at the new
root with every suite green, `self_check.py` included — the proof the layer
roots held — and `ret audit .` returned `earned` at `c1f98059…`.

## What this click is, and is not

An internal ratchet click, recorded as a resealed old→new pair with the gate
re-earned on this machine — the accept bar for an internal correction. It is
deliberately **not** cryptographically signed: an attestation is a keyholder's
act, reserved for the completion ceremony and for external transitions once the
call is open. No proof is claimed across the moved root beyond this local
re-earn. The room export (`room/reticuli`) tracks the new root.
