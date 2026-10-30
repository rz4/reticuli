# zeta's probe guard checks the facade, not what runs

> **LANDED 2026-10-30**, keyholder-authorized directly. Zeta root
> `b0e235d2 → 237ce0b6`; the fix is the staging-under-`-S` approach plus a
> code-containment backstop, pinned by `zeta/criteria/probe_check.py`. Account:
> `research/provenance/revision-2026-10-30-probe-containment.md`. The text
> below is the original proposal, kept as the reasoning record; where it
> weighs part 1 (containment) against part 2 (staging), the implementation
> took part 2 as the real fix and part 1 as the backstop, exactly as the
> "honest caution" section anticipated.

2026-10-29. Staged for a keyholder ruling. A **contraction** on zeta: it
closes a hole through which a probe can run foreign code and report it as a
member's behaviour. It would move zeta's root (a pinned criterion), and it is
**not landed** — it is a ruling because the fix changes what zeta's probe is
allowed to trust, and a wrong fix refuses honest reconstructions.

## The hole, found by falling into it

`zeta/lib/probe.py`'s package driver guards against the import-resolution
trap: it imports `<pkg>.kernel`, then refuses unless `kernel.__file__` resolves
under the member's own tree (`misresolved`). That guard is necessary and it is
not sufficient. Two ways past it, both hit while grade-2-probing the closure
trials (`research/harness/closure/grade2-the-crown-jewel.md`):

1. **Transitive resolution.** A reconstruction whose `kernel.py` imports its
   internals by the package's *real name* — `from reticuli._kernel import
   run` — rather than relatively — `from ._kernel import run` — loads those
   internals from whatever `reticuli` is on the path. Under an editable
   install that is the shipped kernel. `kernel.__file__` still sits under the
   member tree, so the guard passes while the function that runs is foreign.
   `r24-claude` imports absolutely; `r23`/`g2` import relatively. Probing all
   three under the package name `tree` measured shipped-for-r24 and called the
   result a behavioural split.

2. **Facade reimplementation.** Even with the right file loaded, `kernel.cost`
   may reimplement the behaviour inline and never call the `_run.cost` a
   reader would inspect to predict it — so `_run.cost` is dead code and the
   "surface" named in the spec is not what executes. `g2`'s cost facade does
   exactly this; its `_run.cost`'s `math.isfinite` guard never runs.

Neither is caught by a `__file__` check, and both produce a confident wrong
answer rather than an error — the worst failure mode for an instrument whose
whole job is to be trusted.

## Why it matters now

This is the instrument that the replacement-grade program will point at
strangers' reconstructions. A probe that can be fooled into reporting the
shipped kernel's behaviour as a member's — or into predicting from dead code —
cannot certify anything. The reconstruct-codebase skill already carries the
operator-facing version of this ("the harness has to check rather than the
operator remember"); this proposal moves the check into zeta's pinned
criteria, where a regrown zeta must reproduce it.

## The proposed guard

A member observation is trustworthy only if the code that actually ran came
from the member tree. Two checks, both mechanical:

1. **Resolve the called function, not the module.** After calling, record
   `inspect.getsourcefile` (or `__code__.co_filename`) of the *bound function*
   and refuse unless it is under the member tree. This closes transitive
   resolution: r24's `cost`, loaded under the wrong name, would resolve to the
   shipped file and be refused as `misresolved` rather than reported.

2. **Load the member under the name its own code expects.** A reconstruction
   that imports `reticuli._kernel` only runs its own internals when it is
   materialised AS `reticuli`, with no other `reticuli` reachable — which is
   how the succession harness already stages a whole-tool tree. zeta's driver
   should stage the member under its declared package name in an environment
   (`-I -S`, or an explicit clean `sys.path`) where no installed package of
   that name can answer. The member registry already carries the package
   name; the driver should honour it rather than assuming relative imports.

Facade reimplementation (check 2 of the hole) is not fully closeable by a
guard — a facade that inlines its logic is running its own code, which is
legitimate; the lesson there is narrower: a reader must not *predict* a
member's behaviour from a module the facade does not call. That belongs in the
skill's probe-trap list (and is now there in spirit), not in a criterion.

## The honest caution about the fix

Check 1 can over-refuse. A conforming reconstruction may legitimately place a
function in a helper module, or re-export it, and `getsourcefile` on a
re-exported builtin-wrapped callable can point outside the obvious file. The
guard must resolve through `functools.wraps`/re-export to the defining file
and allow anything under the member tree, refusing only what resolves OUTSIDE
it. A guard that refuses honest trees is worse than the hole, because it
turns a conformant reconstruction into a false `misresolved` — the
mirror of the bug it fixes. That calibration is why this is a ruling with a
test obligation (a positive control: a known-good reconstruction that imports
relatively must still pass), not a one-line patch.

## Cost

A pinned criterion on `zeta/lib/probe.py`'s containment, so zeta's root moves
and its reconstruction population retires — currently cheap, the population is
a singleton at the current root. Batch with the other staged zeta rulings so
it retires once.
