# Changelog

All notable changes to this project are documented here. This project's
*claims* are versioned by content hash rather than by release number; when a
claim's identity moves, the entry says so and names both roots.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed
- **The CLI speaks a fourteen-verb grammar**, one concept per verb: init,
  run, status, pack / pull, export, import / verify, audit, assess /
  rebuild, crosscheck / record, sign. Six older spellings dispatch as
  accepted aliases (`seal`→pack, `hooks`→init, `inspect`→`status --all`,
  `tree`→`status --tree`, `claims`→`status --all`, `attest` stays for
  claim attestations) but only `ret help -a` lists them. Output has three
  levels: a terse default (`packed 91c7…`, `fresh 91c7…`, `earned 91c7…
  gates=9/9`), `-v` for the explanatory fact sheets, and a stable `--json`
  envelope `{command, ok, status, root, data}`. Exit codes: 0 the
  predicate held, 1 it failed, 2 the invocation was invalid. Help is
  two-level, git-style: `-h` concise, `ret help <command>`/`--help` the
  full account. New capabilities that fell out of the fold: `ret pack`
  with no flags seals a project whose `reticuli.toml` already is the
  declaration (gates must pass warm first); `ret pack --accept` packs an
  observed session and refuses unresolved observations unless `--force`;
  `ret init --agent claude` wires agent hooks at initialization (auto when
  `.claude/` is detected, `--no-agent` opts out); `ret audit --record`
  preserves the run as a record; `ret crosscheck` takes two or more
  realizations — given exactly two it materializes a real byte-copy M2 via
  export/import and says so; `ret record --sign` signs with
  `$RETICULI_KEY`; `run` accepts `ret run -- argv…`; claim arguments
  default to `.`. One breaking spelling: `pack`'s positional argument is
  now the project path (`--name` names the claim); the old
  `pack <name> -C <dir>` form still works whenever `-C` is given.
- **Every output leaf conforms to the same grammar**, verified by a
  leaf-by-leaf walk of every verb and outcome. Views speak the authoring
  triad: `ret status` counts `observed / declared / unresolved` and names
  each undeclared file; `--all` is the `path / observed / declared /
  evidence` table (dashes for untraced files — observation is never
  silently a declaration, matching what pack actually declares); `--tree`
  uses the same words. Tables drop the row index and glyphs (`true`/`false`
  and `-` instead of symbols; short roots spell `abc123...`); `status
  --all` exits by what it demonstrated, since it re-runs the gates. The
  walk also surfaced and fixed two crashes that had hidden behind rare
  leaves: packing a session whose traced file was later deleted, and
  importing a missing or unreadable archive — both now refuse with a
  reason, and `status` on a missing path refuses instead of inventing an
  empty draft. Trace events now record their provenance (`hook` or
  `shell`), which is the evidence column.
- **The maturity pass: the CLI behaves like a grown Unix tool**, under a
  written style contract (`docs/cli-style.md`). The silence rule: a passing
  check (`verify`, `audit`, `crosscheck`, `import`, the `--check` forms)
  says nothing — the exit code is the answer; makers print only the
  unknowable (`pack`/`rebuild` print the root, `rebuild` the bill); views
  speak; `run` is a silent wrapper. Every diagnostic moves to stderr,
  class-first with git-style `hint:` lines. **A broken `verify` names the
  files that moved**, from a preimage-parts residue written at seal time
  and trusted only after it re-derives the sealed root. Color, the ls way:
  `--color=auto|always|never`, `NO_COLOR`/`RETICULI_COLOR` respected, and
  on a terminal the class color may replace a label word — the word
  returns wherever color is off. `-v` spells hashes in full; long
  operations show a self-erasing elapsed line on a terminal only.
  `ret --version` names the tool by its own claim root. `-` is the
  standard stream: `ret export -o - | ret import -`, `ret record -o -`.
  `ret status` outside a workspace refuses with `hint: ret init` instead
  of inventing an empty draft. `ret completion bash|zsh` generates shell
  completion from the parser itself.
