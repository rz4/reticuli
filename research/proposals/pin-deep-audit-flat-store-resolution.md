# Proposal — the deep audit must resolve a flat (shared-store) chain

*Staged 2026-10-09, from the r15 claude succession. The sixth claude
seam, and the mirror image of r13. A candidate criteria edit (a root
move); staged for the keyholder, with the r13 precedent explicitly in
view — this one may, like r13, be left to self_check as the catch.*

## The finding

r15 (claude) grew all twenty-one layers and CLEARED the authoring layer
— the pack→audit_deep record round-trip pin from r14 steered correctly,
and that seam is gone. It then failed the identity full gate at
`self_check` (41 seconds, fast — not a 27-minute deep re-earn):

    assert deep["ok"]  →  AssertionError: the whole chain re-earns: None

`self_check` runs `registry.audit_deep(chain/surface)` with the regrown
r15 registry substituted. Reproduced faithfully (r15 modules staged into
a temp src, chain rebuilt, r15's audit_deep dumped):

    ok: False | layers walked: 2
      OK  cli-verbs   earned
      XX  cli-parser  unresolved

r15's `audit_deep` walks the chain by PHYSICAL RECURSION: it audits
`surface`'s component `cli-verbs`, then looks for `cli-verbs`'s own
component (`cli-parser`) under `surface/sealed/cli-verbs/.reticuli/
sealed/`. But the self-claim chain stages its components FLAT — all
eighteen layers sit directly under `surface/.reticuli/sealed/` (symlinks
into the shared store), resolved by ROOT, not by physical nesting. So
r15 finds `cli-verbs`, fails to find `cli-parser` nested beneath it,
calls it `unresolved`, and refuses after two layers.

Control: the SHIPPED `audit_deep` on the same flat chain returns
`ok=True` and walks all eighteen layers. It resolves each component by
root across the store (`chain()` + `resolve()`), so a flat or a nested
layout both work. The chain is valid; r15's resolver is the diverging
party. (The `verdict: None` in the error is cosmetic — r15's audit_deep
returns `{ok, layers}` with no `verdict` key; the load-bearing fact is
`ok=False`.)

## Why the boundary did not catch it

`exchange_check`'s deep-audit fixtures are built by physically nesting
each component under its parent (`copytree` into the parent's
`sealed/`), so recursion-by-nesting resolves them — r15 PASSED
exchange_check during the grow. Nothing in the criteria builds a chain
staged FLAT (shared store, resolved by root) and deep-audits it. The
resolution contract — *resolve a component by its root wherever it lives
in the store, nested or flat* — is the unexercised half.

## The mirror of r13

r13's seam was the same staging AXIS, the opposite half: r13's component
MATERIALIZATION did a bare copyfile with no makedirs and crashed on
NESTED outputs, where exchange_check's fixture was FLAT. r15's component
RESOLUTION recurses by nesting and fails on a FLAT chain, where
exchange_check's fixture is NESTED. Flat-fixture-missed-nested (r13) and
nested-fixture-missed-flat (r15): the staging contract has now been
bitten from both sides by two different claude draws. That is a strong
signal the nested/flat duality of the component store is a deep, two-
sided under-specification.

## What to pin — and the open question of whether to

The property: `audit_deep` must re-earn every layer of a chain whose
components are staged FLAT in a shared store and resolved by root, not
only one physically nested. The self-claim chain IS such a fixture, and
`self_check` ALREADY runs audit_deep on it — which is exactly what
caught r15. So, as with r13, this seam is ALREADY CAUGHT at the whole-
repo level; the question is whether to add a LOCALIZED fixture (an
exchange_check case that stages a composed claim flat — components in the
top's store by root, not nested — and asserts audit_deep re-earns it).

Unlike r13 (whose localized fixture could not be cleanly encoded —
construction artifacts tripped both implementations), a flat-staged
composed claim looks straightforward to build. But r13 taught that
encodability must be MEASURED, not assumed: before signing, construct
the fixture and verify it FAILS on the r15 tree and PASSES on the
shipped tree, the same discipline every landed pin followed.

## 2026-10-09 addendum — the seam is SYSTEMATIC and CROSS-FAMILY

r16 (claude, fresh draw) did not reproduce it, so it was provisionally
classified draw-specific. r18 (codex, at the two-pin root 71fd7559) then
FAILED identity on exactly this seam — the first codex refusal since r8,
ending a four-pass codex streak. r18's walker is independently written
and differently shaped (it copies each component to a temp room and
recurses into the COPY, where r15 recursed into the parent's nested
store) but makes the SAME assumption: a component's own components are
reachable from the component's claim. On the flat chain it walks 2 of 18
layers and reports `cli-parser: unresolved, missing declared component`
— byte-for-byte the r15 failure shape, reproduced faithfully (r18
modules staged into a temp src, chain rebuilt, walker dumped). Control
unchanged: the shipped audit_deep walks all 18 on the same chain.

Two families, two independent implementations, one unexercised contract
half. This is no longer draw noise; the boundary is genuinely silent
about flat-store resolution, and the silence now costs qualifying trials
in BOTH families. The r13 accept-as-caught precedent weakens here:
self_check does catch it, but at the price of a failed trial per draw —
and unlike r13, the fixture looks cleanly encodable (a composed claim
staged FLAT — components in the top store, resolved by root — that must
audit deep). Per the measure-before-pin rule: before signature, build
that fixture and verify it FAILS r15's and r18's walkers and PASSES the
shipped one.


## Status

SIGNED ("pin them") and LANDED 2026-10-09 in the batched exchange
move, root 71fd7559 -> c48fbf52, with pin-data-dependency-re-earn.
Encoded as the flat-only continuation of the transitivity fixture.
Provenance: revision-2026-10-09-batched-exchange-pins.md.
