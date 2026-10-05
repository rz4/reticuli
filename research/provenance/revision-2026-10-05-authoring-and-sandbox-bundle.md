# Revision — the authoring-and-sandbox bundle

*2026-10-05. Keyholder-signed ("I sign off on both, land them as one
bundle"), from the first cross-judging run's two staged proposals. The
cycle from finding to signed pin: same day.*

    old root  3e7dc82769cb3caa43cc7fa53d9935179d9315c32a6707d6215b3a19d69f4ed5
    new root  79bce6fb4ca2f69e23e66c5c14174c7f2a7f7ca1c9ff2c6bfa90cce80157f4ad

    authoring  0ce31932…  ->  c290405a…   (the format-3 default, pinned;
                                           second draft — see below)
    build      117d71f1…  ->  852c086b…   (the sandbox signal, pinned)
    the other eighteen layers hold, reference included. (An intermediate
    reseal, 7697861c…, carried the first authoring draft for the minutes
    it took the gate to refuse it.)

## Click one — a fresh claim is born at format 3

Cross-judging found three conforming kernels minting two names for one
authored claim: pack's own default guidance line sat inside the
format-1 root, and no criterion pins guidance text — by doctrine none
can, since guidance cannot reject a realization. Now `pack` defaults
new claims to format 3, where guidance is outside identity.

`authoring_check` exercises the whole decision: a default pack writes
`format = 3`; rewriting a step's guidance and resealing leaves the
root unchanged (the point of the default); and `claim_format=1` writes
the KEYLESS era-1 recipe — an explicit `format = 1` line would mint a
different root than every era-1 claim already sealed, so the era-1
spelling is omission, pinned as such. The self-claim chain's
unmigrated layers now pass `claim_format=1` explicitly and their
pinned roots re-mint byte-identically — which the lockfile verified:
eighteen of twenty layers held through a change to pack's authoring
default.

An inputs manifest no longer hard-codes format 2; it requires 2 or
newer and is born at the default like everything else (pack refuses a
manifest at an explicit format 1).

## Click two — a verdict's record names its jail

The same run found both regrown kernels earning every verdict while
reporting no quarantine at all: the build criteria checked that
rebuilds run, seal, and refuse tampering, but never made a kernel SAY
what confinement a verdict was earned under — exactly the provenance a
trust-transfer acceptor needs before applying a ~44,000× multiplier to
someone else's earn. `build_check` now exercises it: an audit's gate
rows and a rebuild's result each carry `quarantine`, drawn from the
closed vocabulary (`seatbelt`, `bubblewrap`, `inherited`, `none`) —
`none` is the honest word for an unsandboxed earn, and an absent key
is nonconforming.

## The closure criterion ate first

The bundle's first draft failed the gate — refused by `closure_check`,
the criterion signed two days earlier: the new authoring pin consumed
`kernel._dump_recipe` and `kernel.recipe_path` from the generated
package, names no check exercises, so a conforming regrown kernel
could legally omit them and crash the gate's own machinery. The fix
was less consumption, not more pins: the guidance-neutrality test now
rewrites the raw recipe textually and stands only on exercised surface
(`kernel.RECIPE`, `kernel.seal`, `kernel.load_recipe`). The boundary
instrument caught the boundary's own maintainer within minutes of the
mistake existing — the same week it was signed into the criteria.

## …and the scanner ate second (postscript, same day)

The landed second draft carried its own defect: the guidance-rewrite
test quoted the default hint verbatim, and the hint names the generated
file — `pkg/__init__.py`, a nested path this pinned file does not
contain, which dangles in a rebuild room. The self-contained scanner
caught it twice within the hour: CI went red on all six platforms, and
the r4 judge's held-out battery flagged the same line against the
regrown tree. Third draft: a flat fixture whose hint quotes a bare
filename. Final roots:

    authoring  c290405a…  ->  07e0fff6…
    repository 79bce6fb…  ->  344ba6e1…

One pin, three drafts, each refusal from a different standing
instrument (the closure criterion, then the scanner) — none of them
aimed at this mistake in particular, all of them general. That is what
a boundary with teeth feels like from the inside.

## The shape of the move

One bundle, two criteria files, two layer roots, no cascade: each
layer's root covers its own check and recipe, so a criteria edit is
surgically local and the lockfile diff reads as the exact intention —
the same property that let CI's reference finding and the
implementation-sensitivity finding land as one-entry re-pins. Full
gate and audit green at the new root; 103/103 ordinary tests; the test
suite's one adjustment is the manifest test following the default it
pinned.

Both proposals now carry their signed status. The r4 predictions
(predictions_r4.md) gain two testable consequences for whenever the
paused run resumes: trees regrown under this boundary must author at
format 3 by default and must name their jails — the cross-judging
matrix is the instrument that will check both, closing the loop the
findings opened.
