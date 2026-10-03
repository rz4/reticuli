# Revision — click F lands: the gate enforces its own closure

*2026-10-03. An identity-bearing transition, keyholder-signed. One bundled
click: the closure criterion is promoted into `criteria/`, and
`kernel_check` pins the three names its first run caught.*

    old root  cfb038bf08717a889c1a547c525bab88904f9459756e94fa34f67fac0b4032df
    new root  03edfbb733adf44b1a840cbfc6a99736f2deea7fcccbc4718f96bf28e9726728

## Why the root moved

The succession found the species: pinned machinery consuming names from
the generated package that no criterion exercised, so a conforming
implementation could fail the gate's own scripts. Clicks A and J fixed the
two instances it exposed. This click lands the general repair:

**`criteria/closure_check.py`** — for every name and call keyword a pinned
file consumes from the generated package, the check of the layer owning
that module must exercise the same. Static, seconds, every boundary.
Validated against history before promotion: at the pre-click-A root it
flags exactly the pack seam the succession found by regrowing the whole
tool; at the pre-transition root it flags exactly the three pins below and
nothing else; after them it passes. The gate now enforces its own closure
— the species, not the instance, is dead: any future pinned file leaning
on unexercised surface fails the gate the moment it is committed.

**Three pins in `kernel_check`** (the closure check's first catches):
pinned criteria consume `kernel.MANIFEST` (exchange_check, self_check),
`kernel.ledger` (exchange_check), and `kernel.RECIPE` (launcher_check),
none exercised until now. Every regrown kernel so far merely happened to
carry those names — the prior saved us, the reliance this project refuses.
kernel_check now pins the consumed contracts: MANIFEST locates the sealed
manifest, a recipe written at RECIPE is the claim's recipe, ledger appends
an event the ledger reads back. (The ledger probe runs on a side fixture:
an existing pin relies on the primary fixture staying ledgerless — caught
by the suite itself during this transition, which is the system working.)

## What moved

`criteria/closure_check.py` is a new pinned input (`reticuli.toml` names
it), and `kernel_check.py` changed — so the crosscheck layer root moved
(`ea7f1e6b… → 9948833c…`, every other layer held), the self_check lockfile
records it, and the repository root moved with them. Validated before the reseal: the closure criterion passes on the
living boundary (30 pinned consumers, 36 owned modules), the kernel chain
passes all eight suites (`kernel_parity`), the full gate re-earns
`REPO_OK` cold at the new root, and the room is refreshed.

## What this closes, and what it does not

Closed: the entire class of silent seam drift between the pinned surface
and the layer checks — hereditary, because the criterion itself is pinned
and will judge every future boundary, including regrown ones. Not closed:
generated-to-generated seams (proposal specimen D — original modules on
regrown ancestry), module ownership outside the layer chain (producers/,
reference.py), and the remaining staged clicks of the closure proposal.
