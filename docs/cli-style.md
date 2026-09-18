# The CLI style contract

*Informational — the CLI's output and error conventions, stable per release. The
durable machine contract is the record ([`spec/record.md`](../spec/record.md));
see [`compatibility.md`](compatibility.md) for which promise covers which surface.*

Every verb's output and errors follow this page. The surface acceptance
suite (`criteria/surface_check.py`) pins the behaviors; this page is the
reference a future verb inherits instead of re-deriving. The model is a
mature Unix tool: git's discipline, ls's color rule, tar's streams.

## The silence rule

Print only what the user could not already know.

- **Checks** — `verify`, `audit`, `crosscheck`, `import`, `sign --check`,
  `attest --check`: success is silent, exit 0. Failure is one line on
  stderr, exit 1. Counts and tables live under `-v`.
- **Makers** print the unknowable and nothing else: `pack` and `rebuild`
  print the root (`packed 91c7...`); `rebuild` adds the cost when money
  moved. `export`, `import`, `pull`, `record`, `sign`, `attest` succeed
  silently — the target was named. `init` prints its one line (a side
  effect the user should see, git's own precedent). `run` is a silent
  wrapper: only the child's streams.
- **Views** — `status`, `help` — always speak; that is their purpose.

`-v` always speaks, in fact sheets and tables. `--json` always speaks, in
the envelope `{command, ok, status, root, data}`: the stable machine surface
for scripting a release. Human output may change without notice. The durable,
cross-version contract other programs rely on is not `--json` but the record
(`spec/record.md`) — see `docs/compatibility.md` for which promise covers
which surface.

## The `--json` payload

`--json` prints one object, always the envelope
`{command, ok, status, root, data}` — on success and on failure alike (a
failure is `ok: false`, exit 1, the JSON still on stdout, stderr empty). It is
the stable machine surface *for a given release*; the durable cross-version
contract is the record (`spec/record.md`), not this. `criteria/surface_check.py`
pins the shape.

`status` is a short verb-specific word. The values a verb emits:

| verb | `status` |
|---|---|
| `verify`, `status` | `fresh` when identity holds, `broken` when a pinned file moved |
| `audit` | `earned` when every gate reproduced, `broken` on identity failure, `reused` under `--reuse` when a prior local pass was trusted |
| `assess` | `measured` |

`data` carries the verb's full report. The fields scripts rely on:

- **verify**: `name`, `root`, `recomputed` (equal to `root` exactly when fresh),
  `phase`, `ok`.
- **audit**: `name`, `root`, `recomputed`, `elapsed`, `environment`, `layers`,
  and `gates` — a list of `{output, status, returncode, seconds, quarantine,
  detail}`, one per gate.
- **assess**: `measured`, `not_measured`, `not_applicable`, `declared`, plus
  `gate`/`gate_detail`. Each rung under `measured` carries its own sample (see
  `ret help assess`); a rung absent from `measured` is present under one of the
  other three, never silently dropped.
- **status**: the ledger groups — `fixed`, `free`, `verdicts`, `deciding`,
  `audited`, `proof`, `signatures`, `discovery`, and `next` (the one command
  that advances the claim).

One naming seam to know: the confinement backend is `quarantine` in
`audit --json` (and in the ledger, `spec/kernel-api.md`), but `sandbox` in the
record (`spec/record.md`). Same values (`seatbelt`, `bubblewrap`, `inherited`,
`none`); a parser that reuses field names across the two surfaces must map one
to the other. The names are stable; only their surfaces differ.

## Streams

Stdout carries products and reports only. Every diagnostic — errors,
warnings, hints, progress — goes to stderr. Progress appears only when
stderr is a terminal, rewrites itself in place, and is erased on success,
so the end state honors the silence rule.

## Errors

    ret: <verb>: <fact>
    hint: <the next command>

Lowercase, no trailing period, the failure class first when one applies —
the classes are `spec/verification.md`'s own vocabulary (`environment`,
`mismatch`, `timeout`, `broken`, `incomplete`), which makes them the
machine-greppable error codes. `hint:` is advice and may be ignored;
`warning:` is proceed-but-know. A refusal always has a reason; a raw
traceback is a bug in this contract.

## Color

`--color=auto|always|never`; `RETICULI_COLOR` is the env override,
`NO_COLOR` and `TERM=dumb` are respected; auto means "stdout is a tty",
decided per stream. **Information never lives only in color**: on a
terminal, class colors may replace a label word (the ls rule); wherever
color is off, the word returns.

Palette: pinned/criteria cyan, generated default, verdict files magenta,
hashes yellow, pass words green, fail words red, incomplete/environment/
undeclared yellow, meta dim, hints yellow.

## Hashes, time, paths

Hashes print as 12 hex + `...` by default, in full under `-v` and always
in `--json`. Times humanize on a terminal (`3h ago`, durations `2m14s`)
and are ISO 8601 UTC for machines. Paths print relative to the current
directory when under it, absolute otherwise.

## Exit codes

0 the operation and its predicate held; 1 the operation ran and the
predicate failed (or a refusal with a reason); 2 the invocation was
invalid. Anything finer belongs in structured output.

## Streams as arguments

`-` means the standard stream where it makes sense: `export -o -` writes
the archive to stdout, `import -` reads it from stdin, `record -o -`
writes the record JSON to stdout. Everything else stays silent so the
stream stays clean.

## Interrupts and mistakes

Ctrl-C exits 130 (128+SIGINT) with a bare newline — never a traceback; the
progress line erases itself on the way out. An unknown command gets the git
answer: `ret: 'verfy' is not a ret command. See 'ret -h'.` plus a `hint:`
naming the nearest real ones. Every refusal speaks with one voice —
`ret: <verb>: <fact>` — whatever layer it rose from.

## Status is the pure view; audit is the judge

`ret status` reads and reports — it never executes, so every form is
instant. It shows recorded state with honest dates (an audit receipt is
testimony, and only `--reuse` ever trusts one), and every view ends with
`next`: the first rung of the confidence ladder this claim has not earned
(restore → audit → assess → prove → sign → share). Earning verdicts is
`ret audit`, which judges in the STRICT jail by default — a claim's gates
never read your files, yours or a stranger's; `--no-strict` opts down.
`inspect` is retired: its jail became audit's default, its report became
status's ledger.

## The deciding set

`ret assess` leaves its measurements in the store as residue (never
identity), stamped with the root they measured. `ret status --all` reads
them back only while that root still matches, rendering the third set of
the authoring triad — evidence the declaration actually constrains
implementations — and drops its "strength unknown" line exactly then. One
truth at a time: either the evidence shows, or the ignorance does.

`ret help environment` documents every variable the tool reads.

## Deliberate non-rules

Aliases (`seal`, `inspect`, `tree`, ...) work silently — no deprecation
nag; the docs carry the migration. Tree connectors keep box-drawing
characters; the glyph ban is about information encoded in symbols, not
structure.
