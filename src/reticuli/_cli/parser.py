"""ret command line — the parser layer: the argv grammar, the verb map, man-page help, and completion."""
from __future__ import annotations

import argparse
import sys

from .. import assess as assess_mod
from .handlers import (  # noqa: F401
    init,
    run,
)

# -- dispatch ----------------------------------------------------------------

_DESC = """\
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
    sign        authorize a claim or proof"""



_EPILOG = ("See 'ret <command> -h' for command usage.\n"
           "See 'ret help <command>' for detailed help; 'ret help -a' lists "
           "everything,\nincluding accepted older spellings.")



#: The fourteen: each survives the test that removing it would erase a
#: distinction, not merely a view. Everything else is an alias or plumbing.
PORCELAIN = ("init", "run", "status", "pack",
             "pull", "export", "import",
             "verify", "audit", "assess",
             "rebuild", "crosscheck",
             "record", "sign")



#: Accepted older spellings — they dispatch, `ret help -a` lists them, the
#: fourteen-verb map does not. Removing each would break invocations without
#: preserving a distinction: their meaning survives inside a porcelain verb.
#: `seal`/`hooks`/`tree`/`claims` were retired 2026-09-22 — their meaning is
#: fully covered by `pack --accept` / `init` / `status --tree` / `status
#: --claims`, so they are now unknown verbs, not quiet synonyms (see RETIRED).
ALIASES = {"attest": "record --key / sign (machine vs human signature)"}



_FULL_HELP = {
    "init": """\
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
    0 initialized; 1 refused (with a reason); 2 invalid invocation.""",
    "run": """\
NAME
    ret run — run and observe a command

SYNOPSIS
    ret run <command> [-C <workspace>]
    ret run -- <argv>...

DESCRIPTION
    Executes the command in the workspace and appends it to the session
    trace. Useful even when agent hooks are present: it is an explicit,
    human-authored execution boundary. The child's exit code is returned
    unchanged.""",
    "status": """\
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
    0 (a view); 1 the path holds no readable state; 2 invalid invocation.""",
    "pack": """\
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
    0 packed; 1 the gates or the declaration refused; 2 invalid invocation.""",
    "pull": """\
NAME
    ret pull — add another claim as a dependency

SYNOPSIS
    ret pull <claim> [-C <into>]

DESCRIPTION
    Copies a sealed claim into this workspace's claim store and registers it
    as a dependency. Pull changes the dependency graph; export/import move
    bytes without composition semantics — that is the difference.""",
    "export": """\
NAME
    ret export — write a portable claim archive

SYNOPSIS
    ret export [<claim>] [<archive>] [-o <archive>] [--blind]

DESCRIPTION
    Writes the claim's declared content to a deterministic tar. No
    dependency semantics. --blind writes the rebuilder's room: criteria,
    verdicts, and the manifest travel; the generated implementation stays
    home — the root never covered it, so the room still verifies.
    The archive defaults to <name>.tar in the current directory.""",
    "import": """\
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
    0 imported and fresh; 1 the extracted bytes do not verify; 2 invalid.""",
    "verify": """\
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
    0 fresh; 1 broken; 2 invalid invocation.""",
    "audit": """\
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
    0 earned (or honestly reused); 1 anything else; 2 invalid invocation.""",
    "assess": """\
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
    (trusted only while their recorded root still matches).""",
    "rebuild": """\
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

    The shipped producers answer to their names: `--producer openai` or
    `--producer anthropic:claude-opus-5`. Naming one authorizes forwarding
    its own vendor's key (OPENAI_API_KEY / ANTHROPIC_API_KEY) from your
    environment — only the matched key, never to gates — and a missing SDK
    or credential refuses in one line before any money moves. Set
    RETICULI_PRICE ("in,out" usd/Mtok) if you want dollars in the ledger;
    without it tokens are recorded and a declared usd envelope reads
    incomplete, honestly. Any other value is run verbatim as a command —
    a producer is any program, a compiler and a Makefile included.

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
    the cost is ledgered.""",
    "crosscheck": """\
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
    0 accept; 1 reject or incomplete; 2 invalid invocation.""",
    "record": """\
NAME
    ret record — write an execution record

SYNOPSIS
    ret record [<claim>] [-o <file>] [--key <ssh_key> | --sign]

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

EXIT STATUS
    0 recorded and earned; 1 recorded a failure; 2 invalid invocation.""",
    "sign": """\
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
    A signed machine record never substitutes for this.""",
}




def _add_verbose_json(q) -> None:
    q.add_argument("--json", action="store_true")
    q.add_argument("-v", "--verbose", action="store_true")
    q.add_argument("--color", choices=("auto", "always", "never"), default=None)




