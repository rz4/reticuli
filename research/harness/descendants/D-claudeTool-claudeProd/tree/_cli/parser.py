"""The argv grammar: fourteen verbs, one concept each.

The help is organized by CONCEPT, not as a flat verb dump -- a mental map the
user reads top to bottom as the workflow itself. Two levels: `-h` is concise
usage, `ret help <verb>` (and `--help`) is the fuller account, and
`ret help -a` lists everything, accepted older spellings included.
Completion is generated from this grammar, so it cannot drift from it.
"""
import argparse

#: The fourteen. One concept per verb: observe, declare, test, reconstruct,
#: compare, preserve.
PORCELAIN = ("init", "run", "status", "pack",
             "pull", "export", "import",
             "verify", "audit", "assess",
             "rebuild", "crosscheck",
             "record", "sign")

#: Accepted older spellings. Every v1 metaphor verb is retired and every fold
#: (seal -> pack --accept, hooks -> init, tree/claims -> status, attest ->
#: record) is complete, so nothing is aliased today. The table stays because
#: an alias is how a spelling is kept working when one is next folded.
ALIASES: dict = {}

#: Plumbing: dispatches, never listed in the fourteen-verb map.
PLUMBING = ("hook", "help", "completion")

_DESC = """Reticuli records and reproduces software claims.

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


def _version() -> str:
    from .. import __version__
    return f"ret {__version__}"


def _add_verbose_json(parser: argparse.ArgumentParser) -> None:
    """The three output levels, on every verb that answers."""
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="the explanatory account")
    parser.add_argument("--json", action="store_true",
                        help="the machine envelope")
    parser.add_argument("--color", choices=("auto", "always", "never"),
                        default="auto", help="colour policy")


def _verb(sub, name: str, usage: str | None = None):
    """One verb, with its own two-level help."""
    parser = sub.add_parser(name, prog=f"ret {name}", add_help=False,
                            usage=usage)
    parser.add_argument("-h", action="help", help="concise usage")
    parser.add_argument("--help", dest="full_help", action="store_true",
                        help="the full account")
    return parser


def _parser():
    """The parser, and the verb table it was built from."""
    top = argparse.ArgumentParser(
        prog="ret", description=_DESC, epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    top.add_argument("-V", "--version", action="version", version=_version(),
                     help="print the version")
    sub = top.add_subparsers(dest="cmd", metavar="<command>")

    init = _verb(sub, "init")
    init.add_argument("path", nargs="?", default=".")
    init.add_argument("--agent", default=None,
                      help="wire a coding agent's hooks (claude)")
    init.add_argument("--no-agent", action="store_true",
                      help="mark the workspace only")
    _add_verbose_json(init)

    run = _verb(sub, "run")
    run.add_argument("command", nargs="+")
    run.add_argument("-C", "--workspace", default=".")
    _add_verbose_json(run)

    status = _verb(sub, "status")
    status.add_argument("path", nargs="?", default=".")
    status.add_argument("--all", action="store_true", dest="every",
                        help="the whole ledger")
    status.add_argument("--files", action="store_true",
                        help="every declared file by role")
    status.add_argument("--tree", action="store_true",
                        help="the claim lens")
    status.add_argument("--claims", action="store_true",
                        help="the claim store")
    status.add_argument("--deps", action="store_true",
                        help="the dependency DAG")
    _add_verbose_json(status)

    pack = _verb(sub, "pack")
    pack.add_argument("path", nargs="?", default=".")
    pack.add_argument("--name", default=None)
    pack.add_argument("--root", default=None,
                      help="the root this pack must mint")
    pack.add_argument("--generated", action="append", default=None,
                      metavar="GLOB")
    pack.add_argument("--inputs", action="append", default=None,
                      metavar="GLOB")
    pack.add_argument("--carried", action="append", default=None,
                      metavar="GLOB")
    pack.add_argument("--gate", default=None)
    pack.add_argument("--output", default=None,
                      help="the verdict the gate pins")
    pack.add_argument("--pytest", nargs="?", const="tests", default=None,
                      help="gate on pytest")
    pack.add_argument("--environment", default=None,
                      help="a hash-pinned requirements file")
    pack.add_argument("--inputs-manifest", dest="inputs_manifest",
                      default=None)
    pack.add_argument("--mutation-floor", dest="mutation_floor", type=float,
                      default=None)
    pack.add_argument("--requires", action="append", default=None)
    pack.add_argument("--by", default=None, help="who wrote it")
    pack.add_argument("--format", dest="claim_format", type=int, default=None)
    pack.add_argument("--accept", action="append", default=None,
                      metavar="VERDICT")
    pack.add_argument("--claim", action="append", default=None,
                      metavar="FILE")
    pack.add_argument("-o", "--into", default=None)
    pack.add_argument("--force", action="store_true")
    _add_verbose_json(pack)

    pull = _verb(sub, "pull")
    pull.add_argument("claim")
    pull.add_argument("-C", "--workspace", default=".")
    _add_verbose_json(pull)

    export = _verb(sub, "export")
    export.add_argument("claim")
    export.add_argument("output", nargs="?", default=None)
    export.add_argument("-o", "--out", dest="out", default=None,
                        help="where to write; - is standard output")
    export.add_argument("--blind", action="store_true",
                        help="the rebuilder's room: withhold the generated bytes")
    _add_verbose_json(export)

    restore = _verb(sub, "import")
    restore.add_argument("archive")
    restore.add_argument("into", nargs="?", default=".")
    _add_verbose_json(restore)

    verify = _verb(sub, "verify")
    verify.add_argument("claim", nargs="?", default=".")
    _add_verbose_json(verify)

    audit = _verb(sub, "audit")
    audit.add_argument("claim", nargs="?", default=".")
    audit.add_argument("--shallow", action="store_true",
                       help="this claim's own gates only")
    audit.add_argument("--no-strict", dest="no_strict", action="store_true",
                       help="judge without the strict jail")
    audit.add_argument("--strict", action="store_true",
                       help="judge in the strict jail (the default)")
    audit.add_argument("--trust", default="self",
                       help="whose earned verdicts may be reused")
    audit.add_argument("--reuse", action="store_true",
                       help="reuse verdicts earned on these bytes")
    audit.add_argument("--mutants", type=int, default=None,
                       help="also measure the check")
    audit.add_argument("--record", default=None,
                       help="preserve the execution as a record")
    audit.add_argument("--progress", action="store_true")
    audit.add_argument("--quiet", action="store_true")
    _add_verbose_json(audit)

    assess = _verb(sub, "assess")
    assess.add_argument("claim", nargs="?", default=".")
    assess.add_argument("--mutants", type=int, default=None)
    _add_verbose_json(assess)

    rebuild = _verb(sub, "rebuild")
    rebuild.add_argument("claim")
    rebuild.add_argument("--producer", default=None,
                         help="a producer name, or any program")
    rebuild.add_argument("-o", "--into", default=None)
    rebuild.add_argument("--without-guidance", dest="without_guidance",
                         action="store_true",
                         help="withhold every producer hint")
    rebuild.add_argument("--progress", action="store_true")
    _add_verbose_json(rebuild)

    crosscheck = _verb(sub, "crosscheck")
    crosscheck.add_argument("legs", nargs="*", metavar="REALIZATION")
    crosscheck.add_argument("--mutants", type=int, default=None,
                            help="hold the redo to the declared mutation floor")
    crosscheck.add_argument("--tolerance", type=float, default=None,
                            help="tighten the cost band")
    crosscheck.add_argument("--progress", action="store_true")
    _add_verbose_json(crosscheck)

    record = _verb(sub, "record")
    record.add_argument("claim", nargs="?", default=".")
    record.add_argument("-o", "--output", default=None,
                        help="where to write; - is standard output")
    record.add_argument("--key", default=None)
    record.add_argument("--as", dest="identity", default=None)
    record.add_argument("--sign", action="store_true")
    record.add_argument("--check", action="store_true")
    record.add_argument("--signers", default=None)
    _add_verbose_json(record)

    sign = _verb(sub, "sign")
    sign.add_argument("claim", nargs="?", default=".")
    sign.add_argument("--key", default=None)
    sign.add_argument("--as", dest="identity", default=None)
    sign.add_argument("--check", action="store_true")
    sign.add_argument("--signers", default=None)
    sign.add_argument("-C", "--workspace", default=None)
    _add_verbose_json(sign)

    hook = _verb(sub, "hook")
    hook.add_argument("-C", "--workspace", default=".")
    _add_verbose_json(hook)

    helper = _verb(sub, "help")
    helper.add_argument("topic", nargs="?", default=None)
    helper.add_argument("-a", "--all", dest="every", action="store_true")
    _add_verbose_json(helper)

    completion = _verb(sub, "completion")
    completion.add_argument("shell", nargs="?", default="bash",
                            choices=("bash", "zsh"))
    _add_verbose_json(completion)

    return top, sub


def verbs() -> list:
    """Everything that dispatches: the fourteen, the aliases, the plumbing."""
    return list(PORCELAIN) + list(ALIASES) + list(PLUMBING)


_FULL_HELP = {
    "init": """NAME
    ret init - initialize a workspace

