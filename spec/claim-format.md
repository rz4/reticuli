# The claim format

> **The file was named `claim.toml` before 2026-09-16.** A reader
> accepts either name, preferring `reticuli.toml`; the filename is not
> in the root preimage, so a claim sealed under the old name keeps its
> identity exactly, and a reader must keep accepting it for exactly that
> reason.

**Status: draft, extracted from the v1 recipe format. v2 renames the keys;
semantics are v1's unless a change is called out. Open questions are marked.**

A claim is a directory containing a recipe file, its pinned inputs, and
(optionally) its generated outputs and a store of residue.

```
myclaim/
├── reticuli.toml            the recipe (v1: reticuli.toml)
├── check_*.py            pinned inputs: acceptance tests
├── cases/…               pinned inputs: fixtures
├── <generated files>     the implementation — regrowable, outside identity
└── .reticuli/            store: manifest.json (name + root), ledger, residue
```

## Recipe schema

```toml
[claim]                        # v1: [record]
name = "myclaim"               # required, string
format = 1                     # optional; absent means 1 (see below)
inputs = ["check.py", "cases/c00.txt", …]   # pinned inputs, hashed into the root
requires = ["ssh-keygen"]      # optional: environment contract (binaries /
                               #   python modules the gates need on the host)
gate_timeout = 120.0           # optional: per-gate wall-clock bound (seconds);
                               #   the effective bound is min(declared, host ceiling)
mutation_floor = 0.6           # v1: teeth — optional minimum mutation-kill rate
                               #   the crosscheck must re-earn
envelope = { usd = 25.0 }      # optional: cost ceilings a redo commits to,
                               #   per unit; enforced by the three-machine test
environment = "requirements.lock"   # optional: a hash-pinned requirements
                               #   file; a pinned input, installed into a
                               #   private venv before the gates run

[[step]]
kind = "produce"               # produce | gate
output = "impl.py"
class = "generated"            # v1: free — outside the root; regrowable
guidance = "regenerate impl.py to pass the gate"  # a hint for a rebuilder;
                               #   NOT in the root at format 3 (older: `request`)

[[step]]
kind = "gate"
output = "OK"
class = "validated"            # the gate's verdict file; pinned into the root
run = "python3 check.py && printf ok > OK"
```

### Format version

`[claim] format` is an optional positive integer; **absent means 1**, so a
claim that does not declare it is a format-1 claim and keeps its identity.
Omit it unless you need it — declaring `format = 1` is legal but changes the
recipe text, and therefore the root, for no benefit.

Its purpose is diagnostic, not protective. The recipe text is already inside
the root, so a claim written in a future format cannot be mistakenly accepted
by an older kernel: the root simply will not match. But a bare hash mismatch
says nothing about *why*. A kernel that meets a `format` it does not
understand refuses in words:

    claim format 2 is newer than this kernel understands (format 1);
    upgrade reticuli to read it

### Producer guidance versus criteria (format 3)

A produce step's `guidance` (older spelling: `request`) is a hint for a
rebuilder, not a condition on its output. A **criterion** is authoritative —
it can reject a realization: the gate command, the pinned inputs and
fixtures, the environment, the declared envelope, the pinned verdicts.
**Guidance** cannot make a realization valid; it only helps a producer find
one. At **format 3** guidance is removed from the root preimage
(`spec/identity.md`), so rewording a hint does not rename the claim.

If something written as guidance actually expresses required behavior,
promote it to a criterion (a check, a fixture, a pinned spec) rather than
leaving it in a string the root ignores. Declare `format = 3` to opt in; a
format-1/2 claim keeps hashing guidance, and its root, unchanged. Both key
names are read (a producer is handed either), and `ret rebuild
--without-guidance` withholds the hint entirely, to measure what the criteria
alone carry.

### Large corpora: `inputs_manifest` (format 2)

A claim over a real corpus enumerates hundreds of paths, which makes the
recipe unreadable and its diffs useless — the TOML conformance example was 920
paths in a 44 KB recipe. Instead:

