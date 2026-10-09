# Revision — a claim composed by pack must audit deep

*2026-10-08. Keyholder-signed, from the r14 claude succession. A new
criterion in the authoring layer; a root move. Verified to bite r14 and
pass the shipped implementation before landing.*

    old root  0482adb5d2ef8a1dcd77bbdce1a2b8258125c286c42bed3fc1fe443438950f6d
    new root  2d10271449f3693a6379c3e031f5601e3aa485f991193a4cba15d1bf3a805975

    authoring moves alone; nineteen layers hold.

## What moved and why

r14 (claude) grew all twenty-one layers blind — a foreign-family first
— then failed the identity deep audit: its regrown `_audit_deep` read
`link["input"]` on a component record its own regrown `pack` had sealed
with only `{component, root}`. The two halves of claude's component
contract disagreed. The boundary never caught it because
`exchange_check` deep-audits only records it HAND-AUTHORS as rich
(`{input, component, output, root}`) — it never builds a composed claim
through `pack(component=…)`, so the pack half of the contract was
unexercised. The same seam species as r10 (input globs), r12 (room
recipe form), r13 (nested staging): the unexercised half of a symmetric
pair.

`authoring_check` now builds a composed claim via `pack(component={name,
claim, outputs})` and asserts it audits deep, binding pack's write to
`registry.audit_deep`'s read. It is phrased as the ROUND TRIP, not a
record layout: a conforming kernel may carry any fields in a component
record, as long as the code that writes them and the code that reads
them agree. The fixture lives with `pack` because it is pack's contract
— pack enters at the authoring layer; `registry`/`audit_deep` sits one
layer below. So the AUTHORING layer root moves alone (9594d8cd →
b6bfe31d); exchange and everything else hold, a layer's root covering
its own criterion and not its component's.

## Verified before landing

- Shipped implementation: `pack(component=…)` seals `{component, input,
  output, root}` and `audit_deep` returns ok — the fixture PASSES
  (standalone `authoring_check`: authoring-ok).
- r14 regrown modules: `pack(component=…)` seals `{component, root}` and
  `audit_deep` raises `KeyError: 'input'` — the fixture BITES.
- New root re-earns the cold gate (repo-ok) and the deep audit
  (`ret audit .` ok); `ret verify` clean.

## Consequence for the closure count

A boundary change: by the ratchet rule it RESETS the qualifying count.
It is the first STEERING pin earned for the foreign family — unlike
r13's deep-audit seam, accepted as caught by self_check because its
fixture could not be cleanly encoded. This one encodes in one
assertion. The next claude draw now has the signal pack's record must
survive its own deep audit.
