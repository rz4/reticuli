# CLI reference

Generated from the tool's own help text by `docs/transcribe.py`; regenerated on every docs build.

```text
usage: ret <command> [<args>]

Reticuli records and reproduces software claims.

Authoring
    init        initialize a workspace
    run         run and observe a command
    status      show work, claims, and unresolved inputs
    pack        create a claim from a project

Composition and transport
    pull        add another claim as a dependency
    export      write a portable claim archive
    import      restore a claim archive

Verification
    verify      verify claim identity
    audit       rerun acceptance criteria
    assess      measure specification strength

Reconstruction
    rebuild     rebuild an implementation from a claim
    crosscheck  compare independent realizations

Evidence
    record      write an execution record
    sign        authorize a claim or proof

positional arguments:
  <command>

options:
  -h, --help  show this help message and exit

See 'ret <command> -h' for command usage.
See 'ret help <command>' for detailed help; 'ret help -a' lists everything,
including accepted older spellings.
```

## `ret init`

```text
NAME
    ret init — initialize a workspace

SYNOPSIS
    ret init [<path>] [--agent <name> | --no-agent]

DESCRIPTION
    Creates the session store (.reticuli/), the trace file, and git-native
    skin (.gitignore/.gitattributes entries for local residue). When a
    supported coding-agent environment is detected — a .claude/ directory —
    the nonblocking observation hooks are installed idempotently; --agent
    claude forces that, --no-agent skips it. The wired command adapts to how
    reticuli is reachable (the installed `ret`, or this interpreter's `-m
    reticuli` from a source checkout), so hooks are never wired to a command
    that is not there. For any other harness, --agent generic sets up the
    workspace and prints the contract to target: run `ret hook` at each event
    with a JSON event on stdin ({"event":"write"|"read"|"bash"|"prompt", ...}).
    Observation discovers possible dependencies; nothing observed becomes part
    of a claim until declared.

EXIT STATUS
    0 initialized; 1 refused (with a reason); 2 invalid invocation.
```

## `ret run`

```text
NAME
    ret run — run and observe a command

SYNOPSIS
    ret run <command> [-C <workspace>]
    ret run -- <argv>...

DESCRIPTION
    Executes the command in the workspace and appends it to the session
    trace. Useful even when agent hooks are present: it is an explicit,
    human-authored execution boundary. The child's exit code is returned
    unchanged.
```

## `ret status`

```text
NAME
    ret status — where am I, and what's next

SYNOPSIS
    ret status [<path>] [--files] [--tree] [--all] [--json]

DESCRIPTION
    The pure view: status reads and reports, it never executes anything —
    every form is instant. In a draft session it counts the authoring
    triad (observed, declared, unresolved) and names each undeclared
    file. On a sealed claim it shows the recorded state with honest
    dates: identity (a hash comparison), when this machine last EARNED
    the verdicts (audit's receipt — testimony, not a verdict), the
    tests' measured strength (assess's evidence), whether a proof is
    recorded, and what is signed. Every view ends with `next`: the
    first rung of the ladder this claim has not yet earned.

    --files is the per-file account: what each file is to this claim.
    --tree is the dependency and evidence graph. --all is everything on
    one page. Earning a verdict is `ret audit`; measuring the tests is
    `ret assess`; status only ever tells you which is next.

    Observation is not complete provenance, and a receipt is not a
    verdict: status reports what was seen and what is recorded; it
    never implies the rest.

EXIT STATUS
    0 (a view); 1 the path holds no readable state; 2 invalid invocation.
```

## `ret pack`