```toml
[claim]
name = "toml-1.0.0"
format = 2
inputs_manifest = "INPUTS"
```

`INPUTS` is a text file, one entry per line, optionally `<sha256>  <path>` so
it is meaningful on its own. Blank lines and `#` comments are ignored. The
same claim's recipe drops to ~1 KB.

**The manifest is itself a pinned input.** Its bytes are in the root, so
changing the corpus changes the manifest and moves the root, exactly as
enumerating the paths did. Nothing is weakened.

**It is a fixed list, never a pattern.** A wildcard evaluated when a verifier
reads the claim would make identity depend on directory contents at read time,
which is the one thing a content address cannot tolerate. A file that appears
in the directory later is not part of the claim, and a manifest naming a file
that is gone is a refusal that names it.

Declaring `format = 2` means an older kernel refuses in words rather than
reporting a bare hash mismatch. Write one with
`ret pack … --inputs-manifest INPUTS`.

### The cost envelope: `envelope`

`[claim] envelope` declares ceilings for what an independent rebuild may
cost, one per unit (`usd`, `tokens`, `calls`, `seconds`); each value must be
a positive number. **usd is the unit of commitment** — money is the one unit
comparable across producers and vendors — and the others are legal but
weaker. The table is recipe content, so the commitment is inside the root:
*these tests determine this software within this budget* becomes part of
what the claim says, falsifiable like the rest of it.

The three-machine test enforces the ceilings against M3's ledger, and this
is a different instrument from the M1↔M3 tolerance band: the band compares
two ledgers, so it can say nothing when the original was never rebuilt; the
envelope compares the redo to the claim's own commitment, so it works with
no M1 ledger at all. A measured overrun rejects. A declared unit the redo
did not measure makes the verdict **incomplete** — the condition was
declared hard, and a hard condition nobody measured has not been
demonstrated, so the test cannot accept (`spec/verification.md`, the
three-valued verdict). An under-run passes and stays visible in the
report: a redo far cheaper than the commitment is a signal about the
suite, or about leakage, and signals are read rather than raised.

Set the ceiling by measuring first: run rebuilds, read their ledgers, and
pin what they showed with honest headroom — the same discipline as every
other pin in this format.

### The environment: `environment`

When a test's outcome depends on which version of a package is installed,
that version decides what "passes" means — so it is a criterion, and it
belongs inside the root like fixture bytes. `[claim] environment` names one
file, automatically a pinned input, in the standard pip requirements format
with a `--hash=sha256:…` entry per artifact. Generate it with any tool that
emits hashes (`uv pip compile --generate-hashes`, `pip-compile
--generate-hashes`); this tool only reads it. The file is reviewable text,
and every installable artifact in it is named by its content hash — the
same move the root itself is built on. One file serves every platform,
because the format allows several hashes per package.

Verification gains a step between materializing a room and judging in it:
**furnish**. A private venv is built in the host's cache from exactly the
named artifacts — `--require-hashes`, so nothing unnamed can arrive, and
`--only-binary=:all:`, so nothing executes at install time (installing a
wheel unpacks files; it is source builds that run code). The gate then runs
as always — sandboxed, network denied, scrubbed environment — with the
venv first on its `PATH`. Furnishing may use the network: it is the
auditor's deliberate act, like cloning the repository was. A room that
cannot be furnished — no network, no wheel for this platform, a hash that
does not match — is an **environment** failure: the gates were not run,
nothing proven, nothing disproven.

Furnished environments are cached per (file digest, interpreter, platform).
The cache is host residue and never touches identity.

Scope, plainly: this covers Python packages and nothing else. System
libraries, compilers, and other runtimes remain the host contract
(`requires` — checked, not installed). Containers are not a mechanism here
— an identity should be reviewable, and an image digest is not — but a gate
that runs one is legal, with `requires = ["docker"]`. And a claim that
*wants* host-relative looseness ("any numpy") simply declares no
environment; the looseness is then visible in the recipe.

### Validation rules (v1, carried)

- `[claim] name` is required and must be a string; a non-string is refused.
- Every step needs a `kind` ∈ {`produce`, `gate`} and an `output`; a gate
  additionally needs a `run`.
