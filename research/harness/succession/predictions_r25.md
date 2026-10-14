# Predictions for succession r25 — trial 1 at the obligations root

*2026-10-14. Root `1d9ab7ed714d…`, FROZEN. Lineage: codex. The claude
subscription resets at 19:00, so the codex leg goes first and the claude
leg (r26) follows.*

**The count resets here, and that is the rule rather than a setback.**
r23, r24 and g2 all qualified at `900b6594`. Three root moves have
intervened today — the companion-boundary guard (`0c489183`), the
validation-precondition clause (`13c8bbf0`), and the five batched
obligations (`1d9ab7ed`) — so by condition 7 the k = 3 count returns to
zero. The count only grows while the boundary has stopped learning, and
the boundary learned five times today.

Seven genes are new since the last trial, and they are not equally
visible to a producer:

- **boundary_check** constrains the recipe's input list, not any module.
  Invisible to a rebuild.
- **glob equals pinned** likewise constrains the recipe against the
  criteria directory. Invisible: a flat layer room carries one check and
  its own recipe pins it.
- **validation is a precondition** is the one with a track record of
  biting. At the old root, two of the four members canonicalized a
  document that was not a JSON object and two refused it; the clause
  settled it, so a regrown `attest.py` whose `record_canonical` is a bare
  `json.dumps` now fails its own layer.
- **numbers verbatim** should be free: `json.dumps` already passes them
  through, so the natural implementation satisfies it.
- **cost never counts a boolean** and **the band is closed** are narrow
  and local, in `run.py`. A producer writing the obvious `isinstance`
  check and the obvious `<=` satisfies both without trying.
- **a verdict ignores the granted environment** has never been exercised
  by a producer. `_now` must use `gmtime`, and nothing in `_kernel` may
  import `locale`. A regrown `core.py` reaching for `localtime` is the
  plausible new failure, and it would be the first time this gene is
  tested by anything other than the authored tree.

- **P1.** 21/21 grow; quota pauses absorbed and resumed.
- **P2.** The validation-precondition gene steers at the attest layer:
  either codex writes a validating canonicalizer and the layer earns, or
  it is refused there, named, rather than surfacing later as an identity
  mismatch.
- **P3.** The environment gene is the dark horse. If any layer refuses on
  a `localtime` or a `locale` import, that is a gene doing its job on its
  first producer contact, and it is the finding of this run.
- **P4.** All conditions re-earn inside the sealed gate; the trial seals
  as `trial-r25-codex` — **count 1 of 3** at `1d9ab7ed`, one family
  banked, claude's leg outstanding.
- **P5.** Zero new seams, asserted with r20's humility: the last two
  times this was predicted flatly, the run found one.

**What would falsify the batching argument.** The five obligations were
signed together specifically so the population is retired once. If this
trial refuses on one of them, batching cost nothing — the refusal would
have happened at whichever signature introduced it. If it refuses on two
or more that interact, the batch hid an interaction a staged sequence
would have isolated, and that is an argument against batching worth
recording.