```text
NAME
    ret pack — create a claim from a project

SYNOPSIS
    ret pack [<path>] [-o <directory>] [--name <name>] [--force]
    ret pack [<path>] --accept <verdict>... -o <directory>       (a session)
    ret pack [<path>] --generated <glob>... --gate <cmd> --output <verdict>
    ret pack [<path>] --generated <glob>... --pytest <dir>

DESCRIPTION
    The single authoring boundary: observed work or a declared project
    becomes a claim. Three sources, one verb:

    - A directory with reticuli.toml and no build flags: the recipe IS the
      declaration; the gates run warm and the claim seals in place. The
      specification belongs in reticuli.toml, not in a growing flag language.
    - A draft session (an observed trace): --accept names the verdict files
      that decide acceptance, -o is where the claim materializes; the gates
      re-run COLD in a clean workspace, so the trace has no authority. A
      session with unresolved observations is refused unless --force.
    - A project declared by flags: --generated (the implementation), --input
      (pinned criteria), --gate/--output or --pytest, plus --environment,
      --component, --requires, --mutation-floor, --inputs-manifest, --by.

    Acceptance criteria must pass before the claim is created, in every path.

EXIT STATUS
    0 packed; 1 the gates or the declaration refused; 2 invalid invocation.
```

## `ret pull`

```text
NAME
    ret pull — add another claim as a dependency

SYNOPSIS
    ret pull [<claim>] [-C <into>]

DESCRIPTION
    Copies a sealed claim into this workspace's claim store and registers it
    as a dependency. Pull changes the dependency graph; export/import move
    bytes without composition semantics — that is the difference.

    A pull copies the component BY VALUE: the drawer copy and the manifest
    link freeze the component as it stood. The component's name is the
    mutable pointer; its root is the immutable value the link records.

    With no claim named, pull re-walks every wire instead: run in the
    directory whose subdirectories are the composition's claims, it finds
    each dependent whose view of a sibling went stale (the sibling resealed
    to a new root, or re-linked under the same root), re-pulls the sibling
    into the dependent's drawer, and reseals the dependent warm — bottom-up
    in dependency order, which the graph itself decides. pack moves roots,
    deliberately, one claim at a time; a no-argument pull never moves one —
    supplied files are generated, outside the dependent's root — and
    refuses, naming the file, where a reseal would. A gate that rejects the
    refreshed bytes stops the walk at that layer: the composition genuinely
    broke, and the first refusing layer says where. Recorded proofs on
    refreshed claims predate the new component bytes; the report says so
    rather than re-earning them. `ret status` in the same directory is the
    matching pure view: it shows the stale wires and repairs nothing.

EXIT STATUS
    0 pulled, or the composition is coherent; 1 a reseal refused or a gate
    failed; 2 invalid invocation.
```

## `ret export`

```text
NAME
    ret export — write a portable claim archive

SYNOPSIS
    ret export [<claim>] [<archive>] [-o <archive>] [--blind]

DESCRIPTION
    Writes the claim's declared content to a deterministic tar. No
    dependency semantics. --blind writes the rebuilder's room: criteria,
    verdicts, and the manifest travel; the generated implementation stays
    home — the root never covered it, so the room still verifies.
    The archive defaults to <name>.tar in the current directory.
```

## `ret import`

```text
NAME
    ret import — restore a claim archive

SYNOPSIS
    ret import <archive> [<directory>] [-o <directory>]

DESCRIPTION
    Extracts an archive into a new directory and verifies the root from the
    bytes alone. Restores a portable claim without adding it as a
    dependency (that is pull). export and import are as close to inverses
    as practical.

EXIT STATUS
    0 imported and fresh; 1 the extracted bytes do not verify; 2 invalid.
```

## `ret verify`

```text
NAME
    ret verify — verify claim identity

SYNOPSIS
    ret verify [<claim>] [--json]

DESCRIPTION
    Recomputes the claim root from its declared contents and compares it
    with the sealed manifest. Does not execute acceptance criteria — this
    answers "is this still the same claim?", in milliseconds, and nothing
    else. audit answers whether the bytes currently earn the verdict.

OUTPUT
    fresh <root>                       the identity holds
    broken expected=<root> got=<root>  a declared byte changed

EXIT STATUS
    0 fresh; 1 broken; 2 invalid invocation.
```

## `ret audit`

