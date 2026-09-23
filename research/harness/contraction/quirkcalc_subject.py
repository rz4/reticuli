"""The quirkcalc subject: a deliberately partial C_0 and the probe set.

quirkcalc is an integer expression evaluator with *invented* semantics — `~` is
digit-join, `?` is max, `%` is floor-average, the additive and multiplicative
levels are right-associative, `/` truncates toward zero. None of that is
guessable; it lives only in the cases. That is exactly why it is a good
contraction subject: a partial C_0 leaves genuine ambiguity that only the tests
can resolve, so independent rebuilds diverge on the quirks and the ratchet has
real questions to close.

C_0 pins just enough that every operator appears and basic precedence/parens
hold — but not associativity, not the meaning of ? % ~, and none of the edge
cases (negative digit-join, division by zero, truncation direction). Those are
the probes.
"""

from __future__ import annotations

import random

from boundary import Boundary, observe

# Partial C_0: operators present, basic precedence and parens, associativity and
# invented semantics left open. Each entry is (expression, integer result).
# Chained same-level cases here are associativity-neutral on purpose
# (10+3-2 and 8*2*3 give the same answer either way), so C_0 does not leak it.
CASES = [
    ("0", 0),
    ("42", 42),
    ("1 + 1", 2),
    ("2 + 3 * 4", 14),
    ("2 * 3 + 4", 10),
    ("(1 + 2) * 3", 9),
    ("7 / 2", 3),
    ("8 * 2 * 3", 48),
    ("10 + 3 - 2", 11),
    ("12 ~ 34", 1234),
    ("3 ? 9", 9),
    ("4 % 9", 6),
]

# Expressions that probe the open surface — where quirkcalc's invented rules
# depart from the standard reading a blind model is likely to assume.
CONTESTED = [
    # right-associative additive / multiplicative
    "10 - 3 - 2", "1 - 2 - 3", "100 - 10 - 5 - 1",
    "100 / 5 / 2", "16 / 4 / 2", "24 / 4 * 2", "64 / 8 / 4 / 2", "2 * 12 / 4",
    # ? (max) and % (floor-average): precedence and associativity
    "9 ? 3", "1 ? 5 ? 3", "8 % 2 * 3", "2 ? 3 * 4", "2 * 3 ? 4",
    "1 + 2 ? 5", "2 ? 5 + 1", "10 % 4 % 8", "1 % 2 % 3", "7 % 2", "5 % 5",
    "23 ? 10 % 5", "6 ? 2 % 8",
    # ~ (digit-join): associativity, negative right operand, precedence
    "1 ~ 2 ~ 3", "12 ~ 3 ~ 45", "2 * 3 ~ 4", "1 ~ 2 + 3", "(1 + 2) ~ 3",
    "5 ~ (0 - 2)", "(0 - 7) ~ 2", "1 ~ 0 * 2",
    # division: truncation toward zero, division by zero
    "(0 - 7) / 2", "(0 - 8) / 3", "8 / (0 - 3)", "5 / 0", "0 / 5",
    "1 + 5 / 0", "2 % 30 / 0",
    # negatives, grouping
    "0 - 7", "2 * (3 + 4)",
    # standard operators that quirkcalc does not have — value or error?
    "2 ** 3", "2 ^ 3", "5 // 2", "3.5", "",
]
FUZZER_SEEDS = range(400)
_OPS = ["+", "-", "*", "/", "?", "%", "~"]


# C_1: the counterexamples the keyholder accepted (2026-09-22), each pinning a
# rule the generation-0 rebuilds missed. Must match the claim's cases c12..c21.
C1_RULES = [
    ("10 - 3 - 2", ("ok", 9)),      # right-associative subtraction
    ("100 / 5 / 2", ("ok", 50)),    # right-associative division
    ("24 / 4 * 2", ("ok", 3)),      # right-assoc across * and /
    ("8 % 2 * 3", ("ok", 7)),       # % = floor-average, * binds tighter
    ("1 + 2 ? 5", ("ok", 6)),       # ? = max, precedence
    ("10 % 4 % 8", ("ok", 7)),      # % left-associative
    ("(0 - 7) / 2", ("ok", -3)),    # / truncates toward zero
    ("(0 - 7) ~ 2", ("ok", -72)),   # ~ digit-join, negative left
    ("5 ~ (0 - 2)", ("err",)),      # ~ negative right operand -> error
    ("2 * 3 ~ 4", ("ok", 68)),      # ~ binds tightest
]


# C_2: the residual witnesses from the C_1 survey, adjudicated against truth
# (provisional overnight step, pending keyholder ratification). Must match the
# claim's cases c22..c28.
C2_RULES = [
    ("(0-1)%0", ("ok", -1)),
    ("1-9%0", ("ok", -3)),
    ("2*3?4", ("ok", 6)),
    ("2+9%8?29", ("ok", 31)),
    ("3?0%5", ("ok", 4)),
    ("6%2?8", ("ok", 8)),
    ("9*7/4", ("ok", 9)),
]


def _happy(impl) -> list[str]:
    ev = getattr(impl, "evaluate", None)
    if ev is None:
        return ["missing evaluate"]
    fails = []
    for expr, want in CASES:
        got = observe(ev, expr)
        if got != ("ok", want):
            fails.append(f"case evaluate({expr!r}) -> {got!r}, want {want}")
    return fails


def C0() -> Boundary:
    return Boundary("quirkcalc", op="evaluate", checks=[_happy])


def _fuzz(seed: int) -> str:
    r = random.Random(seed)
    n = r.randint(1, 4)
    toks = [str(r.randint(0, 30))]
    for _ in range(n - 1):
        toks.append(r.choice(_OPS))
        toks.append(str(r.randint(0, 30)))
    expr = " ".join(toks)
    if r.random() < 0.35:
        if r.random() < 0.5:
            expr = "(" + expr + ")"
        else:
            expr = f"(0 - {r.randint(1, 9)}) {r.choice(_OPS)} " + expr
    return expr


def probes() -> list[str]:
    seen: dict[str, None] = {}
    for s in CONTESTED:
        seen.setdefault(s, None)
    for seed in FUZZER_SEEDS:
        seen.setdefault(_fuzz(seed), None)
    return list(seen)
