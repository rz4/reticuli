"""Held-out agreement: how much two producers' outcomes share.

A reconstruction experiment asks whether two independent producers landed on
the same behavior for the same reason. Agreement alone cannot answer that,
and this module exists to keep the difference explicit, because a research
number that overstates itself is worse than none.

THE MARGINAL FORM is the obvious one: observed agreement minus the
independence baseline computed from each producer's overall pass rate. It is
CONFOUNDED by case difficulty. Under conditional independence its
expectation is `2 * Cov_i(p_Ai, p_Bi)`, so two producers sharing nothing at
all show a large positive excess whenever some cases are harder than others
-- which is every real corpus.

THE DIFFICULTY-ADJUSTED FORM is the one that may be read as evidence of
shared structure. For each case it estimates that case's difficulty from the
producers being LEFT OUT of the pair, so the baseline varies with the case
rather than with the corpus. An unbiased per-case estimate needs at least
two left-out observations, hence at least FOUR producers -- and where there
are fewer it says so instead of guessing.
"""


def _shared(a: dict, b: dict) -> list:
    """Only cases both producers were judged on are compared."""
    return sorted(set(a or {}) & set(b or {}))


def agreement(a: dict, b: dict) -> dict:
    """Observed agreement, the marginal baseline, and their difference."""
    cases = _shared(a, b)
    if not cases:
        return {"cases": 0, "agreement": None, "expected": None,
                "excess": None,
                "why": "no case both producers were judged on"}
    same = sum(1 for case in cases if bool(a[case]) == bool(b[case]))
    observed = same / len(cases)
    pa = sum(1 for case in cases if bool(a[case])) / len(cases)
    pb = sum(1 for case in cases if bool(b[case])) / len(cases)
    expected = pa * pb + (1 - pa) * (1 - pb)
    return {"cases": len(cases), "agreement": observed,
            "expected": expected, "excess": observed - expected,
            "rate_a": pa, "rate_b": pb,
            "why": None}


def stratified_excess(outcomes: dict) -> dict:
    """Agreement in excess of what CASE DIFFICULTY alone explains.

    `outcomes` maps a producer name to its {case: passed} mapping. For each
    pair and each shared case, the difficulty is estimated from the other
    producers and the pair's agreement is compared against that per-case
    baseline. Returns None, with a reason, where the estimate cannot exist.
    """
    names = sorted(outcomes or {})
    if len(names) < 4:
        return {"stratified": None, "producers": len(names),
                "why": ("a per-case difficulty estimate must leave out the "
                        "pair being compared, and two left-out observations "
                        "are the fewest that estimate anything: four "
                        "producers are needed, and this population has "
                        f"{len(names)}")}
    total, counted = 0.0, 0
    for first in range(len(names)):
        for second in range(first + 1, len(names)):
            name_a, name_b = names[first], names[second]
            a, b = outcomes[name_a], outcomes[name_b]
            others = [outcomes[n] for n in names if n not in (name_a, name_b)]
            for case in _shared(a, b):
                seen = [bool(o[case]) for o in others if case in o]
                if len(seen) < 2:
                    continue
                rate = sum(1 for value in seen if value) / len(seen)
                baseline = rate * rate + (1 - rate) * (1 - rate)
                observed = 1.0 if bool(a[case]) == bool(b[case]) else 0.0
                total += observed - baseline
                counted += 1
    if not counted:
        return {"stratified": None, "producers": len(names),
                "why": "no case had two left-out observations"}
    return {"stratified": total / counted, "producers": len(names),
            "pairs_measured": counted, "why": None}