- **The cost story: producers by name, and the discovery session's bill.**
  The shipped producers answer to their names — `ret rebuild . --producer
  openai` or `anthropic:claude-opus-5` — expanding to the right invocation
  with the matched vendor key forwarded from your environment (only the
  matched key, only for shipped names, never to gates; naming the producer
  is the authorization). A missing SDK or credential refuses in one line
  before any money moves. Any other value runs verbatim: a producer stays
  any program. There is deliberately **no price table** — tables drift;
  `RETICULI_PRICE` prices tokens when you say so, and a declared usd
  envelope without a measured usd reads incomplete, honestly. And the
  claim's C1 becomes real: hooks remember the agent harness's transcript,
  and pack sums its usage entries over the session's own window — tokens
  always, usd only when the harness itself reported one — landing on the
  ledger as `session-usage`, stamped `source: agent-transcript, scope:
  session-window`. The discovery cost is deliberately larger than a
  targeted rebuild's; the gap between them is now a measurement the
  crosscheck's cost band can finally show. Only usage numbers and
  timestamps are read from the transcript, never message content.
- **Maturity II: interrupts, mistakes, and the deciding set.** Ctrl-C exits
  130 cleanly, never a traceback. An unknown command answers git-style with
  the nearest real ones (`ret: 'verfy' is not a ret command` +
  `hint: … verify`). Every refusal speaks with one voice, `ret: <verb>:
  <fact>`, whatever layer it rose from. The audit progress line names the
  gate it is on (`audit: gate 3/9 kernel_check.py 41s`) via a presentation
  callback on `kernel.audit`; `-v` reports `elapsed`. `ret help
  environment` documents every variable the tool reads, in one place. And
  the authoring triad is complete: `ret assess` leaves its measurements as
  store residue stamped with the measured root, and `ret status --all`
  renders them as the claim's **deciding** evidence — only while the root
  still matches — replacing its "strength unknown" line exactly then.
- **The repository's own root is now the acceptance boundary and only that.**
  Two moves, one reseal, no rebuild: the repository claim adopted **format 3**
  (producer guidance — the `request`/`guidance` strings — is stripped from the
  root, so rewording a hint no longer renames the claim), and the
  **promise-split** removed README, `pyproject.toml`, the logo, and the CI
  workflow from the root (changing a logo must not rename the boundary; a
  parallel commit had put them in, and this reverses that on the principle).
  The repository root moves `d9485515…` → `6061d7f1…`. Format 3 and the
  reference sealer's matching guidance strip were built earlier this cycle as
  a dormant capability; this is the repository adopting it. Held for a
  deliberate rebuild-bearing pass, by design: giving the promise its own
  context digest, migrating the kernel claim and examples to format 3, and
  pinning format 3 in the kernel's own suite (`docs/format3.md`).

### Added
- **The crosscheck verdict is three-valued: accept, reject, or incomplete.**
  A hard condition must be true to accept and rejects on false; a hard
  condition the claim *declared* but the run did not measure yields
  `incomplete`, which can never accept, because unknown evidence is not
  evidence. This corrects a defect from earlier in this cycle where a
  declared cost ceiling with no measurement passed. Observations (producer
  independence, a cost band with no shared unit) still never decide
  (`spec/verification.md`).
- **`ret inspect` reshaped to four blocks** — what is fixed (change it and
  it is a different claim), what is free (rewrite it and the claim keeps its
  name), what was demonstrated here, and what remains unknown — the
  recipient's central interface.
- **The repository claim declares its host contract**: `requires =
  ["python>=3.11", "ssh-keygen"]`, after a clean environment without
  ssh-keygen failed the exchange criterion on an undeclared dependency. A
  prerequisite that decides whether the test can be evaluated is declared or
  eliminated.

### Changed
- **The v2.3 kernel revision** (`e650b524…` → `82a81357…`): the recipe's two
  names pinned in the kernel's own suite (finding 13), the three-valued
  verdict, and a declared cost ceiling `envelope = { usd = 40.0 }` as a hard
  condition. Sealed with no proof; re-earning it is open
  (`docs/provenance/revision-2026-09-17.md`).
