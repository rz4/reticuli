# The coverage batch: the specification says what the kernel already did

2026-10-29. Root `17733759cd4c…` → **`f2d49443a8604639ef7926182acf2e971944970a677ff7779514eec8aec123b5`**.
An **internal click** by the bar in `docs/transitions.md`: reseal + cold
gate + a fresh audit receipt + this recorded pair + a room refresh.
**Deliberately unsigned** — the signature is the ceremony, not a per-commit
stamp, and no agent signs. Raised by an outside reading of the repository;
no reconstruction forced any of it.

Five roots were minted getting here — two of the edits moved the standalone
`reference` layer and its lockfile had to be re-pinned each time, and an
adversarial review of the batch (below) sent one more spec correction
through:
`17733759` → `be17170d` → `d605049d` → `57c27dc9` → `9f9ab176` → `f2d49443`.
Only the last is sealed; the four intermediates are named so the chain has
no gap, and none of them was ever published or proved against.

## Why identity had to move

Nothing in the implementation was wrong. Every change below makes the
**specification say what the shipped kernel already did**, or adds a test
for a rule that was already load-bearing. That is still a boundary change —
a reimplementer reads `spec/`, so a spec that understates the rules admits
trees the kernel would refuse, and a spec that misstates them sends a
conforming producer down the wrong road.

### 1. Two conformance vectors for rules that were never tested

`spec/vectors/` held 21 directories, all positive roots, and none of them
exercised two preimage rules the kernel has always applied:

- **`v13-format2-manifest`** — a format-2 claim whose inputs arrive through
  `inputs_manifest`. The pinned set is the manifest file *plus every path it
  lists*. Verified to discriminate in both directions before being pinned:
  editing a listed file moves the root, and so does editing the manifest's
  own bytes, including a comment line that expansion ignores but hashing
  must not.
- **`v14-environment`** — a claim declaring `[claim] environment`, which is
  a pinned input although it never appears under `inputs`. An implementation
  treating it as metadata computes a different root.

Both agree across `reticuli.kernel` and `reticuli.reference`; `vectors_check`
now reports 21 vectors, two implementations, one answer.

### 2. The published conformance claim was too strong

`spec/vectors/README.md` and `docs/compatibility.md` both said an
implementation "conforms to the identity computation **exactly when** it
reproduces every expected value." Every vector is a positive root, so
nothing in the set exercises the **refusal surface** of `spec/identity.md` —
absolute and `..` paths, symlink components, FIFOs and devices, hardlinks
with `st_nlink > 1`, TOML date and time values. An implementation could be
21/21 and still *seal* claims the specification says must be refused, which
is the worse direction: a wrong root is caught by the next crosscheck, a
wrongly-admitted claim is caught by nothing. Both documents now say
necessary-and-not-sufficient and name the uncovered cases. Closing the gap
needs a vector kind that pins a refusal rather than a value — staged as a
dated proposal, not assumed here, because it changes the vector format.

### 3. `spec/kernel-api.md` was wrong in two rows

- **`verify(d)`** read "identity + gates re-run on present bytes". Verify
  executes no gate; `audit` is the verb that re-earns. `spec/verification.md`
  calls that division load-bearing and had already corrected the same
  sentence in *its own* table — the sweep missed this file, which is the
  table a reimplementer reads first.
- **`RECORD_FORMAT = 1`**, where the kernel and `spec/record.md` have been
  at 2 since the v2.2 revision. A kernel built from the stale constant would
  have refused every current record as newer than it understands.

### 4. Three find-and-replace artifacts

`claim.toml` → `reticuli.toml` had been applied to the *v1* side of three
"v2 not v1" sentences, which therefore read as tautologies:
`spec/kernel-api.md` ("`RECIPE = "reticuli.toml"` (v1: `reticuli.toml`)"),
`spec/claim-format.md` ("the recipe (v1: reticuli.toml)"), and
`spec/layers.md` ("`reticuli.toml` not `reticuli.toml`"). The legacy name is
`claim.toml`, confirmed against `kernel.LEGACY_RECIPE`.

### 5. `[claim] tolerance` is now in the format it belongs to

The key was normative in `spec/verification.md`, relayed in records, carried
by a pinned vector, and read by the kernel — and absent from
`spec/claim-format.md`, which owns the recipe schema. Added to the schema
block and given a section stating what belongs there: it is recipe content,
so it is inside the root, and declaring it turns the cost band from an
observation into a hard condition.

While writing it, a real defect surfaced: **`tolerance` and
`mutation_floor` were never validated at load.** `envelope` has always
refused a damaged table at parse; the other two were taken on faith and each
failed silently in its own direction. A `tolerance = "banana"` was carried
into the crosscheck, decided nothing, and the verdict came back `accept` — a
claim declaring a hard condition nobody could evaluate, which is the one
outcome the three-valued verdict exists to prevent. A non-numeric
`mutation_floor` was coerced to `None`, discarding a published bar. Both now
refuse with a reason, and the rule is stated in the validation list.

