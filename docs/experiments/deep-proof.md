# The deep-proof gate — the cast carries its own induction

The step past [the formal gate](formal-gate.md): `clamp` was straight-line, one
SMT query, no induction. Loops need an **inductive argument**, and a solver will
not invent one — so here the cast must *carry its proof*. The record's free
outputs are two files: the implementation (`sum_to.py`, a genuine while-loop)
**and** `proof.py`, holding a loop INVARIANT and a termination VARIANT as SMT
terms. The gate derives the five Floyd–Hoare verification conditions and z3
discharges each over all integers:

| VC | obligation |
|---|---|
| 1 init | precondition ∧ initializations ⇒ invariant |
| 2 preserve | invariant ∧ loop-condition ∧ body ⇒ invariant′ — **the induction** |
| 3 post | invariant ∧ ¬condition ⇒ postcondition of the return value |
| 4 bound | invariant ∧ condition ⇒ variant ≥ 0 |
| 5 decrease | invariant ∧ condition ∧ body ⇒ variant′ < variant — **termination** |

All five unsat ⇒ **total correctness**: the loop terminates and its result meets
the sealed postcondition for every input satisfying the precondition. This is
proof-carrying code in miniature: the basin is not "implementations that pass" —
it is "**implementation + checkable inductive argument**."

Specimen: `sum_to(n)` (0+1+…+n), sealed spec `PRE: n ≥ 0`,
`POST: 2·result = n·(n+1)` — Gauss, stated without division. The shape contract
*requires* a loop: a closed-form answer is refused, because proving the loop is
the point. Artifacts: [`deepproof/`](deepproof/) (gate, spec, a proven
implementation and its proof). Sealed as `sum-proven`, root `37f683c9`.

## Soundness of the gate itself

The obligations are built **from the implementation's own AST** (restricted
fragment: integer arithmetic, comparisons, min/max/abs, conditionals; simple
assignments; one while; no division, no nesting — where Python-int and SMT-Int
coincide). Primed state is built by sequential substitution, and the invariant is
re-read over primed state with SMT-LIB `let` binding — no textual substitution
ever touches producer strings. The producer's SMT strings are **data, not solver
commands**: token-whitelisted, command-words forbidden, parens balanced, symbols
restricted to params + the impl's own state variables.

## Teeth (all verified)

- **A weak invariant is refused even with a correct implementation** (drop the
  Gauss conjunct → VC3 fails). The proof artifact is load-bearing — this is the
  line between a behavior gate and a proof gate.
- A wrong implementation (sums 0..n-1) with its own best invariant → VC3 fails.
- A non-terminating loop → VC2 *and* VC5 fail.
- A closed-form, no-loop implementation → shape-refused.
- Solver-command injection in the invariant string → refused at the whitelist.
- The honest specimen proves: five ✓, `PROVEN` written.

## The cast — the jester invents the induction

The live rehydration: an untrusted oracle regrows **both** files from the sealed
spec and gate alone — it must write the loop *and invent the invariant and
variant*, the genuinely creative act of a correctness proof, then pass five VCs.

**Landed.** One agentic session (2 calls, 48 s, `$0.23`): the cast wrote its own
loop — same count-up shape, its own state naming (`result` as the accumulator
where ours uses `s`; both files byte-different) — and, having never seen our
proof, **invented the invariant for its own loop**:

```python
INVARIANT = "(and (<= 0 i) (<= i n) (= (* 2 result) (* i (+ i 1))))"
VARIANT = "(- n i)"
```

the running Gauss identity, stated over *its* variables, plus the right variant.
All five VCs discharged; root `37f683c9`, verify and audit clean (audit re-runs
the gate, so the five VCs re-passed jailed). The deep-proof result in one
sentence: the jester can be made to hand you the induction along with the code,
and you never have to trust him — only check.

## The honest trust surface

Unchanged from the formal gate, plus one item: z3's `unsat` (a solver, not a
kernel-checked proof term); the AST→SMT translator's faithfulness on the
restricted fragment; the predicate's adequacy (the irreducible human act); and
now also the **VC generator** — that these five conditions are the right
Floyd–Hoare obligations. All four are *fixed, auditable seeds*; none scale with
the number of casts. Loops with data structures, nested loops, and recursion
still lie beyond this fragment — the genuine doorway to a proof assistant as the
gate, where the trusted core shrinks to a kernel.

## Status

Built and teeth-verified 2026-09-06 with zero model calls; cast landed the same
day (`$0.23`). Records: `sum-proven` (`37f683c9`), and the clamp cast
(`clamp-proven`, `5522c088`, `$0.14`, a structurally different proven phenotype).
The proof body of the jester plan now runs sampler → decider → prover →
**prover-with-induction**, and the last two have been cast by an untrusted
oracle. The cast's own copy of the specimen lives in session scratch; the sealed
realization and its proof are the banked artifacts here.