SYNOPSIS
    ret init [PATH] [--agent claude] [--no-agent]

DESCRIPTION
    Marks PATH as a reticuli workspace and makes it git-native: residue is
    ignored, identity is committed. With --agent, the coding-agent handshake
    is wired at the same time -- the agent is not a separate concept to
    learn. An unknown agent value is an invalid invocation, refused in words.
""",
    "run": """NAME
    ret run - run and observe a command

SYNOPSIS
    ret run COMMAND [-C WORKSPACE]

DESCRIPTION
    Runs COMMAND in the workspace and remembers it as a session
    observation. A transparent boundary: only the child's streams are shown,
    and the child's exit code is returned UNCHANGED, so `ret run` can be used
    as a predicate the way any command can. A red run cannot go green.
""",
    "status": """NAME
    ret status - show work, claims, and unresolved inputs

SYNOPSIS
    ret status [PATH] [--all] [--files] [--tree] [--claims] [--deps]

DESCRIPTION
    The one view. It reads and reports and never executes: every form is
    instant on any claim, and every form ends with `next`, the first rung
    this claim has not yet earned. A session shows the authoring triad --
    what was observed, what would be declared, what is unresolved. A sealed
    claim shows identity, the dated receipts, the discovery bill, and the
    ladder. A broken claim is still described, and pointed at its fix.

    --files lists every declared file by role, hiding none. --tree is the
    claim lens. The jail choice belongs to audit, not to a view.
