# r27 predictions: the first MAG lineage, free tier (gemma)

2026-10-15, written before the run. Root frozen at
`3302eb8a` (the layer-local audit_deep + canonical build digest root, signed
2026-10-15). Lineage: `gemma` = `gemma-4-thinking@cborg` through the DOE
Model Access Gateway, price $0/$0 — this run exists to shake out the MAG
plumbing at zero dollars and to place the first point on the capability
floor, not to qualify a member.

The pipeline is new in exactly one place: the producer is the repo's own
agentic `producers/openai.py`, pointed at the gateway with the credential
handed over the kernel's environment scrub. Everything after the producer
(rooms, threading, gates) is the same machinery r25/r26 used.

- **P1 (plumbing).** The producer completes tool-use turns against MAG with
  no protocol failure: files read, files written, the gate run. Any failure
  is a producer capability failure, not an authentication or API-shape
  failure.
- **P2 (capability floor).** gemma-4-thinking does NOT grow all 21 layers.
  Expected halt: at or before the identity/record band (layers 3–8), where
  the checks demand exact byte-level serializations re-derived from the
  check text alone. Both qualifying families to date (gpt-6-sol, sonnet)
  are frontier-tier; gemma is not.
- **P3 (cost envelope).** The usage ledger records real token counts and
  usd 0.0 for every attempt — the envelope's first gateway-metered entries.
- **P4 (honest halts).** Each failed layer halts as "attempt-failed" ×3 then
  "halted" in the lineage ledger, never as a quota stop and never as a
  silent pass.

Falsification that would matter most: P2 wrong — a free 245K-context model
growing the whole tree would say the spec carries more of the information
than the frontier-only evidence suggested, and would make the closure-count
economics trivial.
