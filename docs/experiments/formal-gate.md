# The formal gate — prove, don't sample or bound

Move 3 of the reach-the-jester plan (docs/notes/jester.md): the deepening hinge.
The fuzz was a sampler ("no divergence in 20k"); the bounded-exhaustive gate was
a decider over a finite domain, trusting a reference. This gate is a **prover**:
its verdict is a machine-checked proof that the implementation satisfies a
**declarative spec** for **every** input, discharged by an SMT solver (z3).

Specimen: `clamp(x, lo, hi)` — small enough to hold in the head, sharp enough to
get subtly wrong. Its spec is five declarative properties (never below `lo`,
never above `hi`, identity in range, pinned to `lo` below, pinned to `hi` above,
under precondition `lo <= hi`) — a *predicate*, not a reference implementation.
Artifacts: [`formal/gate_formal.py`](formal/gate_formal.py) (the translator +
prover), [`formal/spec.py`](formal/spec.py) (the declarative spec),
[`formal/clamp.py`](formal/clamp.py) (a proven implementation). Sealed as the
record `clamp-proven`, root `5522c088`; the gate runs z3 inside the quarantine
via `kernel.run_gate`.

## How it stays sound

The gate builds the proof obligation **from the implementation's own AST**, not
from a producer-supplied model — so a cast cannot pass by proving something other
than its own code. It translates the impl to an SMT term, asserts the precondition
and the *negation* of the spec, and asks z3: can the spec be violated? `unsat`
means no — proven for all integers. `sat` means yes — and z3 returns the exact
counterexample input.

The implementation language is deliberately restricted — straight-line integer
arithmetic, comparisons, `min`/`max`/`abs`, conditional expressions; **no
division, no loops**. That is exactly the fragment where Python's unbounded-int
semantics and SMT `Int` coincide, so the AST→SMT translation is faithful and
small enough to audit. The price is honest: the basin is "impls the gate can
*prove*," which is narrower than "impls that are *correct*" — a correct clamp
written outside the fragment is refused, not blessed.

## Result: proves the correct, refutes the wrong with a witness

| implementation | z3 | verdict |
|---|---|---|
| `max(lo, min(x, hi))` | unsat | **proven** for all integers |
| `lo if x < lo else (hi if x > hi else x)` | unsat | **proven** (a different impl, same basin) |
| `min(x, hi)` (drops lower bound) | sat | refuted — counterexample `x=-1, lo=0` |
| `max(lo, x)` (drops upper bound) | sat | refuted — counterexample above `hi` |
| `max(lo, min(x, hi - 1))` (off-by-one) | sat | refuted at `hi` |

Two ceilings from the bounded-exhaustive gate, both lifted: the domain is
**unbounded** (every integer, not a sample and not an enumerated frontier), and
there is **no reference to trust** (a declarative spec, not a reference impl). And
where a wrong impl fails, it fails with a *witness*, not a probability.

## The trust surface, named

A proof moves trust, it does not abolish it. What this gate asks you to trust:

1. **The checker (z3).** We trust z3's `unsat`. z3 is an SMT solver, not a proof
   assistant with a tiny kernel — a heavier trust base than Lean/Coq, where the
   kernel checks a proof term. A stronger future step: emit and independently
   check z3 proof certificates, or move to a proof assistant so the trusted core
   is a small kernel. (Lean/Coq were absent on this machine; z3 was present, and
   it is the honest tool in reach.)
2. **The translator's faithfulness** — that the AST→SMT rendering matches Python.
   Mitigated by the restricted fragment (no division, no loops), where the two
   semantics coincide; it is the analog of bounded-exhaustive's "trust the
   reference," but smaller (one translator, once) and about the language, not the
   function.
3. **The spec predicate itself** — that these five properties *are* clamp. This
   is the irreducible human act the whole project keeps concentrating and never
   removing: adopting the predicate. A proof that an impl meets the wrong spec is
   a beautifully-checked wrong answer.

## Cast (2026-09-06): the oracle lands in the proof basin, different phenotype

The live rehydration ran: an untrusted oracle (sonnet-5) regrew `clamp.py` from
the spec and gate alone — **one call, 17 seconds, `$0.14`** — and wrote

```python
return min(max(x, lo), hi)
```

**byte- and structure-different** from the sealed realization
(`max(lo, min(x, hi))` — the opposite composition order), and z3 **proved it**
over all integers. Root matches (`5522c088`), verify and audit clean
([`formal/clamp_cast.py`](formal/clamp_cast.py)). The first cast into a *proof*
gate rather than a behavior gate: the basin "provably-correct clamps"
demonstrably holds multiple phenotypes, and the jester landed in it, with a
proof, on the first try.

## What remains

The specimen is a total straight-line function; loops, recursion, and data
structures need loop invariants or induction, which SMT alone does not
discharge. That step — the cast *carrying its own inductive argument* — is the
deep-proof gate ([deep-proof.md](deep-proof.md)).

## Status

Measured 2026-09-05, no model calls. The formal gate is built, teeth-verified
(proves two distinct correct impls, refutes three wrong ones with counter-
examples), and sealed as `clamp-proven` (`5522c088`). This is the proof body of
the jester plan opened for real: a Reticuli gate whose passing is a proof over
all inputs, trusting only the checker and the predicate.