""",
    "pack": """NAME
    ret pack - create a claim from a project

SYNOPSIS
    ret pack [PATH] [--generated GLOB] [--inputs GLOB] [--gate CMD]
             [--output VERDICT] [--pytest [TARGET]] [--environment FILE]
             [--accept VERDICT -o DIR] [--name NAME] [--format N]

DESCRIPTION
    One authoring boundary, three sources. A project that already declares a
    reticuli.toml is sealed with no flags at all -- the recipe IS the
    declaration. A traced session is sealed with --accept, which names the
    verdicts the session stands behind, and -o, which says where the claim
    goes. Otherwise the declaration language above says which files are
    generated, which are criteria, and what the gate is.

    The gate is earned WARM before the claim is sealed, inside the claim, so
    a criterion may ask what claim it is in. A gate whose every decider is
    generated is vacuous and refused: a root must not fit any implementation
    that prints ok.
""",
    "pull": """NAME
    ret pull - add another claim as a dependency

SYNOPSIS
    ret pull CLAIM [-C WORKSPACE]

DESCRIPTION
    Copies CLAIM, and the whole closure beneath it, into the workspace's
    store, then materializes its declared files. The pulled claim stands
    alone: with its source gone it still verifies and its whole chain still
    re-earns. The closure is laid down flat, so each dependency's bytes
    appear a bounded number of times rather than once per path that reaches
    them.
""",
    "export": """NAME
    ret export - write a portable claim archive

SYNOPSIS
    ret export CLAIM [OUTPUT] [-o OUTPUT] [--blind]

DESCRIPTION
    Writes exactly what the claim DECLARES -- never what happens to sit in
    the directory -- byte-deterministically, so two exports of one claim are
    identical. The ledger stays home: a machine's private bookkeeping is not
    part of what travels. Component claims travel beside it, so an import can
    re-earn every layer from the bytes it received.

    --blind writes the rebuilder's room: the same claim minus its generated
    outputs. The identity travels whole, because the root never covered the
    implementation.

    OUTPUT may be - for standard output, so export and import compose through
    a pipe.
""",
    "import": """NAME
    ret import - restore a claim archive

SYNOPSIS
    ret import ARCHIVE [INTO]

DESCRIPTION
    Restores an archive and verifies it from the received bytes alone. A
    missing or damaged archive is a refusal with a reason, never a raw
    crash. ARCHIVE may be - for standard input.
""",
    "verify": """NAME
    ret verify - verify claim identity

SYNOPSIS
    ret verify [CLAIM]

DESCRIPTION
    Recomputes the root from the bytes present and compares it with the
    sealed manifest; identity only, in milliseconds.

    Does not execute acceptance criteria. A verdict is earned by `ret audit`,
    and a verifier that ran gates under the name verify would blur the one
    distinction the whole design exists to keep sharp.

    A passing verify is silent. A broken one names the files that moved.
""",
    "audit": """NAME
    ret audit - rerun acceptance criteria

SYNOPSIS
    ret audit [CLAIM] [--shallow] [--no-strict] [--mutants N]
              [--record PATH]

