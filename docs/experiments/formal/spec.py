"""The formal spec of `clamp(x, lo, hi)` — a DECLARATIVE predicate, not a
reference implementation. These are the properties any correct clamp must have,
for all integers under the precondition lo <= hi; the gate proves the
implementation satisfies them for every input. Because the spec is a predicate
(not a reference impl), nothing here is trusted-by-inspection except the
predicate itself — the irreducible "are these the right properties?" human act."""

FUNC = "clamp"
PARAMS = ["x", "lo", "hi"]
PRECONDITION = "(<= lo hi)"


def properties(result):
    """SMT-LIB2 conjuncts a correct `result` must satisfy (result = clamp(x,lo,hi))."""
    return [
        f"(<= lo {result})",                                    # never below lo
        f"(<= {result} hi)",                                    # never above hi
        f"(=> (and (<= lo x) (<= x hi)) (= {result} x))",      # identity when in range
        f"(=> (< x lo) (= {result} lo))",                       # pinned to lo below
        f"(=> (> x hi) (= {result} hi))",                       # pinned to hi above
    ]
