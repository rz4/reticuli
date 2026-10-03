# The attested shared cache: signed and quorum trust

*2026-10-03. A generated-module change (`src/reticuli/reuse.py`,
`_cli/parser.py`, `_cli/verbs.py`) plus repo tooling
(`scripts/selfaudit.py`). The repository root does not move
(`cfb038bf…`): `src/` is the equivalence class.*

## What changed

Reuse trusted only `self` — this host's own earns. Trusting another
party's earn is a different proposition: a bare "it passed, signed S" is
forgeable, which is the one testimony this system refuses. So a shared
earn is now an **ssh-signed statement binding the exact fingerprint**, and
the new policies count only signers an allowed-signers file verifies:

- `reuse.attest_earn(fp, verdict, key, signer)` publishes a cold earn to
  the shared cache (`shared_dir()`), ssh-signed under a reuse-only
  namespace (distinct from attestation and the signing ceremony).
- `reuse._verified_earners(fp, allowed)` returns only the signers whose
  statement for *this* fingerprint verifies — an unsigned or
  fingerprint-mismatched entry is ignored, never counted.
- `reuse.trusted(fp, policy, allowed)` decides a hit: `self` (local earn),
  `signed:<id>` (that verified signer), `quorum:<k>` (k verified earners).
- `reusing_auditor` and `layered_audit` take the policy, echo it in the
  verdict, and publish a signed earn on a cold run when a key is
  configured. `ret audit --reuse --trust <policy>` and
  `scripts/selfaudit.py --trust` expose it; `self` is the default.

## Demonstrated honestly, with real keys

Two throwaway ed25519 keys, real signatures, real verification:

    cold:                          quorum:2 → miss
    alice signs:                   signed:alice → hit; quorum:2 → still miss (1)
    bob signs:                     quorum:2 → hit (2 verified)
    forged unsigned "carol":       ignored; quorum:3 → miss

And the distributed win, on the repository's own self-audit: a CI signer
earns all nineteen layers cold (17s) and publishes signed earns; a **fresh
host with an empty local cache** then trusts them under
`signed:ci@reticuli` and audits in **0.1s** — `quorum:2` correctly
re-earns, since only one signer exists.

## Why it is safe without a root move

Additive: the existing `self` path (single-file store, pinned round-trip
in `measure_check`) is untouched, and `self` stays the default. The ssh
helpers are local to `reuse.py` (no new cross-layer import). `--trust` is
a new optional argument. Confirmed: `parser_check`, `verbs_check`,
`measure_check`, `surface_check`, and the full gate pass; the root
recomputes unmoved.

## The honest limit

Trust rests on an allowed-signers file the operator curates — reuse
inherits the same key-trust model as `ret sign`. The cache accelerates;
it never decides correctness: a miss is still earned cold, from nothing,
and a hit is reported `reused` with its policy, never as a fresh earn.
Pinning the behaviour in criteria (so it is a promise, not a convenience)
remains a staged transition.