```text
NAME
    ret audit — rerun acceptance criteria

SYNOPSIS
    ret audit [<claim>] [--record [<file>]] [--shallow] [--mutants N]
              [--reuse] [--no-strict] [--json]

DESCRIPTION
    Re-executes every gate in a sandboxed scratch workspace built from the
    claim's declared files: do these bytes currently earn the declared
    verdict? An environment failure (a missing declared requirement, an
    unfurnishable declared environment) is distinct from the claim failing:
    the gates were not run, nothing proven, nothing disproven.

    Auditing is the act of judging bytes, so the gates run under the
    STRICT jail by default: writes confined, network denied, and your
    own files masked — a claim's gates never get to read your home
    directory while you judge them, yours or a stranger's. --no-strict
    opts down to the standard jail. This is the receiving flow: someone
    hands you a claim, `ret audit theirclaim` is the answer, and
    `ret status --all` is the account of what you are trusting.

    An earned audit leaves a dated receipt in the claim's store; status
    reports it (only while the root still matches), and nothing but
    --reuse ever trusts it.

    --record preserves the execution as a portable record (spec/record.md)
    — a convenience; `ret record` remains the full evidence verb.
    --shallow audits this claim only, skipping its component chain.
    --reuse accepts this machine's own prior earned verdict for identical
    bytes, reported as reused, never as earned.

OUTPUT
    earned <root> gates=N/N            every verdict reproduced
    failed gate=<name>                 a criterion rejected the bytes
    environment missing=<what>         this host cannot test the claim

EXIT STATUS
    0 earned (or honestly reused); 1 anything else; 2 invalid invocation.
```

## `ret assess`

```text
NAME
    ret assess — measure specification strength

SYNOPSIS
    ret assess [<claim>] [--mutants N] [--rebuild <producer> [--guided]]
               [--heldout F --heldout-producer NAME=CMD ...] [--json]

DESCRIPTION
    Attacks the specification itself: verify asks whether identity
    survived, audit asks whether this implementation passes, assess asks
    whether the acceptance boundary is meaningful. Measurements include
    fault injection (mutation), gate circularity, blind re-derivation from
    the tests alone (--guided adds a guided control), held-out
    generalization, producer independence, and
    excess cross-producer agreement. Numbers are reported with their
    samples and never collapsed into a grade — the output is evidence for
    refining the specification. Does not change the claim: the root never
    moves; the measurements are left in the store as residue, and
    `ret status --all` reads them back as the claim's DECIDING evidence
    (trusted only while their recorded root still matches).
```

## `ret rebuild`

```text
NAME
    ret rebuild — rebuild an implementation from a claim

SYNOPSIS
    ret rebuild [<claim>] --producer <name>[:<model>] [-o <directory>]
    ret rebuild [<claim>] --producer <command> [-o <directory>]
                [--recursive] [--without-guidance]

DESCRIPTION
    Builds a new implementation from the claim in a blind workspace.
    Generated implementation files from the source realization are
    withheld from the producer — it writes them from the criteria (and, by
    default, the recipe's guidance). --without-guidance withholds the
    hints too, measuring what the criteria alone carry; at claim format 3
    guidance is outside the root, so both target the same root.

    The shipped producers answer to their names, in two families. The SDK
    producers `--producer openai` and `--producer anthropic:claude-opus-5`
    call an API directly; naming one authorizes forwarding its own vendor's
    key (OPENAI_API_KEY / ANTHROPIC_API_KEY) from your environment — only
    the matched key, never to gates — and a missing SDK or credential
    refuses in one line before any money moves. The CLI producers
    `--producer codex` and `--producer claude:sonnet` drive an
    already-signed-in command instead, so there is no key of ours to
    forward; a missing binary refuses the same way. Either family takes
    `:model` to pin the oracle, and either way the model is recorded as
    `observed` when the tool's own record names it.

    Set RETICULI_PRICE ("in,out" usd/Mtok) if you want dollars in the
    ledger; without it tokens are recorded and a declared usd envelope reads
    incomplete, honestly. A CLI producer billed to a subscription has no
    per-token line at all and says so rather than inventing one.

    Any other value is run verbatim as a command — a producer is any
    program, a compiler and a Makefile included.

    PRODUCER CONTRACT
    A command producer is run with its working directory set to the blind
    workspace: the criteria and (by default) the recipe's guidance are
    already there, the generated implementation files are not. The command
    must write those implementation files into that directory — that is its
    whole job. Its exit code is ignored; the rebuilt claim is judged only by
    re-running the gates cold, so a producer that writes nothing (or the
    wrong bytes) simply fails to reach the source root. A minimal offline
    producer is a script that emits the withheld file, e.g.
    `--producer "python3 producer.py"` where producer.py writes solver.py.

    A claim can have arbitrarily many rebuilds; disagreement between
    producers is information about the specification. Every gate re-runs;
    the cost is ledgered.
```