- Both shipped producers survive transient API outages (retry with backoff
  beyond the SDK's own retries) — added after a gateway failure killed a
  paid rebuild mid-run.

## [2.0.0] - 2026-09-17

### Added
- **A claim can carry its environment.** `[claim] environment` names a
  hash-pinned requirements file, automatically a pinned input; verification
  furnishes a private venv from exactly those artifacts (hashes required,
  wheels only) before the gates run, an unfurnishable room is an environment
  failure rather than a verdict, and furnished rooms are cached as host
  residue (`spec/claim-format.md`).
- **The authoring on-ramp.** `ret pack --pytest tests` turns an ordinary
  pytest project into a claim in one flag; `ret pack --environment` declares
  the lockfile. Judging refuses off POSIX in words, while identity keeps
  working everywhere.
- **A second shipped producer.** `reticuli.producers.anthropic` mirrors the
  OpenAI producer through the Anthropic SDK, and `docs/producers.md` carries
  the key-passing wrapper pattern proven in this repository's own runs.
- **A reusable CI workflow.** `.github/workflows/verify.yml` is a
  `workflow_call` interface — three lines in a caller's repository verify
  the root, re-earn the gates as a record, and upload it; the file is
  pinned as context, a published interface inside the identity.
- **The compatibility promise** (`docs/compatibility.md`): formats
  append-only, every past format readable forever, identity changes only
  with a format bump and attested migration, the record as the one
  contractual output, deprecation before removal.

- **The open call: regrow the kernel from its tests alone.** The branch
  `room/kernel-e650b524` is the blind room — recipe, suite, verdict,
  manifest, no implementation — built by `export --blind` and verifying at
  the target root on its own, because the claim is the identity.
  `docs/open-call.md` carries the rules, the going rate from this
  repository's own ledger, the submission protocol (your claim plus your
  signed record, verdicts re-earned here), and the honest caveats:
  blindness is procedural, declarations are declarations, and a failed
  attempt is a finding. The call opens when the keyholder's signed record
  lands beside it — signing is the human's act, and a call cannot be
  anonymous because a record cannot be unsigned.