def _parser() -> tuple[argparse.ArgumentParser, dict]:
    """The argv grammar, and the verbs it registers.

    Built in one place so the documented map in `_DESC` can be checked against
    what `ret` really dispatches — a verb that exists but is undocumented, or
    documented but absent, is a drift the surface gate catches.
    """
    p = argparse.ArgumentParser(prog="ret", usage="ret <command> [<args>]",
                                description=_DESC, epilog=_EPILOG,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    # verbs carry no parser-level help= — the grouped map in _DESC is the one
    # listing (argparse only auto-lists verbs that set help=). Group order and
    # membership are structure, ratified by surface_check; wording stays free.
    sub = p.add_subparsers(dest="cmd", required=True, metavar="<command>")

    def add(name, usage=None, description=None):
        return sub.add_parser(
            name, usage=usage, description=description,
            formatter_class=argparse.RawDescriptionHelpFormatter)

    # -- authoring
    q = add("init", usage="ret init [<path>] [--agent <name> | --no-agent]",
            description="Initialize a Reticuli workspace.\n\n"
                        "When a supported coding-agent environment is detected,\n"
                        "nonblocking observation hooks are installed idempotently.")
    q.add_argument("project", nargs="?", default=".")
    q.add_argument("--agent", default=None, metavar="NAME",
                   help="agent integration: claude (auto-wired), or generic "
                        "for any other harness (targets the `ret hook` contract)")
    q.add_argument("--no-agent", action="store_true",
                   help="do not configure agent integration")
    q = add("run", usage="ret run <command> [-C <workspace>]\n       ret run -- <argv>...",
            description="Run a command and record its execution in the session trace.")
    q.add_argument("command", nargs="*", default=[])
    q.add_argument("-C", "--workspace", default=".")
    q = add("status", usage="ret status [<path>] [--all] [--tree] [--json]",
            description="Show observed work and declared claims.\n\n"
                        "During authoring, status highlights observed but\n"
                        "undeclared or uncovered files. On a sealed claim it\n"
                        "shows identity and recorded evidence; --all is the\n"
                        "full account, --tree the relationships.")
    q.add_argument("workspace", nargs="?", default=".")
    q.add_argument("--all", action="store_true",
                   help="everything, one page: the ledger, the files, the tree")
    q.add_argument("--files", action="store_true",
                   help="the per-file account: what each file is to this claim")
    q.add_argument("--tree", action="store_true",
                   help="dependency and evidence relationships")
    q.add_argument("--claims", action="store_true",
                   help="list the claims in the workspace (the claim store)")
    q = add("pack", usage="ret pack [<path>] [-o <directory>] [--name <name>] [--force]",
            description="Create a claim from a project.\n\n"
                        "A directory with reticuli.toml seals in place after its\n"
                        "gates pass warm. A draft session needs --accept and -o;\n"
                        "its gates re-run cold. Explicit declaration flags\n"
                        "(--generated, --gate/--output or --pytest, ...) build\n"
                        "the recipe first. Criteria must pass before a claim\n"
                        "is created.")
    q.add_argument("path", nargs="?", default=".")
    q.add_argument("-o", "--into", default=None, metavar="DIR",
                   help="where the claim materializes (session flow)")
    q.add_argument("--name", default=None,
                   help="the claim's name (default: the directory's)")
    q.add_argument("-C", "--root", dest="root", default=None, metavar="DIR",
                   help="the project directory (older spelling; with it, a "
                        "positional argument is read as the name, as it "
                        "used to be)")
    q.add_argument("--force", action="store_true",
                   help="pack a session despite unresolved observations")
    q.add_argument("--accept", action="append", default=[], metavar="PATH",
                   help="a verdict file that decides acceptance (session flow)")
    q.add_argument("--claim", action="append", default=[], metavar="PATH",
                   help="force a file into the claim (a pinned input), whoever wrote it")
    q.add_argument("--generated", nargs="+", default=None, metavar="GLOB",
                   help="the implementation: files declared generated (project flow)")
    q.add_argument("--input", nargs="*", default=[], metavar="GLOB")
    q.add_argument("--gate", default=None)
    q.add_argument("--output", default=None)
    q.add_argument("--pytest", default=None, metavar="DIR",
                   help="shorthand for an ordinary pytest suite: the gate runs "
                        "`python3 -m pytest -q DIR`, DIR's tests become pinned "
                        "inputs, and the verdict is OK")
    q.add_argument("--environment", default=None, metavar="FILE",
                   help="a hash-pinned requirements file the gates run inside; "
                        "pinned into the root, because dependency versions "
                        "decide what passing means")
    q.add_argument("--component", default=None, metavar="CLAIM",
                   help="a sealed claim this one layers on")
    q.add_argument("--mutation-floor", type=float, default=None, metavar="FLOOR",
                   help="declare the mutation kill rate crosscheck holds a redo to (0..1)")
    q.add_argument("--requires", nargs="*", default=[], metavar="TOOL",
                   help="what the gate needs from the host: a binary, python:module, python>=X.Y")
    q.add_argument("--inputs-manifest", default=None, metavar="FILE",
                   help="write the pinned input list to FILE and declare it (format 2)")
    q.add_argument("--by", default=None, metavar="MODEL",
                   help="who produced the implementation (ledger residue, never identity)")
    # -- composition and transport
    q = add("pull", usage="ret pull <claim> [-C <into>]",
            description="Add another claim as a dependency of the current project.")
    q.add_argument("component")
    q.add_argument("-C", "--into", default=".")
    q = add("export", usage="ret export [<claim>] [<archive>] [--blind]",
            description="Write a portable representation of a claim.\n"
                        "--blind omits the generated implementation: the rebuilder's room.")
    q.add_argument("claim", nargs="?", default=".")
    q.add_argument("tar", nargs="?", default=None)
    q.add_argument("-o", "--out", dest="tar_opt", default=None, metavar="ARCHIVE")
    q.add_argument("--blind", action="store_true",
                   help="the rebuilder's room: omit the generated outputs and "
                        "signing residue; criteria, verdicts, and the manifest travel")
    q = add("import", usage="ret import <archive> [<directory>]",
            description="Restore a portable claim without adding it as a dependency.")
    q.add_argument("tar")
    q.add_argument("into", nargs="?", default=None)
    q.add_argument("-o", "--out", dest="into_opt", default=None, metavar="DIR")
    # -- verification
    q = add("verify", usage="ret verify [<claim>] [--json]",
            description="Verify the identity of a claim.\n\n"
                        "Recomputes the claim root from its declared contents.\n"
                        "Does not execute acceptance criteria.")
    q.add_argument("claim", nargs="?", default=".")
    q = add("audit", usage="ret audit [<claim>] [--record [<file>]] [--json]",
            description="Rerun a claim's acceptance criteria, cold and sandboxed.\n\n"
                        "Gates run under the STRICT jail: a claim's gates never\n"
                        "get to read your own files while you judge them.")
    q.add_argument("claim", nargs="?", default=".")
    q.add_argument("--no-strict", action="store_true",
                   help="run the gates under the standard jail instead of the "
                        "strict one (which masks your own files from them)")
    q.add_argument("--record", nargs="?", const=True, default=None, metavar="FILE",
                   help="preserve the execution as a record")
    q.add_argument("--shallow", action="store_true",
                   help="this claim's gates only (default: the whole component chain)")
    q.add_argument("--mutants", type=int, default=0, metavar="N",
                   help="also mutate the generated code N times and report the check's kill rate")
    q.add_argument("--reuse", action="store_true",
                   help="skip the gates if THIS machine already earned this exact claim, "
                        "these exact generated bytes, and this environment (off by "
                        "default: a stored verdict is never trusted)")
    q = add("assess", usage="ret assess [<claim>] [<options>]",
            description="Measure how strongly a claim constrains implementations.\n\n"
                        "May evaluate fault detection, re-derivation, held-out\n"
                        "behavior, and producer agreement. Does not change the claim.")
    q.add_argument("claim", nargs="?", default=".")
    q.add_argument("--mutants", type=int, default=assess_mod.DEFAULT_MUTANTS, metavar="N",
                   help="how many faults to inject (default: %(default)s)")
    q.add_argument("--rebuild", metavar="PRODUCER",
                   help="ask this producer to rebuild BLIND, from the tests alone (costs money)")
    q.add_argument("--rebuild-into", metavar="DIR",
                   help="keep the blind rebuild workspace here instead of a temp dir")
    q.add_argument("--guided", action="store_true",
                   help="also run a guided rebuild (the recipe's hint is kept) as a "
                        "control: guided passing while blind fails points at the "
                        "tests, not the producer")
    q.add_argument("--corpus", metavar="FILE",
                   help="record this run into a reference corpus and report where "
                        "it sits in the population (residue; never changes identity)")
    q.add_argument("--heldout", type=float, default=None, metavar="FRACTION",
                   help="hide this fraction of the claim's case corpus, re-seal on the rest, "
                        "and judge each --heldout-producer's blind rebuild on the hidden cases")
    q.add_argument("--heldout-producer", action="append", default=[], metavar="NAME=COMMAND",
                   help="a producer to regrow the implementation from the kept cases alone; "
                        "repeatable, and two or more also give the pairwise excess agreement")
    q.add_argument("--heldout-cases", default=None, metavar="GLOB",
                   help="which pinned inputs are the case corpus (default: the largest "
                        "family of inputs under one directory)")
    q.add_argument("--heldout-into", metavar="DIR",
                   help="keep the held-out workspace here instead of a temp dir")
    # -- reconstruction
    q = add("rebuild", usage="ret rebuild [<claim>] --producer <command> [-o <directory>]",
            description="Build a new implementation from a claim.\n\n"
                        "Generated implementation files from the source realization\n"
                        "are withheld from the producer.")
    q.add_argument("claim", nargs="?", default=".")
    q.add_argument("--producer", required=True,
                   help="command used to produce the implementation")
    q.add_argument("-o", "--into", required=True, metavar="DIR",
                   help="destination for the rebuilt project")
    q.add_argument("--recursive", action="store_true",
                   help="DAG-aware: also rebuild component dependencies, bottom-up")
    q.add_argument("--without-guidance", action="store_true",
                   help="hand the producer the outputs to write but NOT the "
                        "hints for how: a pass then measures what the criteria "
                        "alone carry (format 3, where guidance is not in the root)")
    q = add("crosscheck", usage="ret crosscheck <realization> <realization>...",
            description="Compare realizations of the same claim.\n\n"
                        "Checks claim identity, earned criteria, implementation\n"
                        "reuse, and available provenance evidence. With exactly\n"
                        "two, the byte-copy leg is materialized here and said so.")
    q.add_argument("machines", nargs="+", metavar="realization")
    q.add_argument("--record-proof", action="store_true",
                   help="record the three-machine proof on M1 (residue; signed is the "
                        "signing ceremony's)")
    q.add_argument("--mutants", type=int, default=30, metavar="N",
                   help="mutants for the mutation floor, when the claim declares one")
    # -- evidence
    q = add("record", usage="ret record [<claim>] [-o <file>] [--key <ssh_key> | --sign]",
            description="Write a portable execution record.\n\n"
                        "Records may describe successful or failed executions.")
    q.add_argument("claim", nargs="?", default=".")
    q.add_argument("-o", "--out", default=None, metavar="FILE",
                   help="where to write the record (default: <name>.record.json here)")
    q.add_argument("--key", default=None, metavar="SSH_KEY",
                   help="also sign the record, detached, in the reticuli.record namespace")
    q.add_argument("--sign", action="store_true",
                   help="sign with the configured identity ($RETICULI_KEY)")
    q = add("sign", usage="ret sign [<claim>] [--key <ssh_key> --as <identity>] [--check]",
            description="Authorize a claim and its evidence.\n\n"
                        "A human authorization, distinct from machine execution\n"
                        "records and their signatures.")
    q.add_argument("claim", nargs="?", default=".")
    q.add_argument("--key", default=None, metavar="SSH_KEY")
    q.add_argument("--as", dest="identity", default=None, metavar="IDENTITY")
    q.add_argument("--check", action="store_true")
    q.add_argument("--signers", default=None, metavar="ALLOWED_SIGNERS")

    # -- aliases: accepted older spellings (unlisted; `ret help -a` names them).
    #    seal/hooks/tree/claims were retired 2026-09-22 -- fully covered by
    #    pack --accept / init / status --tree / status --claims.
    q = add("attest")
    q.add_argument("claim", nargs="?", default=".")
    q.add_argument("--key", default=None, metavar="SSH_KEY")
    q.add_argument("--as", dest="identity", default=None, metavar="IDENTITY")
    q.add_argument("--check", action="store_true")
    q.add_argument("--signers", default=None, metavar="ALLOWED_SIGNERS")
    # -- plumbing: agent event sink (invoked by installed hooks), help,
    #    and shell completion, generated from this parser so it cannot drift
    q = add("hook")
    q.add_argument("-C", "--workspace", default=None)
    q = add("completion", usage="ret completion bash|zsh")
    q.add_argument("shell", choices=("bash", "zsh"))
    q = add("help", usage="ret help [<command>] [-a]",
            description="Detailed help for a command; -a lists the whole "
                        "command set,\nincluding accepted older spellings and plumbing.")
    q.add_argument("topic", nargs="?", default=None)
    q.add_argument("-a", "--all", action="store_true")

    for name in (*PORCELAIN, *ALIASES):
        if name not in ("run",):        # run's output is the child's, verbatim
            _add_verbose_json(sub.choices[name])
    return p, sub.choices




def verbs() -> list[str]:
    """Every verb `ret` accepts, in declaration order — the parser is the source."""
    return list(_parser()[1])




def _help_topic(topic: str) -> int:
    if topic in _FULL_HELP:
        print(_FULL_HELP[topic])
        return 0
    if topic in ALIASES:
        print(f"`ret {topic}` is an accepted older spelling of: {ALIASES[topic]}\n"
              f"See `ret help {ALIASES[topic].split()[0]}`.")
        return 0
    if topic == "hook":
        print("ret hook — plumbing: the agent event sink. Installed hooks pipe\n"
              "their payloads here; it appends trace events and prints nothing.")
        return 0
    if topic == "completion":
        print("ret completion bash|zsh — plumbing: print a shell completion\n"
              "script, generated from the parser itself. Install with e.g.\n"
              "    ret completion bash > ~/.local/share/bash-completion/completions/ret")
        return 0
    if topic == "environment":
        print("""\
ENVIRONMENT VARIABLES

Presentation
    RETICULI_COLOR       auto | always | never (--color overrides)
    NO_COLOR             any value disables color (the standard)

Evidence and identity
    RETICULI_KEY         private ssh key `record --sign` uses
    RETICULI_SIGNERS     allowed-signers file for --check verbs

Producers (read inside the scrubbed rebuild environment)
    RETICULI_MODEL       model a shipped producer drives
    RETICULI_PRICE       "in,out" usd per Mtok, so the ledger prices tokens;
                         unset means tokens-only (there is no built-in
                         price table — tables drift)
    RETICULI_AGENT_TURNS producer tool-loop cap (default 40)
    OPENAI_API_KEY / ANTHROPIC_API_KEY / OPENAI_BASE_URL
                         vendor credentials. A NAMED producer
                         (--producer openai) forwards its own vendor's key
                         from your environment automatically; a raw
                         command producer must inject it itself
                         (`. keyfile && exec ...`) — the scrub strips
                         inherited secrets by design, and gates never see
                         any of this either way

Hosts
    RETICULI_ENV_CACHE   where furnished environments are cached
    RETICULI_GATE_TIMEOUT / RETICULI_TOLERANCE
                         host ceilings; a claim can tighten, never loosen

The scrub is the point: a gate or producer sees an allowlist (PATH, HOME,
TMPDIR, LANG, LC_ALL, TZ) plus what reticuli itself sets — inherited
secrets never reach a stranger's gate.""")
        return 0
    print(f"ret: no help for {topic!r} (try `ret help -a`)", file=sys.stderr)
    return 2




def _help_all() -> int:
    print(_DESC)
    print("\nAccepted older spellings (aliases; the fourteen are the grammar)")
    for name, meaning in ALIASES.items():
        print(f"    {name:<11} -> {meaning}")
    print("\nPlumbing\n    hook        agent event sink (invoked by installed hooks)"
          "\n    help        this listing; `ret help <command>` for detail"
          "\n    completion  shell completion script (bash|zsh), from the parser"
          "\n\nTopics\n    environment `ret help environment`: every variable the "
          "tool reads")
    return 0




def _completion(shell: str) -> int:
    """A completion script generated from the one parser, so the shell can
    never disagree with the grammar."""
    _, choices = _parser()
    verbs = [n for n in choices if n != "hook"]
    flags = {n: " ".join(sorted({s for a in choices[n]._actions
                                 for s in a.option_strings}))
             for n in verbs}
    if shell == "bash":
        arms = "\n".join(f'    {n}) COMPREPLY=($(compgen -W "{flags[n]}" -- "$cur"));;'
                         for n in verbs)
        print(f"""_ret() {{
  local cur="${{COMP_WORDS[COMP_CWORD]}}"
  if [ "$COMP_CWORD" -eq 1 ]; then
    COMPREPLY=($(compgen -W "{' '.join(verbs)}" -- "$cur")); return
  fi
  case "${{COMP_WORDS[1]}}" in
{arms}
  esac
  if [ "${{#COMPREPLY[@]}}" -eq 0 ] || [ "${{cur:0:1}}" != "-" ]; then
    COMPREPLY+=($(compgen -o default -- "$cur"))
  fi
}}
complete -F _ret ret""")
        return 0
    arms = "\n".join(f'    {n}) _arguments -- ; compadd -- {flags[n]} ;;'
                     for n in verbs)
    print(f"""#compdef ret
_ret() {{
  if (( CURRENT == 2 )); then
    compadd -- {' '.join(verbs)}
    return
  fi
  case "$words[2]" in
{arms}
  esac
  _files
}}
_ret""")
    return 0
