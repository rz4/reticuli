"""Held-out agreement: how much two producers' outcomes have in common.

Two statistics, and the difference between them matters more than either.
The MARGINAL excess compares observed agreement to an independence baseline
built from each producer's overall pass rate -- and it is confounded by case
difficulty, so producers that share nothing at all show a large positive
excess whenever some cases are harder than others, which is every real
corpus. The DIFFICULTY-ADJUSTED form conditions on a per-case leave-out
estimate of difficulty, needs four producers to exist, and says so instead of
guessing.
"""


def _shared(left: dict, right: dict) -> list:
    """Only cases both producers were judged on are compared."""
    return sorted(set(left) & set(right))


def agreement(left: dict, right: dict) -> dict:
    """The marginal statistic: observed, baseline, and the gap between them."""
    cases = _shared(left or {}, right or {})
    total = len(cases)
    if not total:
        return {"cases": 0, "agreement": None, "expected": None,
                "excess": None, "rate_a": None, "rate_b": None}
    same = sum(1 for case in cases if bool(left[case]) == bool(right[case]))
    observed = same / total
    rate_a = sum(1 for case in cases if bool(left[case])) / total
    rate_b = sum(1 for case in cases if bool(right[case])) / total
    expected = rate_a * rate_b + (1 - rate_a) * (1 - rate_b)
    return {"cases": total, "agreement": observed, "expected": expected,
            "excess": observed - expected, "rate_a": rate_a,
            "rate_b": rate_b}


def stratified_excess(outcomes: dict) -> dict:
    """The difficulty-adjusted statistic, where it can exist at all.

    For each pair and each case, the baseline is built from the OTHER
    producers' outcomes on that same case -- so what every producer finds
    hard is attributed to difficulty rather than reported as hidden shared
    convention. The leave-out set needs at least two members for the per-case
    estimate to be unbiased, which means four producers; below that the floor
    is reported, never guessed at.
    """
    names = sorted(outcomes or {})
    if len(names) < 4:
        return {"stratified": None, "producers": len(names),
                "why": ("four producers are needed: the per-case baseline is "
                        "a leave-out estimate, and with fewer than four the "
                        "leave-out set holds at most one observation, which "
                        "cannot estimate difficulty without bias")}
    terms = []
    for i, first in enumerate(names):
        for second in names[i + 1:]:
            left, right = outcomes[first], outcomes[second]
            others = [outcomes[n] for n in names if n not in (first, second)]
            for case in _shared(left, right):
                judged = [o[case] for o in others if case in o]
                if len(judged) < 2:
                    continue
                difficulty = sum(1 for value in judged if bool(value)) \
                    / len(judged)
                baseline = difficulty ** 2 + (1 - difficulty) ** 2
                observed = 1.0 if bool(left[case]) == bool(right[case]) else 0.0
                terms.append(observed - baseline)
    if not terms:
        return {"stratified": None, "producers": len(names),
                "why": "no case was judged by four producers at once"}
    return {"stratified": sum(terms) / len(terms), "producers": len(names),
            "pairs": len(names) * (len(names) - 1) // 2,
            "observations": len(terms), "why": None}
