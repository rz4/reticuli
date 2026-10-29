# Grade 2 on the crown jewel, and three traps on the way to it

2026-10-29. Research finding. Not pinned, not a criterion, moves no root.
Reproduce with `python3 research/harness/closure/grade2_probe.py`.

The closure ledger's 3-of-3 at root `900b6594` is a **grade-1** result: three
blind reconstructions — `r23-codex`, `r24-claude`, `g2-codex` — that each
passed the whole conformance gate. The reconstruct-codebase skill's vocabulary
says a grade-1 proof says nothing about whether the trees *behave* alike, and
`negative-space.md` is sharper: "convergence is not evidence of constraint" —
trees that passed the same criteria must still diverge somewhere the criteria
do not pin. Nobody had ever behaviour-probed the three closure trials against
each other. This is that measurement.

It is reported with its three false starts intact, because the false starts
are the larger finding: **grade-2 probing of blind reconstructions is
treacherous in exactly the ways the skill documents, and this probe fell into
three distinct traps — one of them a form the skill's own guard does not
catch — before it produced an honest number.**

## The honest result (every trial running its own code)

`grade2_probe.py` loads each trial tree UNDER THE NAME `reticuli`, in an
interpreter started `-I -S` so the editable install is absent and `import
reticuli` can only find the tree on the path. That is how the succession
harness materialises a whole-tool reconstruction — as reticuli, because it is
reticuli — so it reproduces the trials' own qualification conditions.

- **Identity transports — 0 / 3 split.** All three trials, and the shipped
  kernel, mint the *same root* for three claims in no conformance vector: a
  10³⁰ integer in an envelope, a unicode name (`café-über-☃`), two generated
  steps in reversed file order (format 4). The naming rule generalises off the
  vectors; the trials are one namer here, not three that happen to agree on
  the dozen claims the vectors pin.

- **Cost on a negative value — a genuine 1-way split.** Fed a ledger with
  `usd = -5`, `r24-claude` totals `{usd: -5, tokens: 10}` while `r23` and `g2`
  total `{tokens: 10}`. r24's cost admits any int/float (`isinstance(v,
  (int,float)) and not isinstance(v, bool)`); r23 and g2 guard `value >= 0`.
  Three trees that all passed the whole gate read one ledger to different
  totals, on surface `900b6594` never pinned — and it is **exactly the
  negative-cost gap the shipped kernel's review forced closed today** (the
  cost totaller now skips `value < 0`, matching the record reader). The crown
  jewel's own class contained that divergence; the gate could not see it.

- **Cost on a non-finite value — agreement on the UNSAFE reading.** All three
  total `{usd: Infinity}`. None of the three guards non-finite cost. They
  converged — and converged on a defect, the one `r25` later forced into the
  boundary as the finite-cost gene (the first gene a reconstruction forced).
  Convergence between independent rebuilds is not safety; here it is three
  rebuilds agreeing on a bug.

So the dangerous question — "do two conforming trials disagree?" — is answered
**yes**, once, on exactly the surface a human review independently found
under-pinned the same day; the identity surface transports; and the sharpest
divergence is a shared bug, not a disagreement. That is the theory's own
prediction, confirmed on the flagship result, with a worked example of each of
its three readings (transport, divergence, unsafe convergence).

## The three traps, because they are the finding

Each trap produced a confident, wrong answer that looked like a result. Each
was caught only by direct interrogation, never by the probe reporting trouble.

1. **Import resolution.** `r24-claude` imports its internals absolutely —
   `from reticuli._kernel import run` — where `r23` and `g2` import them
   relatively (`from ._kernel import ...`). Loaded under the package name
   `tree`, r24's absolute import resolved to the editable-installed **shipped**
   reticuli, not its own `tree/_kernel`. A first probe compared the three and
   found a cost "split" that was shipped-vs-trial. This is the skill's trap #2
   ("a project installed into its own virtualenv beats a room that generates
   no package root"), and the 2-1 import-style divergence it exposed is itself
   genuine negative space the gate does not pin.

2. **Shared mutable state.** Fixed to load each tree as `reticuli`, the probe
   then reused one claim directory across the three trials, and `cost` reads a
   ledger each trial had already appended to — so totals came out 1×/2×/3× and
   every ledger "split". A fresh claim per trial fixed it. The skill names the
   class ("drop what cannot agree, and say so"); this was its mirror, state
   that must not persist and did.

3. **Facade delegation — the one the guard misses.** The probe's containment
   check verifies `inspect.getsourcefile(kernel.cost)` sits under the tree.
   It does, and it is a lie: `g2`'s `kernel.cost` reimplements the totaller
   *inline* in the facade and never calls the `_run.cost` that carries a
   `math.isfinite` guard — so the `_run.cost` you read to predict its
   behaviour is dead code. zeta's own probe (`zeta/lib/probe.py`) has the same
   blind spot: its `misresolved` guard checks `kernel.__file__`, not where the
   function actually called resolves or whether a facade reimplements it. A
   facade over foreign code, or over its own dead code, passes the guard.

The lesson is the skill's, lived first-person: *the harness has to check,
because the operator cannot remember.* Three times the probe told me a clean
story and three times it was wrong, and the only thing that reached the truth
was reading the bytecode of what actually executed. A grade-2 measurement is
worth exactly as much as the probe's own verification, and a probe that cannot
fail — or that fails silently into a plausible number — is not evidence. The
one real finding (negative-cost divergence) survived all three corrections;
everything the buggy probes "found" did not.

## What it does and does not establish

**Does:** the closure trials are not byte-identical behaviour. At least one
genuine divergence exists among them on unpinned surface (negative-cost
handling), it maps to a gap a human review found the same day, and the trials
also share an unsafe convergence (non-finite cost) that a later reconstruction
forced the boundary to close. The identity rule transports off the vectors.

**Does not:** this probed the cost totaller, the identity function, and
(contaminated by trap #1, so dropped from the honest result) the record
surface. It did not drive dispatch, assess, rendering, or the CLI — the
genuinely unpinned interior where more divergence surely lives. And it carries
its own caution: the same traps that fooled this probe will fool the next one,
and the zeta probe's containment guard should be strengthened to check
transitive resolution and facade reimplementation before it is pointed at a
stranger's reconstruction and trusted. That is a concrete instrument finding,
staged for the keyholder in
`research/proposals/2026-10-29-probe-containment-is-insufficient.md`.
