# Revision — the reference root becomes order-independent

*2026-10-04. An identity-bearing transition, keyholder-directed ("make
the CI green"). CI turned out to be the first machine other than the
author's that the new reference layer ever met — and it caught a real
soundness defect the same hour.*

    old root  0c9aac0b4a0e75969b03aa8e5fc60e20e4602bc09b2c2f8b41e94b67d82941a0
    new root  af4962c3d6ea89ee681b6423b0725123371c4ba37ca1dab5775472a64998cfb9

    reference   cd3e3743…  (macOS readdir order)
                944063be…  (Linux readdir order, measured by CI)
            ->  e0471a90…  (sorted paths — the order-independent value)

## What CI caught

The final bundle's reference layer staged `spec/vectors` via `os.walk`,
sorting files within each directory but not the directory traversal
itself — and the resulting input list is part of the recipe, which is
inside the root. So the twentieth layer's identity depended on the
host's readdir order: one value on macOS, another on Linux. Every other
layer root matched across platforms; `self_check`'s lockfile refused on
CI exactly as designed. A root is a hash over bytes, never over the
host — the lockfile's own doctrine, enforced against its own builder.

## The fix

`scripts/selfclaim.py` (and the matching staging in
`scripts/selfaudit.py`) now enumerate the vectors as sorted full
relative paths, which no filesystem can reorder. The canonical
reference root is a third value — neither platform's accidental order —
pinned in the lockfile with the story. Only the reference entry and the
repository root moved.

## The pleasing part

This is the three-machine doctrine catching its own machinery: M2 — a
machine the author never touched — re-derived the claim and disagreed,
and the disagreement was a genuine defect, found within hours of the
layer existing and fixed the same day. The project's first
cross-platform contact behaved exactly the way the thesis says contact
should: the stranger's machine is the instrument, and its first finding
was real.
