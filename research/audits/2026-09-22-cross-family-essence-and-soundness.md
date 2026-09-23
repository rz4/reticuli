# Cross-family reading of reticuli: the essence, and three soundness gaps

*2026-09-22. Two independent models — Claude (Anthropic) and gpt-6-astra
(OpenAI, via the codex producer) — read the real implementation and spec, not a
summary, and were asked what reticuli essentially is and where the code betrays
that idea. astra found the three gaps below by reading and executing against a
copy; each was then verified in the source by Claude. This is a review, not a
contract.*

## The essence (converged)

Both readings, from different angles, reached the same core: reticuli separates
three things normally fused —

- the **criterion**: the declared acceptance procedure (what must be true),
- the **candidate**: any implementation satisfying it (replaceable, and
  excluded from the name — `identity.py` skips `class == "generated"`),
- the **authority**: who may change the criterion (a keyholder, never a
  producer).

The root names the criterion; implementations are disposable candidates; only a
keyholder moves the criterion. The purpose the code reveals: **make software
commitments survive the loss of their implementations and authors** — the
durable possession is not the code but the ability to demand and recognize
another satisfactory realization, and the authority to judge it.

astra's sharpening, accepted: the root is **the identity of a declared
experiment, not a semantic name for behavior.** Two suites that accept the same
programs but are written differently get different roots. Root equality means
"same question," never "correct answer"; membership among passing answers is a
separate check (audit).

Two one-line phrasings, complementary:
- *Git names bytes; reticuli names the test those bytes must pass — the name is
  the criterion, purified of everything that cannot change what is accepted.*
- *Preserve an executable obligation so its answers can be replaced without
  surrendering the authority to judge them.*

The through-line of the gaps below: reticuli's discipline is purifying the name
down to exactly what decides acceptance — and each gap is a place where
something that should not affect the verdict leaks in, or an identity guarantee
is not enforced.

## Finding A — excluded guidance can decide acceptance (deepest)

**Claim.** At format 3, producer guidance is stripped from the root preimage:
two claims differing only in guidance have the same root, which `spec/identity.md`
justifies as "a byte of guidance cannot change whether any realization passes —
the gate does that." **That absolute is false as implemented:** the judging room
receives the guidance-bearing recipe, so a gate that reads it can accept
differently for the same root.

**Mechanism (verified in code).**
- `_kernel/identity.py` `_preimage_recipe` removes `guidance`/`request` from
  every step before serializing the recipe into the root (format 3). So guidance
  is *not* in the root.
