# Self-rebuild completeness audit — 2026-09-18

*Research record — what was tried and what it showed. Not normative.*

The motivating question, in the owner's words: if we rebuilt reticuli from the
current pinned criteria, would we get a *functionally equivalent* reticuli — the
same CLI, the same machine surface — or only a program that happens to pass the
gate? The root `c1f98059` excludes `src/` by design, so a from-criteria rebuild
is free to write any implementation it likes. The question is how much of what
we *experience* as reticuli is actually forced by the criteria, and how much is
free variation the criteria never nail down.

This audit answers that by measuring, on the one piece of software we understand
best. It also runs, cheaply and for real, the producer-independence experiment
the criteria exist to make possible.

## Method

Three passes, all free except the last:

1. **Static.** Enumerate exactly what the root pins (spec/, criteria/, gate.py,
   reticuli.toml, scripts/selfclaim.py) versus the CLI's actual machine surface
   as built (cli.py and the style contract). A "gap" is any machine-facing
   behavior or documented CLI structure a conforming rebuild could diverge on —
   *excluding* the behaviors `spec/verification.md:144-189` declares free.
2. **Dynamic.** Probe the running CLI to confirm each candidate gap, and for the
   two sharpest, *mutation-prove* them: revert the behavior on a copy of `src/`
   and run the real `criteria/surface_check.py` against the copy. If the
   criterion still passes, the behavior is genuinely unpinned.
3. **Fixpoint + producer independence.** Confirm the current tree still is
   `c1f98059` under a cold self-audit, then rebuild a small claim with a real
   cross-vendor producer (`--producer openai`, gpt-5) and crosscheck.

## Result 1 — a rebuild would grow a recognizably identical CLI

This corrects the working assumption. The CLI is **far** more pinned than "the
criteria only test the kernel." `criteria/surface_check.py` is itself a pinned
input, run by `gate.py`, and it ratifies a large machine surface. A from-criteria
rebuild is forced to reproduce:

- **The fourteen-verb grammar** and its five concept groups in workflow order;
  the exact split of porcelain / aliases / plumbing (`cli.verbs()` must equal the
  union); retired v1 verbs refused with exit 2; unknown-verb near-miss suggestion.
- **The `{command, ok, status, root, data}` envelope** (top-level shape), the
  **0/1/2 exit contract**, the `ret: <verb>: <fact>` error grammar, and
  **silence-on-success** (checks silent, makers print the unknowable, views speak).
- **The color contract** (auto=tty, `RETICULI_COLOR` always/never, label word
  returns when color is off) and a banned-glyph sweep over all output.
- **Two-level help**, `--version` starting `ret `, parser-generated completion,
  and `help environment` naming every `RETICULI_*` variable.
- **The record format** — the one file third parties may parse — pinned twice:
  normatively in `spec/record.md` (a pinned input) and executably in
  `kernel_check.py` / `exchange_check.py`. Closed member sets, canonical bytes,
  the gate and sandbox vocabularies.
- **A second machine surface**: `launcher_check.py` pins launcher exit codes 3–7,
  the `package.toml` contract, the run/strip/ls verbs, and stdout purity.
- **The self-hosting chain**: six layer roots pinned to a byte-exact lockfile,
  and a bootstrap that drives pack → export --blind → import → rebuild → verify →
  crosscheck end to end.

What stays free is the **wording** of each help and output line
(`surface_check.py:35`, "the wording of each line stays free") plus a documented
free list (store/ledger filenames, tolerance value, default timeout, and more, at
`spec/verification.md:144-189`). So a rebuild's CLI would read differently
sentence by sentence but be *structurally the same tool*. The earlier intuition —
"a rebuild would have a totally different CLI" — was wrong, and it was wrong
because the project already did the folding-into-criteria work for the grammar,
the envelope shape, the exit codes, and the record.

## Result 2 — the residual machine-surface gaps (the worklist)

Five behaviors that automation or an interoperating implementation depends on,
that the criteria do **not** pin, so a conforming rebuild could drop or rename
them. Two are mutation-proven.