- Every recipe path is confined to the claim directory (no absolute paths,
  no `..` escapes, no symlink escapes).
- A malformed recipe is a **refusal with a reason**, never a raw parse crash:
  the claim's own recipe is untrusted input.

### Step classes

| v2 | v1 | in the root? | meaning |
|---|---|---|---|
| `generated` | `free` | no | regrowable output; the implementation |
| `pinned` | `exact` | yes | output that must reproduce byte-for-byte |
| `validated` | `validated` | yes | a gate verdict: bytes earned by running the gate |

### Gate execution contract (v1, carried)

Every gate runs the same way, no matter which verb invoked it:

- **scrubbed environment** — a minimal host allowlist plus the claim's own
  variables; inherited secrets never reach a gate, and a hostile gate cannot
  exfiltrate them;
- **sandboxed** — macOS `sandbox-exec` / Linux `bwrap`, probed *functionally*
  (a present-but-nonfunctional sandbox counts as none, honestly reported);
- **bounded** — wall-clock limited by `gate_timeout` and the host ceiling;
- **given somewhere to write** — where a real sandbox is applied, the gate's
  `TMPDIR` and `HOME` point at a scratch directory inside the claim's store
  (residue: outside the root, never a declared file). Inheriting the host's
  would hand the gate paths the sandbox forbids it to write, so any gate using
  `tempfile` would fail *only* where confinement is real — passing on hosts
  with no working sandbox and failing on hosts with one. A confined gate needs
  a coherent environment, not merely a confined one;
- **vacuous gates refused** — a gate that pins no meaningful verdict is
  rejected at seal time.

A consequence worth stating for anyone writing a gate: **it must not need
scratch space outside the claim.** Measured the hard way — a gate piping into
`diff -u expected -` passed locally and on Linux CI and failed under macOS's
real sandbox with `diff: -: Operation not permitted`, because BSD diff spools
non-seekable stdin to the system temp directory. Such a gate passes on every
host without a working sandbox and fails on every host with one. Write to the
claim, or compare without a temp file at all.

### The environment contract

`[claim] requires` names what the host must provide (a binary name or a
Python module). A missing requirement classifies a gate outcome as
`environment` — the host can't run this claim — which is distinct from the
claim being wrong. See `verification.md` for all failure classes.

## The store

`.reticuli/manifest.json` is pure identity: `{name, root}`, plus optional
`proof` (a recorded crosscheck) and `components` (links to layered
sub-claims). It carries no hashes of generated outputs, so editing the
implementation never churns it.

## Decisions (settled 2026-09-15, before the first seal)

- **Recipe filename: `reticuli.toml`.** The format speaks CS; the project name
  lives in the store directory.
- **Store directory: `.reticuli/`** — the project name survived the v2
  break, so the dot-dir does too.
- **Class defaults keep v1 semantics, restated in v2 words**: a `produce`
  step defaults to `class = "generated"`; any other step output defaults to
  `class = "pinned"`. Recipes SHOULD state class explicitly anyway; the
  examples do.

## Still open

- [ ] Fold the bottom-anchored signature chain (genesis + realization
      digests) into the manifest natively rather than as a later attachment.
- [ ] **Signature namespaces — and a measured warning about deferring them.**
      The seed check carries v1's namespace *values* (`reticuli`,
      `reticuli.mint`) so v1 signatures stay verifiable, while everything
      around them speaks v2. The blind rebuild then showed that a carried
      value is contagious: reading `SIGN_NAMESPACE = "reticuli.mint"`, the
      producer named its on-disk signature directory `.reticuli/mint` —
      a v1 metaphor re-entering v2 code through the one door left open.
      Nothing is broken (the directory name is implementation-defined and
      outside every root), but it shows the cost of an open decision.
      Settling it has two tiers: the directory name is free to change today;
      the namespace strings are interop- and identity-affecting — they live
      in the check's bytes, so changing them changes the seed's root and is a
      format-versioning event, and they are the keyholder's call, not a
      refactor.