## `ret crosscheck`

```text
NAME
    ret crosscheck — compare independent realizations

SYNOPSIS
    ret crosscheck <realization> <realization>... [--record-proof]
                   [--mutants N]

DESCRIPTION
    The three-machine test over realizations of one claim: identity
    equality, byte-level reuse, every machine's verdicts re-earned, the
    declared envelope and mutation floor held. Given exactly two
    directories, the byte-copy leg (M2) is materialized here via
    export/import and said so; given three or more, they are original,
    copy, and rebuilds, each rebuild tested. M1/M2/M3 are roles inferred
    from how realizations were produced, not commands.

    The verdict is three-valued: accept, reject, or incomplete — a
    condition the claim declared but this run did not measure can never
    accept (spec/verification.md).

EXIT STATUS
    0 accept; 1 reject or incomplete; 2 invalid invocation.
```

## `ret record`

```text
NAME
    ret record — write an execution record, or attest a build

SYNOPSIS
    ret record [<claim>] [-o <file>] [--key <ssh_key> [--as <identity>] | --sign]
    ret record [<claim>] --check [--signers <allowed_signers>]

DESCRIPTION
    Re-runs the claim's gates and freezes this machine's results as the one
    portable file other programs may parse (spec/record.md): root, build
    digest, per-gate results, environment, cost, producer declaration.
    Records represent failures as well as successes — a negative result is
    still evidence, and the exit code says which kind you hold. --key (or
    --sign, using $RETICULI_KEY) signs the record detached in its own
    namespace: a machine signature means "this execution produced these
    observations" — accountability for an observation, never human
    authorization (that is `ret sign`, and one must not substitute for the
    other).

    With --as <identity>, record writes an in-claim ATTESTATION instead of a
    portable file: a signed witness, bound to the build's root and output
    bytes, that travels with the claim. It self-invalidates on regeneration
    (the outputs change), so an attestation speaks for a build, not just a
    claim. --check verifies a claim's attestations (with --signers, the
    signer's identity against a trust anchor). This is the machine side of
    trust; `ret sign` is the human authorization ceremony.

EXIT STATUS
    0 recorded/attested and earned; 1 recorded a failure or an unverified
    attestation; 2 invalid invocation.
```

## `ret sign`

```text
NAME
    ret sign — authorize a claim or proof

SYNOPSIS
    ret sign [<claim>]                        review the packet (no key)
    ret sign [<claim>] --key <ssh_key> --as <identity>
    ret sign [<claim>] --check [--signers <allowed_signers>]

DESCRIPTION
    Human authorization, distinct from machine execution records and their
    signatures: "I reviewed this claim and evidence and accept
    responsibility for it." With no key it emits the review packet — the
    chain and evidence a signer is about to stand behind. With a key it
    authorizes; --check verifies an authorization against a trust anchor.
    A signed machine record never substitutes for this.
```

## Conventions

- Exit status 0 is the affirmative verdict; nonzero is a refusal with the reason on stderr.
- `--json` emits a machine-readable envelope on stdout, including for refusals.
- Commands that judge (`verify`, `audit`, `crosscheck`) never modify the claim they judge.
