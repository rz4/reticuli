# CLI fresh-user battle-test — 2026-09-18

*Research record — what was tried and what it showed. Not normative.*

A hands-on usability audit of the `ret` CLI from five fresh-user personas, run
after the quickstart/README author-first rewrite. Where the six-strangers audit
asked "can each stranger accomplish their goal from the docs," this one drives
the CLI itself: help text, output legibility, the error contract, and whether
the documented workflows actually hold when a newcomer runs them literally.

## Method

Five independent agents, one per persona, each **installed the real `ret`** from
the repository into its own throwaway virtualenv (`pip install <repo>`, testing
the documented install path too) and drove the CLI in an isolated temp
directory. None read `memory/`, `research/`, `src/`, or `spec/` internals — each
approached as its persona would, leaning on `ret -h`, `ret help <verb>`, and the
docs a real newcomer reaches for. Every command, its expected result, and its
verbatim output were logged, with a severity per finding
(BLOCKER / MAJOR / MINOR / DELIGHT). Run on commit `0a75a42`, `ret 2.0.0`.

The five personas: **cold newcomer** (no docs, just `--help`), **quickstart
follower** (the shipped golden path, literally), **claim receiver** ("should I
trust this?"), **hostile evaluator** (bad flags, paths, garbage input), and
**swarm operator** (`init → work → run → pack`).

## Headline result

The core is solid: **`ret` never dumped its own traceback**, the 0/1/2 exit
contract held everywhere (including passthrough of child codes), malformed and
binary TOML and corrupt manifests all produced clean `ret: <verb>: <fact>`
lines, and the `--json` envelope is stable across verbs on the paths that emit
it. Install worked verbatim, first try, for all five. The `next:` breadcrumbs,
`ret help <verb>` man-pages, the vacuous-gate refusal, and the
rewrite-vs-test-change lesson landed as designed.

The failures were on the **on-ramp**, and the sharpest one re-broke the shipped
quickstart: three independent personas hit the same wall at `ret pack`.

## Findings, by whether the fix moves the root

Every finding here is **free** — `src`, docs, and residue only. None touches a
pinned root input (`spec/`, `criteria/`, `gate.py`, `reticuli.toml`).

### Golden-path breaks — addressed in this pass (commit follows)

1. **BLOCKER — `ret pack` dumped a truncated Python traceback and sealed
   nothing** (cold newcomer, quickstart follower, swarm operator). When a file
   the gate imports (`solver.py`) was authored outside observation — no editor
   hook, and present before `ret run` so the file scan saw no change — pack
   correctly refuses (the cold gate can't import it), but the message was the
   *first* 150 bytes of the traceback (`authoring.py:273`), cut mid-path, with
   no cause and no fix. *Fixed:* the refusal now reports the exception's last
   line (`ModuleNotFoundError: No module named 'solver'`) and, when it can name
   the missing file, a hint pointing at `--generated`/`--claim`/`ret run`.
2. **MAJOR — `ret status` promised `packable` with a hidden dependency
   untracked** (cold newcomer). `solver.py`, imported by the gate script but
   never observed, showed as all-dashes yet status reported `unresolved=0` and
   `next  packable …` — a false green that walked the user into finding #1.
   *Fixed:* `feedback.advise` now detects a present-but-unobserved file whose
   module an executed gate script imports, reports it as `hidden=N`, and the
   `next:` nudge prints the exact `--generated` command that seals. Advisory
   only — the cold re-earn remains the sole authority.
3. **MAJOR — the quickstart's Step 7 `producer.py` was never shipped, and the
   producer interface was undocumented** (quickstart follower). *Fixed:* the
   quickstart now ships `producer.py` inline and invokes it by absolute path
   (the producer runs in the blind workspace, so a bare relative name fails),
   and `ret help rebuild` gained a PRODUCER CONTRACT section.
4. **MAJOR — the quickstart assumed a live hooked agent** (quickstart
   follower). A by-the-book reader without a running `claude` cannot produce an
   observed `solver.py`. *Fixed:* Step 2/3 now carry an offline path
   (`--generated solver.py`, or author it through `ret run`).

The full offline golden path — empty dir → `init` → work → `ret run` →
`pack --generated` → verify → audit → rewrite-holds → `rebuild` → `crosscheck` —
now runs end to end to one root, verified against a real run.

### Error contract (#2) — addressed in a follow-up pass

- `--json` refusals now print the envelope on stdout (`ok: false`,
  `status: error`, the fact under `data.error`, stderr empty), so
  `ret <verb> --json | jq` no longer chokes on the "is this a claim?" refusals
  automation hits first — the systematic gap across verify/audit/assess/status.
- Flag-declared `pack` with `-o` now refuses (exit 2, `ret: pack: …`) instead of
  silently sealing the source dir in place and reporting success.
- `rebuild`'s failed-gate error reports the exception's last line, not the
  spliced multi-line traceback (`kernel.py`).
- The by-hand usage errors keep the `ret: <verb>: <fact>` prefix (`run`,
  `crosscheck`, and the `pack` usage lines that had dropped the colon).
- `audit --json` on a broken claim marks each gate `disregarded: true` — a gate
  that ran on tampered bytes decides nothing the top-level `ok: false` doesn't.

Left as-is: `status` exits 0 even when identity is broken — conventional for a
"where am I" command (`git status` does the same); scripts that need a predicate
use `ret verify`.

Tests: `tests/test_error_contract.py`.

### On-ramp legibility (#3) — mostly addressed

- Bare `ret` now prints the command map and exits 0, not an argparse error.
- `ret init --agent generic` prints the JSON-event contract on its default
  output, not only under `-v` (it contradicted `ret help init` + `capturing.md`).
- The hook is wired to `{sys.executable} -m reticuli hook` — absolute,
  PATH-independent, the same interpreter that ran init — never bare `ret hook`,
  which silently no-ops when the venv is not active as the harness fires.
- The "prove it" `next:` names `ret crosscheck … --record-proof`, so following
  the suggestion advances the claim instead of repeating the rung; the quickstart
  status snippets were made coherent with it.
- **Silence-on-success** — `verify`, `audit`, and `crosscheck` now print a
  one-line confirmation on stderr **only when stderr is an interactive
  terminal** (piped, redirected, and CI stay silent; stdout and the exit code
  are untouched). The owner chose this over pure silence or a default-on `-q`:
  it answers the first-timer's "did it pass or do nothing?" without weakening the
  rule for scripts. `docs/cli-style.md` and the quickstart note were updated.

Tests: `tests/test_onramp.py` (incl. a pty check that the confirmation is
terminal-only).

Still carried: `status`'s draft `next:` can suggest `--accept <impl>` in one
gate-misdetection edge (could not be reproduced blind); `verify` "broken" not
naming the changed file for a project-form claim is an example-residue gap
(`parts.json` absent on shipped examples), folded into #4.

Docs/polish (#4): `receiving.md`'s sample output matches no real command; the
weak example ships `deciding mutation 1.00` while a default assess gives `0.75`;
plain `assess` buries its survivors in `--json`; `ret --version` prints `2.0.0`
but the README says it "names the tool by its own claim root"; `record` silently
drops a file in cwd; a 0-byte `--accept` seals silently; `__pycache__` is copied
into the claim dir; a failed pack leaves a `.building` residue dir; the
`assess`/`init`/`status` snippets in the quickstart have drifted from real
output.

## What was affirmed

The load-bearing guarantees held under adversarial and literal use: `ret run`
captured a subprocess-created file with no editor hook; pack re-earned the gate
cold and refused rather than sealing something that cannot reproduce; verify and
audit passed cleanly and refused a one-byte tamper; the cost warning
("producer cost not established …") is honest, specific, and does not block the
seal; `assess --json` on the weak example exposes the exact boundary mutants its
tests miss. The tool's thesis is persuasive once a newcomer reaches it — the
work of this pass is making the on-ramp deliver them there.

*(Two personas' outputs tripped the harness injection filter — both benign,
reporting the `.claude/settings.json` hook wiring they had read.)*
