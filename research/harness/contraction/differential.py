"""Run every surviving implementation against X and find where they disagree.

A disagreement is an input on which the survivors do not all behave the same
way. Each one is a question C_n did not answer. The matrix D[i][j] is the
fraction of X on which i and j differ — the pairwise behavioral distance the
metrics average into D(n).
"""

from __future__ import annotations

from dataclasses import dataclass

import boundary


@dataclass
class Disagreement:
    probe: str
    outcomes: dict[str, tuple]  # impl name -> canonical outcome

    def splits(self) -> int:
        return len(set(self.outcomes.values()))


def run(impls: dict, probes: list[str]) -> dict[str, list[tuple]]:
    """impl name -> its outcome on each probe, aligned to `probes`."""
    return {name: [boundary.call(m, p) for p in probes] for name, m in impls.items()}


def matrix(results: dict[str, list[tuple]]) -> dict[str, dict[str, float]]:
    names = list(results)
    n = len(next(iter(results.values()))) if results else 0
    out: dict[str, dict[str, float]] = {a: {} for a in names}
    for i, a in enumerate(names):
        for b in names[i:]:
            if n == 0:
                d = 0.0
            else:
                differ = sum(1 for x, y in zip(results[a], results[b], strict=True) if x != y)
                d = differ / n
            out[a][b] = out[b][a] = d
    return out


def mean_pairwise(mtx: dict[str, dict[str, float]]) -> float:
    names = list(mtx)
    pairs = [(a, b) for i, a in enumerate(names) for b in names[i + 1:]]
    if not pairs:
        return 0.0
    return sum(mtx[a][b] for a, b in pairs) / len(pairs)


def disagreements(impls: dict, probes: list[str]) -> list[Disagreement]:
    """Every probe the survivors do not all agree on."""
    results = run(impls, probes)
    out = []
    for i, p in enumerate(probes):
        outcomes = {name: results[name][i] for name in impls}
        if len(set(outcomes.values())) > 1:
            out.append(Disagreement(probe=p, outcomes=outcomes))
    return out
