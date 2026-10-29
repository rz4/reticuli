# Declared freedom belongs in the recipe, so the quotient is computable

2026-10-29. Staged for a keyholder ruling. This one touches the **format**,
so it is not a maintainer's correction — it is a format-5 question, and the
decision is which of two readings of the identity rule governs. Not landed.
No code here; the proposal is the ruling.

## Why this blocks the replacement-grade work

`negative-space.md` already states the endpoint, and it is not `|I(S)| → 1`:

> the goal is that I(S) quotiented by *declared* freedom is a singleton on
> *consumed* observables.

That sentence has a hole the size of the whole program in it: **declared
where?** Today the declaration lives in `research/metrics/freedom-register.md`
— 30 loci, each P (pinned-where-load-bearing), D (free by design), or S (free
pending selection), each with a reason. It is excellent, and it is prose, about
*this* repository, read by a human. The quotient it describes cannot be
computed, because nothing a program can read says which divergences are
latitude and which are holes.

The reconstruct-codebase skill hits the same wall from the field side. Its
"count contract separately from granted latitude" rule exists because the
partition has to be redone by hand on every target — and the cost of not
having it is recorded: one layer measured 117 and 111 divergences across two
families, ranked second on the worklist, and decomposed to **4 and 3** on
contract once a human sorted display-formatting latitude from real gaps.
Ranking by the raw count sent the operator off to pin prose while a real
defect sat elsewhere.

So the grade-2 → grade-3 loop, the convergence criterion, and the zeta
eviction lane all need the same thing: **a machine-readable declaration, per
claim, of what the claim deliberately does not pin.** The register is that
declaration promoted from prose about one repo into a field of the format
that travels with every claim.

## The sharp question: does freedom belong in the root?

The identity rule, stated as an iff in `docs/design-rationale/format3.md`:

> A byte belongs to the identity of a claim if and only if changing that byte
> can change whether some realization is accepted.

A freedom declaration **cannot reject a realization.** It says "divergence
here is expected"; it admits members, never excludes them. By the strict
reading it is guidance-shaped — it belongs out of the preimage, stripped like
`guidance` was at format 3 and step order at format 4. That is the clean
answer and it may well be the right one.

But there is a real counter-argument, and it is the same exception the format
already made once. `name` stays in the root at format 3 though it rejects
nothing, because it is the human label the claim travels under and dropping it
would collapse two differently-named claims into one root. **A freedom
declaration is a promise about what is not promised**, and that promise is
part of what the claim says to a consumer. Two boundaries with byte-identical
tests but different declared latitude are arguably different claims: a consumer
may rely on "numeric coercion is pinned" versus "numeric coercion is free"
even though no *test* distinguishes them, and the substitution experiment is
the proof that this difference is real and load-bearing — the consumer broke
on exactly the surface the dependency had left silent.

The two readings give different roots for the same tests, so this cannot be
left implicit. It is a ruling.

### My recommendation, and the reasoning

**Put it in the root, as a deliberate second exception alongside `name`** —
but only the *declaration*, never the latitude's content. Concretely: a
`[[free]]` entry names a surface (a module, a function, a behavioural axis)
and a reason string. The surface identifier is identity-bearing; the reason
string is stripped from the preimage exactly as `guidance` is, because the
*words* of the reason cannot reject anyone while the *fact that this surface
is declared free* can change what a consumer is entitled to assume.

The reasoning is the quotient framing taken literally. If the endpoint is
"singleton modulo declared freedom," then the declaration is half the
endpoint — it is not metadata about the claim, it is a term in the claim's
own definition of what it is. A claim that silently drops a freedom
declaration has become a *stronger* claim (it now promises something it used
to disclaim), and the root should move to say so, the same way adding a test
moves it. Strip the reasons so wording stays free; pin the surface list so
the promise is real.

This is the minority reading of the strict rule, and I hold it loosely. The
clean alternative — freedom entirely out of the root, a pure annotation like
the held-out battery — is defensible and cheaper, and its cost is only that
"same tests, different declared latitude" becomes "same claim," which the
substitution result suggests is a merge the format should refuse. The
keyholder decides which cost to pay.

## What the field needs from the declaration, either way

Independent of the root question, the declaration has to carry enough for a
program to partition divergences. From the skill's hard-won list:

- **A surface, not a sentence.** "numeric formatting of the FLOPs display" is
  a pattern a probe can match a divergence against; "output is
  human-facing" is not. The register's own entries are already this shape
  (`store LAYOUT is D`, `the jail's SYNTAX and backend are D`).
- **A reason, for the human who later rules on a divergence that lands
  inside it.** Free-by-design and free-pending-selection are different
  promises — the register's D versus S — and an S entry needs its watch
  condition, the thing that would turn the latitude back into a gap.
- **Consumed-observable scope.** The endpoint is singleton on *consumed*
  observables, so a freedom declaration is relative to a consumer set. A
  surface declared free is free *until a consumer depends on it* — which is
  precisely the substitution finding, and precisely why the declaration and
  the consumer-substitution audit are two halves of one mechanism. The
  honest form may be that freedom is declared on the producer claim and
  *revoked* by a consumer claim that pins the surface it needs, with the
  revocation living in the consumer's root where the substitution result
  says the knowledge belongs.

## Where this leaves the convergence criterion

With declared freedom machine-readable, "replacement-grade" becomes
computable per layer, which is the whole point:

> **probe-clean over a sealed probe battery** (cited by root, shown able to
> fail) **∧ every consumer claim re-earns with the member substituted** **∧
> every residual divergence falls inside a declared-free surface.**

The third conjunct is the one this proposal unblocks: "declared, not
discovered" is only checkable when the declaration is a field a program can
read, not a register a human maintains. Until the ruling lands, the zeta
eviction lane can *find* the contract/latitude split but cannot *apply* it
automatically, and the skill's hand-partition stays mandatory on every
target.

## Cost

A format bump: format 5, append-only like every prior one, formats 1–4
unchanged and their roots untouched. Conformance vectors for the new preimage
transform (surface pinned, reason stripped) if the root reading wins; none if
the annotation reading wins. And a migration of `freedom-register.md` from
prose into the format — which is not throwaway work, because writing the
register's 30 loci as `[[free]]` entries is the first real test of whether the
surface-identifier vocabulary is expressive enough, on the claim we understand
best. Recommended as the test case before the format is declared stable.