### 6. The build digest is defined where it is cited

`spec/record.md` has cited `spec/identity.md` for the build digest since
v2.2. `spec/identity.md` never carried it; the only normative-adjacent
statement was one bullet in `spec/vectors/README.md`. It now has a section:
the preimage, the four conditions a step must meet, why `from` excludes a
step, and why the pairs are sorted — with the zeta measurement that made
sorting load-bearing (an unsorted preimage survived the whole gate because
the two vectors that would have caught it shipped no generated files).

`spec/identity.md` also now states that **the pinned-input set is wider than
`[claim] inputs`**, enumerating the `environment` and `inputs_manifest`
rules that items 1 and 5 above made testable.

## What else landed, outside the root

Recorded here because the batch is one piece of work, though none of it is
identity-bearing.

**Three paths that ran a gate outside the jail, closed.** `run_gate` is
documented as the one place a gate executes, and three routes went around
it. The bundled SDK producers ran the recipe's gate with a bare
`subprocess.run(shell=True)` carrying the caller's whole environment — so
`ret rebuild`, the verb aimed at *other people's claims*, executed a
stranger's shell command against the operator's home and the vendor
credential the session was holding. Now routed through the kernel
(`producers/_gate.py`, shared by every adapter for the reason `_inputs.py`
is). This is also a fidelity fix: a producer that develops against an
unjailed gate can land an implementation that dies at the cold audit, which
this repository has already paid for once with the BSD-`diff`-spools-to-
TMPDIR seam. The launcher carried a second, drifted copy of the sandbox
profile — unescaped path interpolation where the kernel has `_quote_sb`,
`abspath` where seatbelt matches resolved paths, a bwrap arm missing `/dev`
and `/proc`, and `RETICULI_JAILED=1` where the kernel's own suite pins the
value as the backend name — and now calls `kernel.sandbox_wrap`, one policy
with two callers. `reuse.layered_audit` runs unjailed by design and said so
dishonestly: its cache key recorded the backend a jailed run *would* have
used, which also let a plain earn satisfy a lookup whose caller believed it
was reusing a jailed one. The key now says `plain`, so the two populations
cannot collide.

**The bwrap jail unshares PID and IPC.** Without a PID namespace the jail's
`/proc` is the host's, so a gate could read `/proc/<pid>/environ` of any
same-uid process — including the parent `ret` holding an API key. The
environment scrub was decorative on Linux, which is where CI runs. Probed as
a unit, with fallback, since a sandbox that is present but non-functional
counts as none.

**Strict's home mask is derived, not hardcoded.** `/home` and `/root` are
right on a stock distribution and mask *nothing* on the layouts this tool is
most likely to be audited on — a cluster's `/data/home`, an NFS or autofs
mount, a relocated `$HOME`. Strict that protects nothing while reporting
`strict` is worse than strict that is absent.

**`mutation_score` no longer reports 1.00 on a broken claim.** With a
failing baseline every mutant's audit failed for reasons unrelated to the
mutant, the loop counted them all killed, and the function returned rate
1.00 with `ok: true` against any floor — a perfect score meaning "the
harness is broken", which `docs/criteria.md` names as indistinguishable from
a working suite. It also handed each mutant the claim's *full* ceiling
instead of a time box. Now refused before the loop, so a broken claim costs
one audit instead of N, with `rate: null` and `baseline: "not earned"`.

**`cost()` skips a negative value.** The two readers of one quantity
disagreed: the record reader has always required `value >= 0` while the
totaller accepted a negative, so a ledger could total to a figure no record
could hold — and that total fed a cost band and an envelope. A negative cost
is a broken instrument, not a cheap run.

**`reuse.trusted` no longer counts the unsigned local earn as a signer.**
`quorum:k` and `signed:<id>` are documented as counting "only
cryptographically verified shared earners" and the local cache was unioned
in before either was evaluated, so `quorum:1` was satisfiable with **zero
signatures** by anything that could write `~/.cache/reticuli/earned/`. The
docstring was right and the code was wrong, which is why this is a fix.

**Stale tracked residue removed.** `.reticuli/audit.receipt.json` sat in the
repository holding root `16297fb0` — a value matching no root the claim has
ever had — read by nothing. Three implementations wrote three spellings of a
receipt (`audit.json` shipped, `audit-receipt.json` from the r3 lineages,
`audit.receipt.json` from something) and the ignore rules matched two of
them. All three are ignored now; the `.gitignore` comment had predicted this
exact failure.