- **Conformance vectors: the identity computation grows teeth other
  languages can bite on.** `spec/vectors/` holds fifteen tiny claims with
  their expected roots and build digests — the kernel suite's golden tables
  extracted into files, plus three vectors for hazards found since: the
  canonical recipe name (a `claim.toml`-only reader fails it, and its root
  is byte-equal to v1's because the filename is outside the preimage), an
  integer above 2^53 (exact decimal, no float round-trip), and the
  `[claim] envelope` table. `spec/vectors/run.py` points any implementation
  in any language at them; `criteria/vectors_check.py` keeps the vectors
  agreeing with both shipped implementations and proves the runner fails a
  tampered vector. The vectors are pinned into the repository's root, so
  editing one renames the repository — deliberately — and ruff now excludes
  them alongside the sealed claims.
- **The protocol pieces: a budget in the claim, a room on the wire, a record
  at the surface.** `[claim] envelope` declares cost ceilings a redo commits
  to (usd is the unit of commitment; in-root, enforced by the three-machine
  test against M3's ledger, with unmeasured units reported untested and
  under-runs visible rather than raised). `ret export --blind` writes the
  rebuilder's room — criteria, verdicts, and the manifest travel; the
  generated implementation and signing residue stay home; the room still
  verifies, because the root never covered the implementation. `ret record`
  freezes this machine's results as the one file other programs may parse,
  optionally signed in the record's own namespace, exiting nonzero when the
  gates failed so a script knows which kind of record it holds; CI now
  uploads records of each runner's results as workflow artifacts — the M2
  leg's testimony as a document. Pinned where each belongs: the blind room
  in the exchange suite, the two verbs in the surface suite (two lockfile
  lines moved, four held); the envelope's suite pin rides the next kernel
  revision alongside finding 13.
- **The v2.2 kernel revision: `4b90feef…` -> `e650b524…`.** Three behaviors
  pinned, each measured before it was demanded: a declared path may contain
  no symlink and no `..` component — the kernel and the reference sealer
  disagreed about internal links, one sealed and one refused, and an
  internal link can alias generated bytes as pinned ones; records are the
  crosscheck's second transport — a record file stands as a leg wherever a
  claim directory does, reaches the same verdict, and a recorded proof
  embeds anchored signer identities or refuses; and audit of a claim whose
  gate is itself a kernel reports completely, gate name and status and
  sandbox, never a shrug (finding 12, the v2.1 dissent). The revised suite
  passed against the living kernel on the first run. **The v2.1 proof does
  not transfer**: the claim is sealed with no proof until a fresh
  cross-vendor blind rebuild re-earns it. Only the kernel layer's self-claim
  root moved; the five above held. scripts/record_check.py served its
  purpose — battery F now lives in the kernel suite — and is deleted.
  **Re-earned the next day**: a blind `gpt-5` rebuild landed the root with
  distinct bytes, the proof is recorded, and the M3 carries the lineage's
  first full rebuild ledger (4,575,703 tokens, $25.74, three sessions with
  two host kills disclosed). The run also fixed the shipped producer, which
  had never learned the recipe's canonical name, and surfaced finding 13:
  no fixture pins the two-name recipe rule, so a `claim.toml`-only kernel
  conforms yet cannot read the claim it satisfies
  (`docs/provenance/crosscheck-v22-2026-09-17.md`).
- **Records: a signed statement of one machine's results** — the one file
  format other programs may parse. `spec/record.md` pins the document:
  canonical bytes (the identity serialization, verbatim), a closed member
  vocabulary refused in band, per-gate wall-clock deliberately outside the
  signed bytes, and a signature namespace of its own (`reticuli.record`,
  separated from attestation and mint). `reticuli.record` authors them in
  the exchange layer, whose acceptance check now demands emission that
  re-earns its gates, cost relayed with absent-means-unmeasured, and
  tamper-fatal signing. Consuming a record as a crosscheck leg is kernel
  behavior and waits for the v2.2 revision (`scripts/record_check.py`,
  battery F, staged red). The exchange layer gaining a module moved the
  self-claim roots of exchange and every layer above it; the kernel's did
  not move.
### Removed
- `examples/kernel-2.0/` — the superseded v2.0 kernel claim `d64cc301…`. Its
  proof did not transfer to `4b90feef…`, which earned its own cross-vendor
  proof separately, so it was lineage rather than evidence for anything
  current. The frozen bytes and its own README are preserved outside this
  repository; the supersession is recorded in `docs/provenance/`. A test now
  covers the legacy `claim.toml` filename it used to demonstrate.

### Changed
- **The fault injector is much wider, and now reports its own fault model.**
  It swapped operators and nothing else, which made every mutation score a
  measurement of the injector as much as of the tests: `examples/weak` scored
  0.80 while differing from its sibling implementation only in two constants —
  a fault the injector could not express. It now also injects constants
  (`n±1`, `0`), boolean and membership operators, string results, forced
  branches, dropped return values and transposed call arguments, and the score
  carries `by_kind` and `pool_by_kind` so a reader can see *where* a suite is
  blind. Sampling is stratified across fault kinds, so a small budget over a
  string-heavy program still reaches the constants.

  Widening moved the aggregates very little — `examples/weak` 0.80 → 0.77,
  quirkcalc 0.92 → 0.80, the kernel's own claim 0.50 → 0.57 — because the new
  operators bring easy kills as well as hard survivors. **The breakdown is the
  finding, not the rate**: the kernel claim kills 0 of 5 injected constants,
  and every survivor in `examples/weak` is a boundary.

  Scores from before this change are not comparable with scores after it. Both
  are residue, so no root moves.

### Fixed
- `ret pack` wrote the gate's stdout to **stdout**, where the JSON report
  lives, so `ret pack --json | jq` failed for every claim whose gate prints
  anything — which is all of them, since a check that passes silently is a
  check nobody trusts. The gate's output now goes to stderr, and its *stderr*
  is relayed too: a gate that passed while warning previously passed in
  silence.
- `ret assess` and `ret inspect` accepted no `--json`. Both already emitted
  through the JSON path; they had simply been left off the list, so the
  measurement verb and the recipient's report were the two verbs a script
  could not read.

### Added
- `tests/test_mutation.py` — pins the instrument rather than any score: every
  fault kind stays reachable, docstrings are never mutated (they are equivalent
  mutants by construction), the draw is stratified, and — with a negative
  control — a suite fitted to one value per branch survives the boundary
  mutants while a suite that probes the boundaries kills them.
- `tests/test_streams.py` — stdout carries the report, stderr carries
  everything a person reads. Pinned across `pack`, `verify`, `audit`,
  `inspect` and `assess` with a gate that is loud on both streams.
- `ret inspect` and `docs/receiving.md` — the receiving end. Re-runs the gates
  locally and prints what holds, what it does not establish, and what you are
  trusting; every other verb was written from the author's side.
- `[claim] inputs_manifest` (format 2) — a large input list moves out of the
  recipe into a pinned file. The TOML example's recipe goes from 44 KB to
  1 KB with the corpus still fully committed to. `ret pack --inputs-manifest`.
- `ret audit --reuse` — opt-in local reuse, keyed on claim AND generated
  bytes AND environment, reported as `reused` with the time it was earned.
- `docs/producers.md` and `docs/compatibility.md` — the producer contract
  (environment, cost reporting, the four causes of a failed rebuild) and
  what is stable versus what moves.
- `docs/threat-model.md` — what a claim proves and what it does not, including
  the trust boundaries and the failure modes we hit while building this.
- `examples/weak` — a deliberately weak claim: a model wrote the code and the
  tests together, both look reasonable, and two implementations with different
  behaviour carry the same root. Shows the tool detecting it, and shows what
  the mutation score misses.
- `ret assess` — measures how much a claim's tests actually constrain its code:
  circularity and mutation adequacy by default, re-derivation by a different
  model on request. Descriptive: it reports numbers and names what it did not
  measure, distinguishing "not measured" from "not applicable". `ret pack --by`
  records who produced the original so independence has something to compare.
- `ret assess --heldout FRACTION --heldout-producer NAME=COMMAND` — the
  generalization rung, no longer permanently "not measured". Hides a fraction
  of the claim's case corpus, re-seals on the rest (a different root: fewer
  inputs, the same gate), has each producer regrow the implementation blind
  from the kept cases, and judges every rebuild on the hidden cases one at a
  time. Reports a held-out pass rate per producer and, for two or more, the
  excess agreement `a - (p1·p2 + (1-p1)(1-p2))` — above zero means the
  producers share structure the claim never named. The split is seeded from the
  claim's root, so it reproduces and cannot be shopped for; everything runs on
  copies, so the measured claim is never touched.
