# Layered self-audit: the scaling win, on the repository itself

*2026-10-02. A generated-module addition (`src/reticuli/reuse.py`) plus
repo tooling (`scripts/selfaudit.py`). The repository root does not move
(`cfb038bf…`): `src/` is the equivalence class, and `scripts/selfaudit.py`
is not a pinned input (only `scripts/selfclaim.py` is, by explicit name).*

## The gap this closes

Last session shipped per-component reuse in the deep audit, but it bit
only on *composed* claims — and the repository audits as one monolithic
gate (`gate.py`, every criterion), so its own self-audit stayed
O(the whole claim): ~26 minutes, no matter how little changed. The
scaling idea was proven but could not yet help the one audit that hurt.

## What was built

Two pieces, split by where generality lives:

- **`reuse.layered_audit(layers, …)` — general, in `src`.** Given a layer
  decomposition (each layer a check over the file set it judges), it earns
  each layer by running its check against those bytes, staged in its own
  room, and reuses any layer already earned on this host (same check, same
  judged bytes → same content key → a hit, reported `reused` not
  `earned`). A failed layer stops the audit, as a failed gate stops the
  gate run. It reuses the module's existing fingerprint store
  (`_lookup_fp`/`_remember_fp`); it is opt-in (`reuse=False` earns all)
  and `self`-trust only, consistent with the rest of `reuse.py`.
- **`scripts/selfaudit.py` — reticuli-specific, repo tooling.** It turns
  `scripts/selfclaim.py`'s nineteen-layer decomposition into that spec and
  audits the live `src/` by it. It lives beside the chain declaration it
  reads, not inside the shipped tool — the same placement as `selfclaim`.

## Measured on the repository (one M1 machine)

    cold (nothing cached):        19/19 earned     17.0 s
    warm (unchanged):             19/19 reused      0.0 s
    touch cli.py (top layer):     18/19 reused, 1 earned   2.6 s
    touch _kernel/core.py (base): 0/19 reused, 19 earned   16.9 s

O(the frontier), correct direction: a change at the top re-earns one
layer; a change at the foundation, which every layer ships, re-earns
all; an unchanged tree is a handful of cache hits. The repository's own
self-audit is now incremental.

## Why it is safe without a root move

`layered_audit` is an additive function; nothing else in `reuse.py`
changed, so its pinned round-trip (`measure_check`) holds. The default
`audit`/`audit_deep` paths are untouched. `scripts/selfaudit.py` is new
and unpinned, and `gate.py` globs only `criteria/`, so it never runs in
the gate. Confirmed: root recomputes unmoved, `measure_check` passes, the
default audit path is unchanged, and the full gate re-earns `REPO_OK`.

## The honest limits

This earns each layer by running its check against staged bytes — the
same plain run `gate.py` gives each criterion — not by sealing a chain of
sub-claims and auditing those through the kernel's sandbox. It is
faithful to how the repository is actually checked (gate.py runs criteria
as plain subprocesses; the sandbox wraps the whole gate once), but it is
not the kernel's per-claim sandboxed audit. The fully principled version —
compose the repository as the layered chain so the shipped
`audit_deep` + per-component reuse applies directly — is a transition
(it changes how the repo seals), staged in
`research/proposals/verdict-cache-in-audit.md`. And trust is still
`self`; the shared, cross-signer cache remains the next increment.
