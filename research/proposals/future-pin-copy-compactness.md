# Future pin — reproduction stays disk-compact

*Staged 2026-10-08 as a FORWARD item, not for immediate signature.
Keyholder-raised after reviewing the compact-dependencies patch: it
would be useful to pin the compactness so every conforming
reproduction stays disk-performant, not just this implementation.
Depends on that patch landing first.*

## The property worth pinning

Copying or pulling a claim with k shared ancestors produces O(k)
physical copies of each dependency — ideally exactly one — never
O(k^2) or exponential. Naive recursive copytree follows the directory
symlinks a deep chain uses to carry its ancestors and unfolds the
shared closure into a tree; the compact-dependencies patch flattens it
to one copy per dependency. At the scale the compose-as-chain / corpus
/ external-system directions imply, the unfolding is not "slow", it is
"not practically regenerable" — which is the regenerability promise
itself.

## Why this is a GOOD pin candidate (unlike speed)

The project deliberately leaves speed out of the root beyond the
declared gate window, because pinning speed fairly across hosts is an
open hard problem: time is host-dependent. Disk duplication is NOT —
it is a property of the copy ALGORITHM, identical on every machine. So
the fairness objection that keeps speed unpinned does not apply.
Precedent exists for pinning a resource bound when it is load-bearing
(the declared gate_timeout); this is the disk axis of the same idea,
and it is cleaner to pin than the time axis.

## The design constraint — pin the bound, NOT the layout

The wrong pin asserts "dependencies live under `deps/<root>`". That
pins one implementation's presentation, the exact mistake the format-4
"substance not presentation" and the room-recipe corrections were made
to undo. A conforming kernel (a regrown generation, a foreign family)
must be free to arrange bytes its own way.

The right pin asserts the observable BOUND: after a copy/pull of a
chain with shared ancestors, each dependency's bytes appear at most
O(1) (target: exactly one) physical time, and the result still
verifies and audits deep and survives removal of the source. The
compact-dependencies patch's test (tests/test_component_copy.py)
already measures precisely this (one impl.py per layer); the criterion
is that test promoted from tests/ to exchange_check, phrased as a
bound rather than an exact layout.

## Costs, stated

- It is a criteria edit in the exchange layer — a root move, signature
  gate.
- It RAISES the exchange layer's regrowth bar: every future regrown
  kernel must produce a compact copy, not merely a correct one. Each
  pin is one more obligation a blind producer must hit; worth it only
  once deep chains are routine enough that the blowup actually bites.

## Trigger — when, not now

Pin this when deep/shared chains become routine in practice — the
compose-repo-as-chain work, a real corpus, or the first external
system (jq/Lua/SQLite) whose reconstruction nests claims deeply.
Pinning now would be speculative: the self-claim chain is 20 layers,
copied rarely, and the compact-dependencies patch (in tests/) already
keeps THIS implementation compact. Promote to a criterion when a
second conforming implementation is observed unfolding a chain that
matters — the same discovery-driven trigger every other pin followed.

## Dependency

Blocked on the compact-dependencies patch landing (its copy_claim is
the compact implementation this would pin the property of). Reconcile
one inconsistency first: copy_claim keys deps by root, transfer.export
keys them by name — harmless to resolution (content-addressed) but the
compactness pin should not bless two keyings; pick one (root, for the
collision-avoidance the patch cites) across both paths.

## 2026-10-09 measurements — the property is wild in the corpus

The compactness probe ran every realization's own `pull` over a 7-layer
shared-ancestor chain (research/harness/corpus/compact_probe scripts):

    gen0 (with copy_claim)   8 copies   COMPACT, closure travels
    r9, r11, r18 (codex)     1 copy     SHALLOW — the closure does not
    r15, r17 (claude)        1 copy     travel; the pulled claim cannot
                                        stand alone if the source goes
    r16 (claude)            64 copies   UNFOLDS (2^6) — the blowup is
                                        real in the wild, 1 of 7
    r14 (claude)            DNF         (probe harness mismatch)

So the closure-travel contract is boundary-silent and the observed
behavior spans three regimes. The pin now needs a DESIGN decision before
a fixture: what must `pull` carry — the full closure compactly (gen0's
copy_claim semantics: the pulled claim stands alone, each dependency
once), or is shallow legal with resolution deferred to the workspace?
The keyholder's earlier framing ("reproduction stays disk-performant")
implies closure-travels-compactly. Staged for the next signature window;
not landed in the 2026-10-09 batch because the semantics choice is the
keyholder's.

## Status (final)

SIGNED ("pin these as well") and LANDED 2026-10-09 in the endorsement
batch, root c48fbf52 -> 57da3b61, with the design decision resolved:
closure-travels-compactly is pull's contract. The fixture pins the
BOUND (stands alone + O(1) copies per dependency), never the layout.
Provenance: revision-2026-10-09-the-endorsement-batch.md.