- `_kernel/build.py` `_materialize` (lines ~80–81) copies the **actual recipe
  file** — guidance included — into the workspace under its real name, because
  some gates legitimately name the recipe ("a gate that names it would not find
  it"). `audit` and `rebuild` both materialize this way.
- Gates run in that workspace. Nothing scopes what a gate may read, so a gate
  can read the guidance the root does not cover.

**Reproducible vector.** A claim (format 3) whose gate reads its own guidance:

    # check.py
    import tomllib
    g = tomllib.load(open("reticuli.toml", "rb"))["step"][0].get("guidance", "")
    open("OK", "w").write("ok") if g == "yes" else exit(1)

Seal two copies differing only in `guidance = "yes"` vs `"no"`. Both compute the
**same root** (guidance stripped). `audit` passes the first and fails the
second — same root, different acceptance. (astra ran exactly this under the
Seatbelt sandbox and observed the flip; all 17 identity vectors still matched,
so the serialization is conforming — the gap is in what reaches the room, not in
the hash.)

**Corollary.** The guidance-blind rebuild (`_produce(..., guidance=False)`)
withholds the environment hint but leaves the same guidance readable in the
recipe on disk, so the "blind" rebuild is not blind to guidance a producer
chooses to read.

**Reproduced by execution (2026-09-23).** A minimal format-3 claim
(`research/audits/finding-a-repro/`) whose gate reads its recipe's guidance:
sealed with `guidance = "yes"` it audits PASS at root `4ce14d04e3fd…`; editing
only the guidance to `"no"` (no reseal) leaves `verify` passing and the manifest
root **identical**, yet `audit` now FAILS. Same root, acceptance flipped — the
counterexample runs.

**Fix (small, and it *increases* essence-fidelity).** Materialize the
guidance-stripped recipe into the room — write `_preimage_recipe(recipe)` (or
strip the guidance keys from the copied recipe) instead of the raw file — so the
room sees exactly the recipe the root was computed from. The recipe stays
present under its real name for gates that reference it; only the
non-identity-bearing guidance is removed. Materialization is not hashed, so no
root moves; audit outcomes change only for claims whose gates read guidance
(i.e., only the pathological case this closes). This is an identity-level
alignment (it changes what a judging room contains), so it is a keyholder
decision, but it makes the room match the name — the essence, enforced.

## Finding B — rebuild can succeed at changing the question

`_kernel/build.py` (rebuild, ~line 414) runs the gates and then `manifest =
seal(dest)`, returning whatever root the dest sealed to, with **no assertion
that it equals the source root** and no comparison of regenerated verdicts to
the source's pinned bytes. Inputs and pinned outputs are materialized read-only
from the source and the producer is expected to touch only generated files — but
nothing enforces it, so a producer that alters a pinned input or the recipe
yields a dest that seals to a *different* root, and rebuild reports that root as
success. "Rebuild succeeded" therefore means "produced a self-consistent claim,"
not "reproduced this claim." `crosscheck` catches the divergence afterward, but
the guarantee should not depend on a second step. **Fix:** after sealing the
dest, assert `dest_root == source_root` (recomputed), and fail the rebuild
otherwise.

## Finding C — portable evidence loses obligations

`_kernel/crosscheck.py` (~line 130) populates `claim_table` **only when M1 is a
directory**; when M1 is a record, it stays empty, so the claim's declared
tolerance, cost envelope, and mutation floor are not consulted. `spec/record.md`
promises "one predicate, two transports" — a crosscheck over records reaches
exactly the verdict it would over the directories. That promise does not hold:
directory→record substitution can silently drop conditions that would reject.
**Fix:** carry the claim's declared obligations into the record and read them
from it, or refuse a record M1 that lacks them, so the record transport enforces
the same conditions as the directory.

## Finding D — held-out success is read as causal attribution (methodological)

`heldout.py` (~line 11) explains high held-out success as evidence that the
retained cases *carried* the behavior, and near-zero excess agreement as the
claim *accounting for* the agreement. Those observations cannot establish that
causal attribution: correlated success across producers can reflect shared
training, common item difficulty, or the structure of the evaluation set just as
well as a criterion that determines the behavior. The measurements are useful;
the interpretation overreaches. This is the same failure mode the quirkcalc
shared-miss result demonstrated — agreement is not correctness — stated here as a
caution on how the existing tooling narrates its own numbers.

## Finding E — the record's contamination check overreaches (methodological)

`spec/record.md` treats comparing a producer's declared training cutoff against
a call's publication date as answering "could this producer have seen the
original?" It supports only a conditional inference: earlier versions, private
access, retrieval augmentation, later fine-tuning, and simply inaccurate
declarations all escape the comparison, and a signature authenticates an
assertion — it does not expand what the signer observed. Useful as one signal;
not a contamination guarantee. Relevant to any clean-room / provenance use (see
`research/design/future-cross-family-substitution.md`).

## Status

Findings A–C are verified soundness gaps against the current source; D and E are
methodological over-claims in how the tooling and spec narrate their evidence. A is the one that touches the
identity guarantee directly (the room the gate judges in does not match the
criterion the root names); B and C are defense-in-depth and a spec-promise
repair. Acting on A or B is a root-affecting, keyholder transition; C is a
record/crosscheck change. None is scheduled here — this note records what the
cross-family reading found.