DESCRIPTION
    The only verb that re-earns a verdict. It regrows nothing it is told to
    trust: every gate is re-run cold in a sandbox, every pinned byte must
    reproduce, and composed claims are judged recursively on the bytes the
    outer claim ships. Judging happens in the strict jail by default, so a
    claim's gates never read your files; --no-strict is the explicit opt-down.

    --shallow judges this claim's own gates only. --mutants also measures how
    much the criteria prove. --record preserves the execution as a record.
""",
    "assess": """NAME
    ret assess - measure specification strength

SYNOPSIS
    ret assess [CLAIM] [--mutants N]

DESCRIPTION
    A root says what a claim IS, never how strongly it is held. assess
    measures the width of the equivalence class: which declared files the
    gates reach, and which survive deterministic mutation drawn from the
    root. The result is left as root-stamped residue -- a receipt, not a
    verdict.
""",
    "rebuild": """NAME
    ret rebuild - rebuild an implementation from a claim

SYNOPSIS
    ret rebuild CLAIM --producer NAME|COMMAND -o DIR [--without-guidance]

DESCRIPTION
    Materializes a blind room from the claim -- the recipe, the pinned
    inputs, the verdicts -- and asks a producer to regrow the generated
    outputs until the gates pass. The generated sources are withheld from
    that room, which is the whole guarantee: a rebuild that lands the same
    root shows the criteria alone carry the software.

    A producer is any program. It is handed the output to write in
    RETICULI_OUTPUT, the whole work list in RETICULI_OUTPUTS, and a place to
    report its cost in RETICULI_USAGE. It keeps your HOME, so a model CLI
    finds its credential, and it never sees a variable you did not hand over.

    The shipped adapters answer to their names, with an optional model after
    a colon:

        --producer openai[:MODEL]      the OpenAI SDK (OPENAI_API_KEY)
        --producer anthropic[:MODEL]   the Anthropic SDK (ANTHROPIC_API_KEY)
        --producer codex[:MODEL]       the codex command line
        --producer claude[:MODEL]      the claude command line

    A named producer is preflighted: a missing command or credential is one
    line on stderr before a room is built or any money moves.

    --without-guidance withholds every producer hint, so a pass measures what
    the acceptance criteria alone carry.
""",
    "crosscheck": """NAME
    ret crosscheck - compare independent realizations

SYNOPSIS
    ret crosscheck M1 [M2] M3 [--mutants N] [--tolerance T]

DESCRIPTION
    The three-machine test. M1 verifies in place, M2 is the same bytes having
    travelled, and M3 is an independent rebuild that saw only the pinned
    inputs. Valid means one root across all three, every verdict re-earned,
    byte reuse where reuse is claimed, and every condition the claim itself
    declared.

    Given two realizations, a real byte-copy M2 is materialized here and the
    result says so; one realization is not a comparison.

    The verdict is three-valued: accept, reject, or incomplete. A declared
    condition this run could not measure is neither true nor false, and
    incomplete can never accept.

    A leg may be a claim directory or a signed record: one predicate, two
    transports.

    --mutants holds the redo to the claim's declared mutation floor.
    --tolerance may TIGHTEN a declared cost band, never loosen it.
""",
    "record": """NAME
    ret record - write an execution record

SYNOPSIS
    ret record [CLAIM] [-o PATH] [--key KEY] [--as IDENTITY]
               [--sign] [--check] [--signers FILE]

DESCRIPTION
    A record is the one file this project promises other programs may parse:
    a signed statement of what one machine established about one claim at one
    time. Emitting one re-earns the gates; the file holds its own canonical
    bytes, and its digest is how it is cited.

    With --key and --as, the claim is attested in place: a signed statement
    about this build, kept with the claim and travelling with it. --check
    verifies the attestations already there. --sign signs the emitted record
    with the identity in RETICULI_KEY.
""",
    "sign": """NAME
    ret sign - authorize a claim or proof

SYNOPSIS
    ret sign [CLAIM] [--key KEY --as IDENTITY] [--check] [--signers FILE]

DESCRIPTION
    The accountable act, and never an agent's. With no key, the review packet
    is printed: what a signer would be standing behind -- the chain root, the
    composed audit, whether a proof is recorded. With --key, that packet is
    signed in the authorization namespace, which is cryptographically
    distinct from attestation.

    Signing refuses a claim whose verdicts do not reproduce, and -- where the
    claim declares components -- a claim whose composed verdict does not
    re-earn.

    --check asks what is authorized TO YOU, which is a question about your
    anchor. With no allowed_signers file the honest answer is that nothing
    is: a signature can then only be shown self-consistent, never attributed.
