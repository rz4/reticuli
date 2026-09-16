# The claim format

> **The file was named `claim.toml` before 2026-09-16.** A reader
> accepts either name, preferring `reticuli.toml`; the filename is not
> in the root preimage, so a claim sealed under the old name keeps its
> identity exactly. `examples/kernel-2.0/` is kept on the old name as a
> live check that this holds.

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

[[step]]
kind = "produce"               # produce | gate
output = "impl.py"
class = "generated"            # v1: free — outside the root; regrowable
request = "regenerate impl.py to pass the gate"   # prompt/instruction for a rebuilder

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
