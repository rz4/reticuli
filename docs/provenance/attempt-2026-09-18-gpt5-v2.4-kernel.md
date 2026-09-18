# Open-call attempt: gpt-5 on the v2.4 kernel — did not land

**2026-09-18.** The first *live, paid* rebuild of the v2.4 kernel claim
(`fac55f89…`) with the shipped `openai` producer. It did not earn the
proof. Recorded here because a failed attempt is evidence: its ledger,
without its bytes, tells the going rate and locates the limit.

## The attempt

- **Producer:** `ret rebuild examples/kernel --producer openai:gpt-5`, the
  shipped agentic loop, run through the vendor proxy.
- **Turn cap:** 40 (the default `RETICULI_AGENT_TURNS`).
- **Room:** the kernel's blind room — recipe, the ~1,900-line v2.4 suite,
  the pinned verdict, no implementation.

## The result

The agent finished and the gate never wrote `KERNEL_OK`:

    producer_openai: agent finished but the gate never produced KERNEL_OK
    (turn cap or gate never passed)

- **Cost:** one producer session, **4,334,578 tokens, $24.38** — under the
  claim's declared `usd = 40` envelope, but with no proof to show for it.
- **Progress:** it wrote a **1,076-line** `reticuli/kernel.py` (the
  reference is 2,558; a blind Claude build earlier the same day was 1,190).
  Run against the suite, that partial kernel fails at
  **`an escaping gate must refuse`** — a confinement edge case deep in the
  suite. Identity, sealing, verification, audit, and records were working;
  it ran out of turns before finishing the confinement rules.

The partial implementation's bytes are **not shipped** — only this ledger,
per the open call's own rule.

## Diagnosis: a limit of the producer within budget, not a spec hole

The gate did exactly its job: it refused an incomplete kernel. Nothing
about the acceptance boundary changes — there is no counterexample here,
no criterion to add. What this measures is the *going rate*:

- This was **turn-bound, not stuck.** The failure is late in the suite and
  the implementation is nearly complete; more turns would likely have
  closed the gap.
- The harness matters. The shipped producer is a **bounded 40-turn API
  loop** — the honest thing a stranger runs. A blind Claude subagent with
  open-ended iteration landed the same v2.4 kernel earlier the same day;
  gpt-5 landed the *easier* v2.1–v2.3 kernels historically for $3–$26. The
  v2.4 suite (format 3 and the declared cost band added surface) plus a
  40-turn ceiling put a passing kernel just out of reach for ~$24.

## What it says for the open call

The v2.4 kernel is regrowable — proven blind the same day — but its going
rate for a shipped 40-turn gpt-5 producer exceeds one $24 session. The
proof stays open. The likely lever to land it is a higher turn cap
(`RETICULI_AGENT_TURNS`); the point of opening the call is to let outside
compute carry that cost instead of the keyholder's.
