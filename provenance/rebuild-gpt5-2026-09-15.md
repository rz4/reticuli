# The cross-vendor rebuild (GPT-5) — round 1 landed, round 2 stopped

The second blind rebuild of the kernel, cross-vendor (`gpt-5` via an OpenAI
gateway, `tools/producer_openai.py`, 120-turn agentic loop), in a room
holding a byte-identical dry copy of the seed claim.

## Round 1: same root, different hands

- **Pass in its environment.** Gate earned in 20.1 min; re-earned
  independently by the orchestrator from a deleted-verdict state.
- **`reticuli/kernel.py`: 833 lines** (Opus: 1,451; v1: ~900). Three
  implementations, three shapes.
- **One digest across two vendors**: the room's root computed to
  `d64cc301082f420f4541150618d8774c0ea6c1fc7015b15ce7fd001343ccb405` —
  identical to the seed's. M3 sealed by the GPT-5 kernel's own `seal()`.
- Ledger: 1,036,037 tokens, $5.83 (priced 1.25/10 usd/Mtok), started
  2026-09-15T17:17:57Z, ended 17:38:05Z.
- New spec-width finding: the check never pins `seal()`'s return value
  (Opus returns the manifest; GPT-5 returns `None`; both conform).

## The crosscheck catches an environment-relative divergence

`kernel.crosscheck(M1=seed, M2=byte copy, M3=gpt-5 room)`, run by the
Opus-regrown kernel under an inherited jail (the orchestrating shell is
itself sandboxed — declared via `RETICULI_JAILED`, the exact case the
execution contract defines):

- `equivalence: true` — three rooms, one root.
- `reuse: true` — M1/M2 build digests identical
  (`8dc2b7919878…`), M3's different (`907008983007…`): a byte copy and an
  independent implementation, exactly as designed.
- **`satisfied: false`** — M1 and M2 audits earned; **M3's audit failed**
  in the inherited-jail environment. `record_proof` correctly declined.

Diagnosis (check lines 935–952): with no functional sandbox, the contract
requires an escaping gate to RUN — recorded, not hidden. GPT-5's kernel
statically refuses escaping redirects in every environment, so it passed in
its birth room (real seatbelt → the refusing branch) and fails where the
jail is inherited (the else branch). The Opus kernel normalizes
`RETICULI_JAILED` to backend `inherited` and conforms in both environments
(verified bare and jailed).

The lesson, plainly: **one digest does not mean one behavior in every
environment.** A gate verdict is environment-relative; the composed audit
exists precisely to re-earn verdicts in environments the birth run never
exercised. It worked.

## Round 2: stopped by hand

Round 2 relaunched the producer in the same room with `RETICULI_JAILED=1`
so its iterations would exercise the failed branch. It was **stopped
manually mid-iteration** (~27 min in, no usage report written — OpenAI-side
spend unrecorded). State at stop: the room's kernel was mid-edit and
conforms in **neither** environment; round 1's passing bytes were
overwritten and the audit's temp copies were already cleaned, so they are
**unrecoverable** — the build digest `907008983007…` remains their only
fingerprint. The root is unaffected (implementation bytes never enter it).

## Standing

- The cross-vendor **root agreement stands**: it was computed, re-verified,
  and does not depend on the lost bytes.
- The cross-vendor **crosscheck does not stand**: no machine currently
  holds a conformant GPT-5 kernel. Options recorded, none taken: resume
  round 2; accept round 1 as an environment-scoped result; or leave
  cross-vendor open.
- Cost note: vendor token meters are not comparable here (a resend-heavy
  chat loop vs. a cached agentic harness), so the crosscheck's cost
  envelope was left unmeasured — reported, not faked.
