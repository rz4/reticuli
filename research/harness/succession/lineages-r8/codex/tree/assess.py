"""Measure how strongly a sealed claim's gates constrain its generated code."""

from __future__ import annotations

from . import kernel


def assess(directory, *, mutants=100):
    """Return mutation evidence and the three assessment buckets.

    A killed mutant is measured by the checks; a surviving mutant is not.
    When no mutation can be made, mutation testing is not applicable.
    """
    if type(mutants) is not int or mutants < 0:
        raise ValueError("mutants must be a nonnegative integer")
    checked = kernel.verify(directory)
    if not checked['ok']:
        raise kernel.ClaimError('claim identity mismatch')
    score = kernel.mutation_score(directory, max_mutants=mutants)
    total = score['mutants']
    killed = score['killed']
    return {
        'measured': killed,
        'not_measured': total - killed,
        'not_applicable': 1 if total == 0 else 0,
        'rate': score['rate'],
        'mutants': total,
        'survivors': score['survivors'],
        'root': checked['root'],
    }