| # | Gap | Evidence | Fix |
|---|-----|----------|-----|
| **G1** | The `--json` **refusal** envelope. On a failed predicate (exit 1, e.g. verify on a non-claim) the tool emits the envelope on stdout with `ok:false, status:"error", data.error`. `surface_check` only ever builds the envelope on *success* paths. | **Mutation-proven.** Reverting refusals to a bare stderr line (empty stdout) still passes `surface_check` (exit 0) yet gives `verify --json` zero bytes on stdout — `jq` chokes on the first thing automation does. | Assert the refusal envelope for every `--json` verb. |
| **G6** | `ret run` returns the **child's exit code unchanged** — its whole reason to exist as a CI predicate. `surface_check` only ever runs it with a *passing* command. | **Mutation-proven.** A `run()` that always returns 0 passes `surface_check`, yet turns every red build green (`run "exit 7"` → 0). | Assert `run "exit 7"` returns 7. |
| **G3** | The per-verb `data` **key sets** (audit/assess/status/pack/rebuild/sign). Documented in `docs/cli-style.md`, but docs are outside the root. `surface_check` asserts only a handful of individual fields. | Probe: `status.data` carries 15 keys (`deciding`, `discovery`, `proof`, …); none are pinned. A rebuild could rename or drop them. | Pin the load-bearing documented key set per verb. |
| **G4** | The envelope `status` **vocabulary**. Only `verify→fresh` and `crosscheck→accept` are pinned; `audit→earned/reused/failed`, `assess→measured`, `status→draft/claim/…`, `sign→signed/authorized/…` are not (the failure *classes* are pinned in spec, but not their appearance as the envelope's `status`). | Probe + read. | Pin the success `status` spelling per verb. |
| **G2** | `--json` on an **invalid invocation** (exit 2) emits *no* envelope — a bare stderr line. A deliberate seam (the verb never ran), but unpinned, so a rebuild could instead emit an envelope. | Probe: `pack … --json` with a missing `-o` → exit 2, zero bytes stdout. | Pin the seam as-is (words on stderr, exit 2, no envelope). G5, the `quarantine`/`sandbox` naming seam, folds in here. |

**The proposal.** `research/proposals/surface_json_contract_check.py` is a
runnable criterion that closes all five. It is **validated**: it passes against
the current, correct `src/`, which means folding it into
`criteria/surface_check.py` needs **no implementation change — only a root
re-seal**. Doing that fold is a root move (it edits a pinned input), so it is
left for the owner to apply, not applied here.

## Result 3 — the fixpoint holds

`ret verify .` is silent (identity fresh, root `c1f98059`), and a cold
`ret audit .` **re-earned that root in a seatbelt sandbox in 48.2s**, verdict
`earned`, gate `REPO_OK` reproduced. The tree is a fixpoint of its own criteria.
This is self-consistency, not producer independence — it says the shipped bytes
satisfy the shipped criteria, not that a from-scratch producer converges.

## Result 4 — producer independence, measured

The bounded paid run the owner authorized. On a small claim (`is_prime` over a
four-line test), `--producer openai` (gpt-5) rebuilt the implementation **from
the criteria alone, with no reference implementation in the room**:

- **Our original:** naive trial division, `all(n % k for k in range(2, n))`.
- **gpt-5's rebuild:** a structurally different program — sqrt-bounded loop,
  even-number fast path, type check, docstring, explicit negative handling.
- **Both land on root `d236f7cf`.** `crosscheck` verdict `accept`,
  `satisfied = true`.

Two implementations that share not one line of the core loop, one identity. This
is the thesis — the root names the criteria, not the code — confirmed by a
genuine cross-vendor producer, not a stand-in script. Cost: ~4,168 gpt-5 tokens
across two attempts, under $0.10 total.

This is one data point at the easy end. The natural next experiment is the curve
from the research notes: rebuild claims spanning mutation scores and plot re-earn
rate against tightness. A loose claim any producer can re-earn certifies little;
a tight one only a correct implementation can. Today's run shows the machinery
works end to end with a real model; it does not yet show where it *breaks*.

## Recommendation

1. **Fold the proposal into `criteria/surface_check.py`** as a v2.5 root move.
   It is validated against current `src/`, so the cost is a re-seal and the
   ratchet's usual re-earn — no code changes. This closes the last machine-
   surface gaps between "passes the gate" and "is the same tool," which is
   exactly what the owner's "machine + CLI structure" equivalence bar asks for.
2. **Leave the wording free.** The audit deliberately pins no help or message
   text; that freedom is what keeps the ratchet from moving the root every time
   a message improves.
3. **Scale the producer experiment.** The paid path works and is cheap at the
   small end. The completeness question for the *whole* self-rebuild — can a
   producer regrow all of `src/` and reproduce the six layer roots — remains
   open and is the real prize; it is expensive and likely to fail first at the
   tightest layers, which is where it would teach the most.

## What was affirmed

The load-bearing guarantees held: the tree re-earns its own root cold; the
record format is doubly pinned; the CLI grammar, envelope shape, exit contract,
silence, and color are all criteria, not conventions; and a real independent
producer reproduced a root from criteria alone. The gaps found are narrow and
sit at the edges of an otherwise well-pinned surface — the on-ramp work and the
six-strangers passes did their job.
