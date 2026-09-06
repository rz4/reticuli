"""The cast's proof artifact: the inductive argument for sum_to's loop, as SMT
terms over the params and the loop state. The invariant carries the running
Gauss identity; the variant counts down the remaining iterations."""

INVARIANT = "(and (<= 0 i) (<= i n) (= (* 2 s) (* i (+ i 1))))"
VARIANT = "(- n i)"