""",
    "hook": """NAME
    ret hook - the coding-agent handshake (plumbing)

SYNOPSIS
    ret hook [-C WORKSPACE]

DESCRIPTION
    Reads one agent-harness payload on standard input and remembers it as a
    session observation. Silent, and exits 0 whatever the payload: a
    handshake that broke an agent's turn would be worse than no handshake.
    Wire it with `ret init --agent claude`.
""",
    "completion": """NAME
    ret completion - print a shell completion script

SYNOPSIS
    ret completion [bash|zsh]

DESCRIPTION
    Generated from the parser itself, so it cannot drift from the grammar.
""",
    "help": """NAME
    ret help - the fuller account of a verb

SYNOPSIS
    ret help [COMMAND] [-a]

DESCRIPTION
    `ret help COMMAND` is the full account; `ret help -a` lists everything
    that dispatches, accepted older spellings included.
""",
    "environment": """NAME
    environment - every variable this tool reads

SYNOPSIS
    ret help environment

DESCRIPTION
    RETICULI_KEY          the ssh key `record --sign` signs with
    RETICULI_SIGNERS      your allowed_signers anchor; with none, nothing is
                          authorized to you
    RETICULI_PRODUCER     the producer the launcher regrows latent bytes with
    RETICULI_GATE_TIMEOUT a host ceiling on a gate's wall clock, in seconds
    RETICULI_TOLERANCE    a cost band to apply; it may tighten a declared
                          band, never loosen it
    RETICULI_CACHE        where earned verdicts are remembered
    RETICULI_ENV_CACHE    where furnished environments are cached
    RETICULI_COLOR        auto, always, or never
    RETICULI_VENDOR       the vendor a rebuild declares
    RETICULI_MODEL        the model a rebuild declares
    RETICULI_PRICE        a price table a producer adapter may read
    RETICULI_AGENT_TURNS  how many turns an agent producer may take
    OPENAI_API_KEY        the openai producer's credential
    OPENAI_BASE_URL       an alternative openai endpoint
    ANTHROPIC_API_KEY     the anthropic producer's credential

    Set inside a room by the kernel, read by a producer:

    RETICULI_OUTPUT       the absolute path of the output to write next
    RETICULI_OUTPUTS      every generated output, as a JSON array
    RETICULI_REQUEST      the recipe's own guidance, when guidance is given
    RETICULI_USAGE        where a producer reports what it spent
    RETICULI_CLAIM        the room the producer is working in
    RETICULI_JAILED       set when you are already inside a sandbox; a
                          conforming tool then inherits rather than nesting
""",
}


def _help_topic(topic: str) -> int:
    """The full account of one verb, or the topic index."""
    if topic in _FULL_HELP:
        print(_FULL_HELP[topic].rstrip())
        return 0
    if topic in ALIASES:
        return _help_topic(ALIASES[topic])
    print(_DESC)
    print()
    print(_EPILOG)
    return 0 if topic in (None, "") else 2


def _help_all() -> int:
    """Everything that dispatches, grouped, nothing hidden."""
    print(_DESC)
    print()
    print("Plumbing")
    for name in PLUMBING:
        print(f"    {name}")
    print()
    print("Accepted older spellings")
    if ALIASES:
        for name in sorted(ALIASES):
            print(f"    {name}  (now: {ALIASES[name]})")
    else:
        print("    none: every v1 spelling has been folded into the "
              "fourteen above")
    print()
    print("Topics")
    print("    environment")
    print()
    print(_EPILOG)
    return 0


def _completion(shell: str = "bash") -> int:
    """A completion script generated from the grammar itself."""
    names = " ".join(sorted(set(verbs())))
    if shell == "zsh":
        print("#compdef ret")
        print(f"_ret() {{ _arguments '1:command:({names})' '*:file:_files' }}")
        print("compdef _ret ret")
        return 0
    print("# bash completion for ret, generated from the grammar")
    print("_ret_complete() {")
    print("    local cur prev")
    print('    cur="${COMP_WORDS[COMP_CWORD]}"')
    print('    prev="${COMP_WORDS[COMP_CWORD-1]}"')
    print(f'    local verbs="{names}"')
    print('    if [ "$COMP_CWORD" -eq 1 ]; then')
    print('        COMPREPLY=( $(compgen -W "$verbs" -- "$cur") )')
    print("        return 0")
    print("    fi")
    print('    COMPREPLY=( $(compgen -f -- "$cur") )')
    print("}")
    print("complete -F _ret_complete ret")
    return 0