**Zeta's control operators re-pinned, and one added.** The `cost()` edit
moved the line two mutant operators target, for the third time; the comment
beside them had already predicted that upkeep and said it is paid in the
open. A new operator `cost-accepts-negative` tests the gene added today, and
is staged **`unknown` rather than `killed` on purpose**: no criterion pins
the non-negativity guard yet, so if it survives that is a real finding about
a gap introduced the same day it was fixed.

## The review of this batch found four regressions in it

Recorded at length because it is the most useful part of the day. The
security changes above were written, the full gate passed, 223 tests
passed — and an adversarial review of the diff then found **four
reproducible defects the suite did not catch**, three of them introduced by
the consolidation itself. That is the obligation-placement pattern again,
one level up: the criteria judge the *claim*, and nothing judged the
bundled tooling that runs beside it.

1. **The producer gate helper cleared an ambient jail signal.** `_JAILED` is
   in `_KEEP_ENV`, so a producer launched from inside a jail — exactly what
   the self-hosting chain does, and what `criteria/build_check.py` documents
   as the outer-confinement case — inherits the signal legitimately. The
   first version of `producers/_gate.py` popped it before every call, so
   `run_gate` tried to apply a sandbox inside a sandbox: `sandbox_apply:
   Operation not permitted`, exit 71, on **every** `run_gate` the model
   makes. A producer would burn all forty turns and the layer would be
   recorded as a capability failure — a harness bug wearing the costume of
   a model that cannot code, which is the single most expensive kind of
   defect this project has. Now the non-matrix path does not touch the
   environment at all and lets `sandbox_backend()` decide; only the matrix's
   no-sandbox leg sets the signal, and it sets a backend *name* rather than
   the literal `1` this same batch had just corrected in the launcher.

2. **Consolidating the launcher's sandbox silently dropped a functional
   probe.** The launcher used to run `sandbox-exec -p <profile> true` and
   fall back to `none`; `sandbox_backend()` only ever did
   `shutil.which("sandbox-exec")`. So the consolidation traded a probed
   backend for a PATH check while the new docstring claimed "decided by
   probe, not by PATH" — false the moment it was written. Inside any outer
   seatbelt jail that does not carry `RETICULI_JAILED` (a CI runner,
   another tool's sandbox, an operator's wrapper) the launcher reported
   `seatbelt` and then died with exit 71. **The gate path had the same hole
   all along**, which is why the consolidation is a net win: `seatbelt` is
   now probed and cached exactly as `bwrap` always was, so a
   present-but-non-functional sandbox counts as `none`, honestly reported,
   on both platforms instead of neither.

3. **Collapsing two sandbox policies into one lost a distinction that was
   real.** The launcher's profile allowed writes to `/private/tmp` and
   `/private/var/folders` and the kernel's gate profile does not. That is
   not drift: a **gate** must not need scratch outside the claim (the
   witness is the `diff -u expected -` seam, which `producers/_gate.py`'s
   own docstring cites), while an **entrypoint** is a program that may
   legitimately shell out to BSD tools — and those read
   `confstr(_CS_DARWIN_USER_TEMP_DIR)`, which no `TMPDIR` redirection
   reaches. Dropping the allow broke `printf x | diff -u expected -` under
   `ret run`, verified before and after. `sandbox_wrap` now takes
   `system_tmp`, default False for gates, True from the launcher: one
   policy, two documented modes, instead of one policy and a silent
   regression.

4. **The derived strict mask could mask the host.** The `/` guard handled
   `/root` and nothing else. Measured: `HOME=/var/root` (root on macOS)
   derived `/private/var`, which denies `/private/var/select/sh` on every
   strict gate and injects a foreign error into every verdict;
   `HOME=/opt/app` derived `/opt`, which under bubblewrap tmpfs-hides
   `/opt/homebrew/bin/python3`; `HOME=/usr/local/myhome` derived
   `/usr/local`. A candidate that is a system directory, or that contains
   this interpreter or this shell, is now refused and the home directory
   itself is masked instead — a narrower promise, never a broken host.
   Re-measured across ten layouts, including the three above.

Two smaller findings from the same review, also fixed: the new validation
was **stricter than the record reader** (it refused `mutation_floor = 0`,
which `attest.record_validate` admits and a sealed claim may have declared —
recreating, for a different quantity, the two-readers-disagree defect the
batch was fixing for cost values), and `tolerance`'s real constraint is
`>= 1` rather than `> 0`, since `_in_band` reads it as `[1/t, t]` and
`tolerance = 0.5` names the empty band `[2.0, 0.5]`. And the `rate: None`
shape from fix 5 above crashed `corpus.place` with a `TypeError` — reached
by no current caller, so latent, but a refused measurement must place to
nothing rather than to the bottom of a distribution it never entered. The
crosscheck's rejection reason also read "mutation floor" for a claim that
declared none; it now says the measurement was not possible, and says it
under `incomplete` rather than `reject`, which is where an unmeasurable
condition belongs.

