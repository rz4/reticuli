"""Bounded-exhaustive gate for quirkcalc — DECIDE, don't sample.

The differential fuzz asked "did impl and reference disagree on N random
expressions?" and answered "not in 20k tries." That is a sampler; a rarer edge
can hide below its resolution (one did — a `/0`-inside-`?` ordering edge at
~1-in-60k). This gate replaces the sampler with a DECIDER over a bounded domain:
enumerate EVERY quirkcalc expression with up to MAX_OPS binary operators over a
fixed operand set, in the parenthesizations the grammar admits, and require the
implementation under test (`calc.evaluate`) to agree with the sealed reference
semantics (`semantics.evaluate`) on ALL of them — the same integer, or the same
refusal (CalcError). Passing is a small-scope theorem: `calc` IS the reference on
the entire bounded domain, not merely on a sample of it. Beyond the bound stays
unproven — the honest ceiling, but now a decided one, not a hoped one.

Stdlib only. Writes PASS iff the implementation conforms exhaustively.
"""
import sys

sys.path.insert(0, ".")
import calc
import semantics

# The bounded domain. 0 is mandatory — it is where the sharp edges live
# (division by zero, digit-join with zero); the rest give ordering (?), width
# (~), and — via subtraction — negative intermediates.
OPERANDS = ["0", "1", "2", "5"]
OPS = ["+", "-", "*", "/", "~", "?", "%"]
MAX_OPS = 2


def _exprs(n):
    """Every expression string with exactly n binary operators, each combining
    node rendered both BARE (exercises precedence/associativity) and fully
    PARENTHESIZED (forces structure, exercises the evaluator directly)."""
    if n == 0:
        yield from OPERANDS
        return
    for k in range(n):                       # k operators on the left, n-1-k on the right
        for left in _exprs(k):
            for right in _exprs(n - 1 - k):
                for op in OPS:
                    yield f"{left} {op} {right}"
                    yield f"({left}) {op} ({right})"


def _outcome(mod, s):
    """The observable behavior of `mod` on `s`: a value, a defined refusal, or a
    raw crash (itself a divergence — a conformant impl refuses, never throws)."""
    try:
        return ("value", mod.evaluate(s))
    except mod.CalcError:
        return ("refused", None)
    except Exception as e:                   # noqa: BLE001 — a raw exception is a finding
        return ("crash", type(e).__name__)


def main():
    domain = set()
    for n in range(MAX_OPS + 1):
        domain.update(_exprs(n))

    disagreements = []
    for s in sorted(domain):
        got, want = _outcome(calc, s), _outcome(semantics, s)
        if got != want:
            disagreements.append((s, got, want))

    if disagreements:
        for s, got, want in disagreements[:25]:
            print(f"DISAGREE  {s!r}\n    impl={got}  reference={want}")
        print(f"\n{len(disagreements)} disagreements over {len(domain)} expressions "
              f"(<= {MAX_OPS} ops, operands {OPERANDS})")
        sys.exit(1)

    print(f"bounded-exhaustive: calc == reference on all {len(domain)} expressions "
          f"(<= {MAX_OPS} ops over {OPERANDS}) — a small-scope theorem, not a sample")
    with open("PASS", "w", encoding="utf-8") as f:
        f.write("ok")


if __name__ == "__main__":
    main()
