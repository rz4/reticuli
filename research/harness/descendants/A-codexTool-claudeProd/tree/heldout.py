"""Held-out measurement: how much two producers agree, and why.

The arithmetic here decides what a reconstruction experiment MEANS, so it is
under contract rather than left to a rebuild's taste: two conforming versions
of this tool reporting different adequacy for the same experiment would make
the research output unreadable.

`agreement` reports the **marginal** statistic: the observed agreement rate,
the independence baseline built from each producer's own pass rate, and the
excess between them.

That excess is **confounded by case difficulty**, and the confound is not
small.  Under conditional independence its expectation is
`2 * Cov_i(p_Ai, p_Bi)`, so producers that share nothing at all show a large
positive excess whenever some cases are harder than others — which is every
real corpus.  `stratified_excess` is the form that may be read as evidence of
shared structure: it compares each pair's agreement against a per-case null
estimated from the OTHER producers, so difficulty is explained away rather
than reported as convention.  That estimate needs a leave-out sample of at
least two, hence at least FOUR producers, and it says so instead of guessing.
"""
from itertools import combinations


def _shared(a: dict, b: dict) -> list:
    """Only cases both producers were judged on are comparable."""
    return sorted(set(a) & set(b))


def agreement(a: dict, b: dict) -> dict:
    """The marginal agreement statistic for two producers.

    Rates come from the SHARED cases, so the three numbers stay consistent
    with each other; no shared case is UNMEASURED, never a zero.
    """
    cases = _shared(a, b)
    if not cases:
        return {"cases": 0, "agreement": None, "expected": None,
                "excess": None, "rate_a": None, "rate_b": None}
    total = len(cases)
    same = sum(1 for case in cases if bool(a[case]) == bool(b[case]))
    rate_a = sum(1 for case in cases if a[case]) / total
    rate_b = sum(1 for case in cases if b[case]) / total
    observed = same / total
    expected = rate_a * rate_b + (1 - rate_a) * (1 - rate_b)
    return {"cases": total, "agreement": observed, "expected": expected,
            "excess": observed - expected, "rate_a": rate_a,
            "rate_b": rate_b}


def stratified_excess(population: dict) -> dict:
    """The difficulty-adjusted excess, or the reason it cannot be estimated.

    For each pair and each case, the null probability of agreement is
    estimated from the producers OUTSIDE the pair.  With three producers a
    pair leaves exactly one observation, which cannot give an unbiased
    per-case estimate; the floor is reported rather than guessed, on the
    standing rule that unknown evidence is not evidence.
    """
    names = sorted(population)
    if len(names) < 4:
        return {"stratified": None, "producers": len(names),
                "why": (f"a per-case difficulty null needs a leave-out "
                        f"sample of at least two, so at least four "
                        f"producers; this population has {len(names)}")}
    cases = None
    for name in names:
        keys = set(population[name])
        cases = keys if cases is None else (cases & keys)
    cases = sorted(cases or [])
    if not cases:
        return {"stratified": None, "producers": len(names),
                "why": "no case was judged by every producer"}
    diffs = []
    for left, right in combinations(names, 2):
        others = [n for n in names if n not in (left, right)]
        if len(others) < 2:
            return {"stratified": None, "producers": len(names),
                    "why": "a pair leaves fewer than two observations"}
        pair = []
        for case in cases:
            observed = 1.0 if bool(population[left][case]) == \
                bool(population[right][case]) else 0.0
            share = sum(1.0 for n in others if population[n][case]) \
                / len(others)
            null = share * share + (1 - share) * (1 - share)
            pair.append(observed - null)
        diffs.append(sum(pair) / len(pair))
    return {"stratified": sum(diffs) / len(diffs), "producers": len(names),
            "pairs": len(diffs), "cases": len(cases), "why": None}
