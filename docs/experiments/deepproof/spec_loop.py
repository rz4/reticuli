"""The sealed spec for `sum_to(n)` — pre/postcondition as declarative SMT
predicates. The postcondition is stated over `result` and the params only, so it
is independent of how the implementation names its loop state. The contract also
fixes the SHAPE: the implementation must be a genuine loop (initializations, one
while, one return) in the gate's restricted fragment — a closed-form answer is
refused; proving the LOOP is the point."""

FUNC = "sum_to"
PARAMS = ["n"]
PRECONDITION = "(>= n 0)"
# result = 0 + 1 + ... + n, stated without division: 2*result = n*(n+1)
POSTCONDITION = "(= (* 2 result) (* n (+ n 1)))"