- `docs/quickstart.md` — ten minutes, no API key, no model.
- `examples/make` — a claim whose producer is a compiler. Two compiler
  settings produce different binaries carrying the same root; CI asserts both
  halves. **A producer does not have to be a language model**, and used this
  way the toolchain is a build verifier.
- `[claim] format`, an optional version field (absent means 1, so no existing
  claim changed identity). Diagnostic only: a future-format claim already
  fails to verify under an older kernel, but now it refuses in words.
- The toolchain above the kernel: exchange, authoring, agents, launcher and
  the `ret` command line, each with its own acceptance suite.
- `examples/tomli` — a claim over a conforming TOML 1.0.0 parser, judged by
  709 cases from the external toml-test corpus. tomli 2.3.1 and CPython's
  stdlib `tomllib` are members; tomli 2.4.1 is not (it implements TOML 1.1.0).
- `examples/self` — the repository sealed as six layered claims, deep-audited.
- Packaging (`pip install .`, the `ret` entry point) and CI across macOS and
  Linux on CPython 3.11–3.13.

### Changed
- **The kernel claim moved: `d64cc301…` → `4b90feef…`.** The acceptance suite
  now pins seven behaviors that were measured to be under-specified, two of
  which two independently synthesized kernels disagreed about. The predecessor
  is kept, proven and verifying, at `examples/kernel-2.0/`; the proof did
  not transfer and was re-earned against the revised suite.
- Repository layout now follows Python conventions: `src/`, `tests/`, `docs/`,
  `scripts/`, plus `criteria/` for the identity-bearing suites and claims.
  No claim identity changed — declared paths are claim-relative.

### Fixed
- Refusals name what they refused. A malformed recipe now reports the file, a
  gate missing its output reports which step and its command, and `pack`
  failing to match generated files lists the patterns it tried, the directory
  they were relative to, and how many files `--input` already claimed.
- Materializing a generated output preserves its permission bits, so a claim
  whose output is an executable can be audited at all (it previously failed
  with "Permission denied" the moment it was copied to a workspace).
- Acceptance suites write a verdict file only when running as a claim's gate,
  instead of dropping one into whatever directory invoked them.
- A kernel applying a sandbox now exports `RETICULI_JAILED`, so a gate that
  itself runs claims inherits the sandbox instead of failing to nest.
- Sandboxed gates get a writable `TMPDIR`/`HOME` inside the claim.
- `cost()` totals wall-clock again, and the cost envelope compares exactly one
  unit — the strongest both machines measured.
- Authoring no longer pins case-folded filenames, which had made the same
  session seal to different roots on case-insensitive filesystems.
