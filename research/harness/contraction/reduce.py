"""Shrink a disagreement to its shortest form, without changing what it is.

A raw disagreement is often a long fuzzed string; what the keyholder should see
is the minimal input that splits the survivors *the same way*. The reducer is
partition-preserving: it deletes a character only if the who-agrees-with-whom
split is unchanged, so a URL-safe question does not collapse into a generic
junk-character one on the way down. Two disagreements that reduce to the same
minimal witness are the same question — that is how novelty and cross-generation
duplicates are decided.

The reducer is frozen and deterministic: no model.
"""

from __future__ import annotations

import boundary


def partition(impls: dict, s: str) -> tuple:
    """Which implementations agree with which on input `s`, discarding decoded
    values. A tuple of groups (each a sorted tuple of implementation names).
    Length < 2 means everyone agreed — not a disagreement."""
    groups: dict = {}
    for name, m in impls.items():
        groups.setdefault(boundary.call(m, s), []).append(name)
    return tuple(sorted(tuple(sorted(g)) for g in groups.values()))


def minimize(probe: str, impls: dict) -> str:
    """Shortest input reachable by single-character deletion that keeps the same
    partition as `probe`. A local minimum, which is what a minimal witness is."""
    target = partition(impls, probe)
    if len(target) < 2:
        return probe  # not actually a disagreement; leave it
    s = probe
    changed = True
    while changed:
        changed = False
        for i in range(len(s)):
            cand = s[:i] + s[i + 1:]
            if partition(impls, cand) == target:
                s = cand
                changed = True
                break
    return s


def witness_key(probe: str, impls: dict) -> str:
    """The identity of a disagreement: its minimal, partition-preserving
    witness. Equal keys are the same question, within and across generations."""
    return minimize(probe, impls)
