# The CLI style contract

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
the envelope `{command, ok, status, root, data}`, and is the only
parse-stable output; human output may change without notice.

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

## Deliberate non-rules

Aliases (`seal`, `inspect`, `tree`, ...) work silently — no deprecation
nag; the docs carry the migration. Tree connectors keep box-drawing
characters; the glyph ban is about information encoded in symbols, not
structure.
