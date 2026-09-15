# The claim format

**Status: draft, extracted from the v1 recipe format. v2 renames the keys;
semantics are v1's unless a change is called out. Open questions are marked.**

A claim is a directory containing a recipe file, its pinned inputs, and
(optionally) its generated outputs and a store of residue.

```
myclaim/
├── claim.toml            the recipe (v1: reticuli.toml)
├── check_*.py            pinned inputs: acceptance tests
├── cases/…               pinned inputs: fixtures
├── <generated files>     the implementation — regrowable, outside identity
└── .reticuli/            store: manifest.json (name + root), ledger, residue
```

## Recipe schema

```toml
[claim]                        # v1: [record]
name = "myclaim"               # required, string
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
- **vacuous gates refused** — a gate that pins no meaningful verdict is
  rejected at seal time.

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

- **Recipe filename: `claim.toml`.** The format speaks CS; the project name
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
- [ ] Signature namespaces: pinned strings, plain-CS spelling, decided before
      the first signing ceremony.
