"""Compute one generation's metrics from the frozen definitions.

Nothing is defined here that is not in the pre-registration; this file only
computes. A generation's inputs are: the attempted rebuilds, which of them the
gate passed (the survivors), their sources, the disagreements found among them,
the keyholder's adjudication, and the witnesses seen in prior generations.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import boundary
import differential
import structure
from reduce import partition, witness_key


@dataclass
class Generation:
    n: int
    attempts: int              # rebuilds started
    survivors: dict            # name -> module, gate passed
    sources: dict              # name -> source text of the generated code
    costs: dict = field(default_factory=dict)  # name -> producer cost (units)
    prior_witnesses: set = field(default_factory=set)
    # adjudication maps a minimal witness -> "counterexample" | "irrelevant" |
    # "specified"; supplied by the keyholder, absent means not-yet-adjudicated.
    adjudication: dict = field(default_factory=dict)


def compute(gen: Generation, probes: list[str], tau: float) -> dict:
    survivors = gen.survivors
    rcount = len(survivors)

    # R(n): reconstruction success rate, and the count Y/Y* divide by.
    R = rcount / gen.attempts if gen.attempts else 0.0

    # Structural diversity S(n) and the cluster floor.
    smtx = structure.dist_matrix(gen.sources) if gen.sources else {}
    S = structure.mean_pairwise(smtx)
    cluster_count = len(structure.clusters(smtx, tau)) if smtx else 0

    # Behavioral diversity D(n).
    dmtx = differential.matrix(differential.run(survivors, probes)) if survivors else {}
    D = differential.mean_pairwise(dmtx)

    # Disagreements -> minimal witnesses -> classes -> novelty.
    #
    # A class is one *question*: all inputs whose minimal witness splits the
    # survivors the same way (the same outcome across every implementation) are
    # the same disagreement, and the keyholder adjudicates one representative,
    # not each near-duplicate. Dedup within a generation is by this partition;
    # dedup across generations is by the representative witness string, which is
    # population-independent and so stable as survivors change.
    raw = differential.disagreements(survivors, probes)
    classes: dict[tuple, dict] = {}
    for dis in raw:
        w = witness_key(dis.probe, survivors)
        wout = {n: boundary.call(survivors[n], w) for n in survivors}
        sig = partition(survivors, w)
        cur = classes.get(sig)
        if cur is None or len(w) < len(cur["rep"]):
            classes[sig] = {"rep": w, "outcomes": wout}

    reps = {c["rep"]: c for c in classes.values()}
    novel = [rep for rep in reps if rep not in gen.prior_witnesses]

    U = len(novel)
    accepted = [rep for rep in novel if gen.adjudication.get(rep) == "counterexample"]
    A = len(accepted)
    witnesses = reps

    Y = U / rcount if rcount else 0.0
    Ystar = A / rcount if rcount else 0.0

    known = [c for c in gen.costs.values() if c is not None]
    Kstar = min(known) if known else None

    def _class_summary(rep: str) -> dict:
        outs = reps[rep]["outcomes"]
        vgroups: dict = {}
        for n, o in outs.items():
            key = "err" if o[0] == "err" else repr(o[1])
            vgroups.setdefault(key, []).append(n)
        return {
            "witness": rep,
            # value groups: what each side actually computed (for value
            # disagreements, not just accept-vs-reject)
            "groups": [{"value": k, "members": sorted(v)}
                       for k, v in sorted(vgroups.items())],
            "accept": sorted(n for n, o in outs.items() if o[0] == "ok"),
            "reject": sorted(n for n, o in outs.items() if o[0] == "err"),
        }

    return {
        "generation": gen.n,
        "attempts": gen.attempts,
        "R": round(R, 4),
        "R_count": rcount,
        "S": round(S, 4),
        "clusters": cluster_count,
        "D": round(D, 4),
        "U": U,
        "A": A,
        "Y": round(Y, 4),
        "Ystar": round(Ystar, 4),
        "Kstar": Kstar,
        "novel_witnesses": sorted(novel),
        "accepted_witnesses": sorted(accepted),
        "all_witnesses": sorted(witnesses),
        "novel_classes": [_class_summary(rep) for rep in sorted(novel)],
    }
