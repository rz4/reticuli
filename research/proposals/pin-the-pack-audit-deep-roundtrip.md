# Proposal — a composed claim built by pack must audit deep

*Staged 2026-10-08, from r14's deep-audit refusal. A criteria edit in
the exchange layer, so a root move and the signature gate. Measured to
bite r14 and pass the shipped implementation before staging; the
explicit end-to-end reproduction against the r14 tree is the
pre-signature confirmation below.*

## The finding

r14 (claude), re-run at the hardened-probe root `0482adb5`, grew all
twenty-one layers blind — the first time the foreign family cleared the
whole chain. It then FAILED the identity full gate (`ok=False`, a
merit refusal, judge ran clean to completion). The failure is in the
deep recursive audit, not the shallow criteria: the shallow gate prints
`REPO_OK`, then the deep audit crashes.

The exact crash, from the regrown `registry.py`:

    File ".../work/src/reticuli/registry.py", line 258, in _audit_deep
        input_name = link["input"]
    KeyError: 'input'

The regrown `_audit_deep` walks `manifest["components"]` and reads
`link["input"]` and `link["output"]` off every record. But the regrown
`pack.py` seals component records with only two keys:

    components = [{"component": comp_name, "root": comp_root}]   # regrown pack.py:113

claude's own component-record contract is self-inconsistent: its `pack`
WRITES two keys, its `_audit_deep` READS four. The deep audit crashes
the instant it walks a layer composed via `pack(component=…)`.

The shipped implementation is consistent — the original `pack`, given
the same `component={name, claim, outputs}`, resolves and seals the
rich record `{component, input, output, root}`, and `audit_deep` reads
only `component`/`root` from the chain (reconstructing the supplied
bytes from each component's recipe), so it would survive a lean record
too. Measured both ways:

- Original `pack(component=…)` → record keys `{component, input,
  output, root}`; `audit_deep` ok=True (local construction, this repo).
- Regrown `pack(component=…)` → record keys `{component, root}`;
  regrown `_audit_deep` → `KeyError: 'input'` (the r14 traceback).

## Why the boundary did not catch it

`exchange_check` exercises the deep audit only on component records it
HAND-AUTHORS as rich — `registry.seal_with(appc, components=[{"input":
…, "component": …, "output": …, "root": …}])` then `audit_deep`
(criteria/exchange_check.py:442, :503, :522). It never builds the
composed claim through `pack(component=…)`, so it never checks that
`pack` PRODUCES records `audit_deep` can consume. The `pack →
audit_deep` round-trip is the unexercised half of a symmetric contract
— the same seam species as every prior claude refusal (r10 input
globs, r12 room recipe form, r13 nested staging). The producer coded
`_audit_deep` to the record shape the fixture always handed it.

## What to pin

One fixture, phrased as the ROUND TRIP, not the record layout: a claim
composed via `pack(component={name, claim, outputs})` must `audit_deep`
successfully. This binds pack's write to audit_deep's read without
pinning either's byte-level shape — a conforming kernel is free to
carry whatever fields it likes in a component record, as long as the
code that writes them and the code that reads them agree. It belongs in
exchange_check beside the existing deep-audit fixtures, which keep their
hand-authored-record coverage; this adds the missing producer path.

Sketch (criteria/exchange_check.py, a new case):

    base = pack(... "base" ...)                       # a leaf claim
    app  = pack(..., component={"name":"base","claim":base,
                                "outputs":["lib.py"]})  # composed via pack
    assert registry.audit_deep(app)["ok"], \
        "a claim composed by pack must audit deep: pack's component " \
        "record and audit_deep's reader are one contract"

## Costs, stated

- A criteria edit in the exchange layer — a root move, signature gate.
- It raises the exchange layer's regrowth bar: every future regrown
  kernel must make its pack and its audit_deep agree on the component
  record, not merely pass the hand-authored-record fixtures. One more
  obligation a blind producer must hit — and the precise one that the
  binding family (claude) has now missed once, cleanly.

## Pre-signature confirmation (the measure-before-pin step)

Verified so far by source + the r14 traceback + a local original-side
construction. Before signing, run the candidate fixture end to end
against the r14 tree substituted (it must FAIL there) and against the
shipped tree (it must PASS) — the same discipline the producer-probe
fix followed. Offered, not yet run, to avoid a second heavy audit
without the keyholder's call.

## Status

STAGED for the keyholder. Not landed. If adopted, it is a boundary
change: by the ratchet rule it resets the qualifying count, and it is
the first STEERING pin earned for the foreign family — unlike r13's
deep-audit seam, which was accepted as caught by self_check because its
fixture could not be cleanly encoded. This one can: it is a clean
contract round-trip.