**What this says about the instrument.** Every one of these passed
`gate.py`. `src/reticuli/producers/` is deliberately outside the root
(substrate, not identity) and `launcher.py` is generated, so the acceptance
boundary had no opinion about any of it — correctly, by the design's own
logic, and the cost is that the bundled tooling has no criteria. The jail
floor is pinned as a *property* for gates (`criteria/run_check.py`'s seven
planks); nothing pins that the producer's gate path and the launcher's
execution path reach the same floor. That is a candidate obligation, and it
is the honest follow-on from this batch rather than something to assert now.

## Two things this batch corrected in the project's own account of itself

Both outside the root, and both the kind of drift this project can least
afford, since its thesis is that the signed diffable text is the artifact.

1. **The closure count.** `research/metrics/closure-ledger.md` ended at
   "**3 of 3** at root `900b6594`" and the README repeated it, while the live
   provenance records read 1 of 3 (r26, at `f9b292af`) and then 0 of 3 (r33,
   at `3302eb8a`). Eight adopted boundary changes have intervened since
   `900b6594`, and condition 7 resets the count on each. The ledger now
   carries the whole post-`900b6594` history, and the headline is stated
   where a reader meets it: **0 of 3 at the current root, with no trial ever
   run against it.** The three `900b6594` trials remain sealed and verify
   today — that result stands at the root that earned it. Two bookkeeping
   gaps are labelled rather than patched over: r25's qualification never got
   a provenance record (its sealed claim is the evidence, which is the
   stronger artifact, but the ledger row did not exist), and **the four root
   moves after r33 landed with no provenance record at all**, skipping the
   step this file is. The pairs are recoverable from git; they were not
   recoverable from where the ritual says to look.

2. **Zeta's self-description.** `zeta/README.md` said "every entry is
   undeclared and the promotion ledger is empty" and that "the ranker has not
   yet been shown to rank anything" — both contradicted by the same file
   higher up and by `zeta/promoted/ledger.jsonl`, which holds three
   keyholder-signed promotions. One clause signed out of that pressure
   (`the_band_is_closed`) went on to refuse a stranger from a different model
   family at r33, which is the strongest thing zeta has done and the ledger
   said it had done nothing. Corrected in place, as a correction.

## Re-earned

```
python3 gate.py                      repo-ok, ~1m20s, 17 suites (kernel_parity stages 8 more)
ret verify .                         f2d49443a860…, fresh
ret audit .                          verdict = earned, quarantine = seatbelt, ~1m22s
pytest tests/                        223 passed
zeta/gate.py                         zeta-ok, 8 suites
zeta/cli.py population               rebuilt at f2d49443; every reconstruction retired
```

Plus the differential checks the review's findings demanded, each run
before and after the fix: a producer gate call from inside an outer
seatbelt jail (exit 71 → exit 0, ambient signal preserved);
`sandbox_backend()` inside an un-signalled outer jail (`seatbelt` →
`none`); `printf x | diff -u e.txt -` under the launcher wrap and under the
gate wrap (works / blocked, which is the intended split); strict gates
under `HOME=/var/root`, `/opt/app` and `/Users/…` (clean stderr in all
three); `mutation_score` on a healthy and a broken claim (0.80/earned and
None/not-earned); and `corpus.place` on a refused score (no `TypeError`).

The population retiring is the documented coupling, not a surprise: a root
move retires every member earned against the old boundary, and only the
authored tree is a current-root member until trials are re-run. Zeta reports
`singleton` and refuses to mint a finding from a population of one, which is
the guard working.

## Not done, and whose call it is

- **The outside re-earn (condition 5).** `research/harness/closure/receipts/`
  is still empty. Unchanged by this batch and the one thing that converts the
  self-hosting result from a laboratory result.
- **Refusal vectors.** Staged as a dated proposal. Needs a reason-code
  vocabulary on `ClaimError` and a way to ship a hostile symlink inside a
  claim whose own rules refuse to hash one.
- **The `_seam()` private-name pins.** Sixteen criteria files assert that the
  kernel exports specific *private* helper names, so membership currently
  depends on this repository's internal spelling — against the identity rule
  the format-3 and format-4 strips were derived from, and against the lesson
  `_util.py`'s docstring records. Measured today rather than argued: renaming
  one private helper consistently (`_quote_sb` → `_sb_quote`, closed over
  every reference, identical behavior, same sandbox backend) is **refused** by
  `run_check.py` with "must export callable `_quote_sb`". Staged as a
  proposal, not landed, because dropping a pin **widens** the class and that
  is a keyholder ruling rather than a maintainer's correction.
