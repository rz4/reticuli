"""The argv grammar: fourteen verbs, one concept each.

The help is organized BY CONCEPT, not as a flat verb dump -- a mental map a
user reads top to bottom as the workflow itself: observe, declare, test,
reconstruct, compare, preserve. Structure evaporates unless a gate demands
it, so the groups, their order and their membership are part of the
contract; the wording of each line is not.

Two levels of help. `ret <verb> -h` is concise usage. `ret help <verb>` (and
`ret <verb> --help`) is the fuller account, with a SYNOPSIS and the
reasoning a user needs once. `ret help -a` lists everything, plumbing and
accepted older spellings included -- so nothing dispatches undocumented, and
nothing documented fails to dispatch.

Completion is GENERATED from this grammar, so it cannot drift from it.
"""
import argparse

_DESC = 'Reticuli records and reproduces software claims.\n\nAuthoring\n    init        initialize a workspace\n    run         run and observe a command\n    status      show work, claims, and unresolved inputs\n    pack        create a claim from a project\n\nComposition and transport\n    pull        add another claim as a dependency\n    export      write a portable claim archive\n    import      restore a claim archive\n\nVerification\n    verify      verify claim identity\n    audit       rerun acceptance criteria\n    assess      measure specification strength\n\nReconstruction\n    rebuild     rebuild an implementation from a claim\n    crosscheck  compare independent realizations\n\nEvidence\n    record      write an execution record\n    sign        authorize a claim or proof'

_EPILOG = "See 'ret <command> -h' for command usage.\nSee 'ret help <command>' for detailed help; 'ret help -a' lists everything,\nincluding accepted older spellings."

#: the fourteen. One concept each, grouped in the help above.
PORCELAIN = ("init", "run", "status", "pack",
             "pull", "export", "import",
             "verify", "audit", "assess",
             "rebuild", "crosscheck",
             "record", "sign")

#: accepted older spellings, which dispatch but are not the grammar. The
#: v1 metaphor vocabulary stays retired, and the 2026-09-22 folds
#: (seal -> pack --accept, hooks -> init, tree -> status --tree,
#: claims -> status --claims, attest -> record --key --as / --check) left
#: no alias behind: the fourteen plus the plumbing ARE the surface.
ALIASES = {}

#: reachable, unlisted in the fourteen-verb map: a hook is for a harness to
#: call, help and completion are for a shell.
PLUMBING = ("hook", "help", "completion")

_SYNOPSIS = {
    "init": ("ret init [PATH] [--agent claude | --no-agent]",
             """Initialize a workspace: a store for residue, a .gitignore
that keeps volatile history out of version control, and -- unless
--no-agent -- the coding-agent hooks wired into the agent's own settings,
idempotently and without touching anything else there.

There is no separate concept to learn: wiring an agent rides on init."""),
    "run": ("ret run COMMAND [-C DIR]",
            """Run a command inside a workspace and observe it.

The command's streams are the only output, and its exit code is returned
UNCHANGED -- so `ret run` can be used as a predicate exactly the way the
bare command could. The observation lands in the session's trace, where
`status` reads it and `pack` turns it into a claim."""),
    "status": ("ret status [PATH] [--all] [--files] [--tree] [--claims]",
               """Show what is here, and what has not been earned yet.

A PURE VIEW: it reads and reports and executes nothing, so every form is
instant and no form can change a verdict. Over a session it counts the
authoring triad -- observed, declared, unresolved. Over a claim it reports
identity, the audit receipt with its date, what the last assessment
decided, the recorded proof, the statements in both drawers, and the
discovery bill as testimony.

Every form ends with `next`: the first rung on the confidence ladder this
claim has not yet earned."""),
    "pack": ("ret pack [PATH] [--accept FILE -o CLAIM] [--generated PAT]\n"
             "         [--gate CMD --output FILE] [--pytest] "
             "[--environment LOCK]",
             """Create a claim from a project. The single authoring boundary.

Three sources, one verb. With a `reticuli.toml` already present, zero flags
seal it in place. With `--accept FILE -o CLAIM` it seals the session the
hooks observed. With `--generated`/`--gate`/`--output` (or `--pytest`) it
declares the boundary from flags.

The implementation is GENERATED -- outside the root, regrowable -- and the
check is the CLAIM. Pack refuses a gate whose every decider is generated:
such a verdict depends on nothing and the root would fit any implementation
that prints ok."""),
    "pull": ("ret pull CLAIM [-C DIR]",
             """Add another claim as a dependency of this workspace.

The claim's whole closure travels with it, each dependency once, so the
pulled claim stands alone: the source can be removed and every layer of it
still re-earns."""),
    "export": ("ret export CLAIM [ARCHIVE | -o ARCHIVE] [--blind]",
               """Write a portable claim archive.

DECLARED CONTENT ONLY, built from the recipe rather than the directory, so
a stray file does not travel; byte-deterministic, so two exports of one
claim are identical; and the ledger stays home, because it is one machine's
residue.

`--blind` writes the REBUILDER'S ROOM: the same claim minus its generated
outputs. The identity travels whole, because the root never covered the
implementation. `-o -` writes to standard output."""),
    "import": ("ret import ARCHIVE [DESTINATION]",
               """Restore a claim archive and verify it from the received
bytes alone.

A receiver trusts nothing it was sent: the root is recomputed here and
compared with the manifest that travelled with it. `-` reads standard
input, so `ret export ... -o - | ret import - DIR` round-trips."""),
    "verify": ("ret verify CLAIM",
               """Recompute the root from the bytes present and compare it
with the sealed manifest.

IDENTITY ONLY. Does not execute acceptance criteria -- no gate is run. This
answers "is this still the same claim?" in milliseconds. A VERDICT is
earned only by executing the gates, which is what `audit` is for, and a
tool that ran gates under the name `verify` would blur the one distinction
that matters most here."""),
    "audit": ("ret audit CLAIM [--shallow] [--no-strict] [--mutants N]\n"
              "          [--record FILE]",
              """Re-earn every verdict, cold, and re-check that the claim
still holds.

Nothing is carried in: the declared content is laid into a fresh room,
every gate is re-run sandboxed, and every pinned byte must reproduce.
Composed claims audit RECURSIVELY by default -- a component's own check is
re-run on the bytes this claim ships -- and `--shallow` is the explicit
opt-down to this claim's own gates.

Judging happens in the strict jail by default, so a claim's gates never
read your files; `--no-strict` opts down. `--mutants N` measures the check
as well as the claim. `--record FILE` preserves the execution as a
record."""),
    "assess": ("ret assess CLAIM [--mutants N]",
               """Measure how much this claim's own criteria actually prove.

Three buckets, because a strength report that counts an unmeasured property
as satisfied is the one failure mode that matters: MEASURED (this run
observed it), NOT MEASURED (live for this claim and not established here),
NOT APPLICABLE (the claim declares nothing for it to be about).

The measurement is root-stamped residue, so it stops being believed the
moment the root moves."""),
    "rebuild": ("ret rebuild CLAIM --producer CMD -o DIR "
                "[--without-guidance]",
                """Rebuild an implementation from a claim alone.

The room holds the criteria, the fixtures and the recipe the ROOT was
computed from; the generated sources are withheld, which is what makes the
result evidence about the claim rather than about the copy. The producer is
asked for each output in turn and the gates must pass before anything is
sealed.

`--producer` takes a name or any program. The shipped adapters answer to
their names -- `--producer openai`, `--producer anthropic`,
`--producer codex`, `--producer claude` (optionally `name:model`) -- and a
named producer preflights its credential before any money moves. Anything
else is passed through verbatim: a producer is any program that writes the
file it is told to write.

`--without-guidance` withholds every producer hint, so a pass measures what
the acceptance criteria alone carry."""),
    "crosscheck": ("ret crosscheck M1 [M2] M3 [--mutants N] "
                   "[--tolerance T]",
                   """Compare independent realizations: the three-machine
test.

M1 verifies in place, M2 arrives by transfer and verifies from the received
bytes alone, M3 is an independent rebuild. Valid means one root across all
three, every verdict re-earned, and every condition the claim DECLARED
holding. A leg may be a claim directory or a signed record; the two
transports must reach the same verdict.

Given two realizations, a real byte-copy M2 is materialized here and said
so, rather than quietly running a weaker two-legged test. The verdict is
three-valued: accept, reject, or incomplete -- and incomplete can never
accept, because unknown evidence is not evidence."""),
    "record": ("ret record CLAIM [-o FILE] [--key K --as ID] [--sign] "
               "[--check]",
               """Write an execution record: the one file this project
promises other programs may parse.

The gates are re-earned here, so the results are this machine's own, and
the file IS its canonical bytes -- sorted keys, default separators, no
prettying -- so its digest cites it exactly. `--key`/`--as` attests the
build inside the claim; `--check` verifies the attestations already there;
`-o -` writes to standard output."""),
    "sign": ("ret sign CLAIM [--key K --as ID] [--check] [--signers FILE]",
             """A human authorizes a claim. Never an agent's act.

With no key this prints the REVIEW PACKET -- what a keyholder would be
standing behind. With `--key` it signs it, after re-earning the verdicts
(and, on a composed claim, the composed verdict, because an endorsement
composes).

`--check` judges the authorizations present. Trust is verifier-relative: it
needs an anchor, an ssh `allowed_signers` file, from `--signers` or
RETICULI_SIGNERS. Unanchored, nothing is authorized to you, and `--check`
says so rather than reporting a signature it cannot attribute."""),
    "hook": ("ret hook [-C DIR]",
             """Plumbing: read one agent hook payload on standard input and
append it to the session's trace. Silent, and exits 0 whatever the payload
was -- a harness must never be broken by its own instrumentation."""),
    "help": ("ret help [TOPIC] [-a]",
             """Print the fuller account of a verb or topic. `-a` lists
everything, plumbing and accepted older spellings included."""),
    "completion": ("ret completion {bash|zsh}",
                   """Print a shell completion script, generated from this
grammar so it cannot drift from it."""),
}

_TOPICS = {
    "environment": """Every variable this tool reads, in one place.

  RETICULI_KEY           the ssh key `record --sign` and `sign` use when
                         none is named on the command line
  RETICULI_SIGNERS       the trust anchor: an ssh allowed_signers file.
                         Without one, nothing is authorized TO YOU
  RETICULI_PRODUCER      the producer the launcher regrows latent claims
                         with
  RETICULI_GATE_TIMEOUT  the host's own ceiling on a gate's wall-clock. It
                         can only tighten a claim's declared window
  RETICULI_TOLERANCE     a cost band this verifier applies. It may tighten
                         a claim's declared band, never loosen it
  RETICULI_CACHE         where reused verdicts are cached
  RETICULI_ENV_CACHE     where furnished environments are cached
  RETICULI_COLOR         always | never | auto (a tty)
  RETICULI_VENDOR        who ran the producer, recorded as a declaration
  RETICULI_MODEL         which model produced the bytes, likewise
  RETICULI_JAILED        set by this tool when it APPLIES a sandbox, read
                         when it is already inside one: sandboxes do not
                         nest

A gate sees none of these except RETICULI_JAILED. Its environment is
scrubbed to a minimal allowlist, so an inherited secret never reaches a
gate and a verdict cannot depend on one.""",
    "producers": """A producer is any program that writes the file it is
told to write.

The kernel sets RETICULI_OUTPUT to the absolute path of the output it wants
next, RETICULI_OUTPUTS to the whole work list as JSON, RETICULI_REQUEST to
the recipe's own guidance (unless the rebuild is blind), and
RETICULI_USAGE to a path where the producer may report what it spent.

The shipped adapters answer to their names: openai, anthropic, codex,
claude. Anything else is run verbatim.""",
    "identity": """A claim's root is a SHA-256 over what the claim IS: the
recipe's parsed content, the bytes of every pinned input, and the bytes of
every pinned step output. The generated outputs are deliberately OUTSIDE
it: an implementation can be deleted and regrown byte-different without
changing the claim's name.

So the root names an equivalence class, and two implementations that pass
the same pinned checks on the same pinned data are the same claim.""",
}


def _add_verbose_json(parser) -> None:
    """The three output levels, on every verb that has a result."""
    parser.add_argument("-v", "--verbose", action="store_true",
                        help=argparse.SUPPRESS)
    parser.add_argument("--json", action="store_true",
                        help=argparse.SUPPRESS)
    parser.add_argument("--color", choices=("auto", "always", "never"),
                        default="auto", help=argparse.SUPPRESS)
    parser.add_argument("--progress", action="store_true",
                        help=argparse.SUPPRESS)
    parser.add_argument("--quiet", action="store_true",
                        help=argparse.SUPPRESS)


def _parser():
    """The whole grammar. Returns the parser and its subparser table."""
    top = argparse.ArgumentParser(
        prog="ret", description=_DESC, epilog=_EPILOG, add_help=True,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    top.add_argument("--version", action="store_true",
                     help=argparse.SUPPRESS)
    sub = top.add_subparsers(dest="cmd", metavar="COMMAND")

    def verb(name, help_text=None):
        # no `help=`: argparse would then list the verb a SECOND time,
        # under its own heading, and the map above is the one that is
        # organized by concept. The map is the contract; this is plumbing.
        made = sub.add_parser(name, add_help=False,
                              description=_SYNOPSIS.get(name, ("", ""))[0])
        made.add_argument("-h", action="help", help=argparse.SUPPRESS)
        _add_verbose_json(made)
        return made

    p = verb("init", "initialize a workspace")
    p.add_argument("path", nargs="?", default=".")
    p.add_argument("--agent", default=None)
    p.add_argument("--no-agent", action="store_true")

    p = verb("run", "run and observe a command")
    p.add_argument("command", nargs="+")
    p.add_argument("-C", "--workspace", default=".")

    p = verb("status", "show work, claims, and unresolved inputs")
    p.add_argument("path", nargs="?", default=".")
    p.add_argument("--all", action="store_true",
                   help="the full account, file by file")
    p.add_argument("--files", action="store_true",
                   help="every declared file, by role")
    p.add_argument("--tree", action="store_true",
                   help="the claim or session as a tree")
    p.add_argument("--claims", action="store_true",
                   help="the claims in this workspace's store")

    p = verb("pack", "create a claim from a project")
    p.add_argument("path", nargs="?", default=".")
    p.add_argument("--name", default=None)
    p.add_argument("--root", default=None)
    p.add_argument("--accept", nargs="+", default=None,
                   help="the verdict file(s) a session earned")
    p.add_argument("-o", "--into", default=None,
                   help="where to write the sealed claim")
    p.add_argument("--generated", nargs="+", default=None)
    p.add_argument("--inputs", nargs="+", default=None)
    p.add_argument("--carried", nargs="+", default=None)
    p.add_argument("--gate", default=None)
    p.add_argument("--output", default=None,
                   help="the verdict file --gate earns")
    p.add_argument("--pytest", nargs="?", const="tests", default=None,
                   help="declare a pytest suite as the gate")
    p.add_argument("--environment", default=None,
                   help="a hash-pinned requirements file, pinned as input")
    p.add_argument("--inputs-manifest", dest="inputs_manifest", default=None)
    p.add_argument("--envelope", default=None,
                   help="declared cost ceilings, unit=value")
    p.add_argument("--mutation-floor", dest="mutation_floor", type=float,
                   default=None)
    p.add_argument("--requires", nargs="+", default=None)
    p.add_argument("--by", default=None)
    p.add_argument("--format", dest="claim_format", type=int, default=None)
    p.add_argument("--force", action="store_true")

    p = verb("pull", "add another claim as a dependency")
    p.add_argument("claim")
    p.add_argument("-C", "--workspace", default=".")

    p = verb("export", "write a portable claim archive")
    p.add_argument("claim")
    p.add_argument("archive", nargs="?", default=None)
    p.add_argument("-o", "--output", dest="output", default=None)
    p.add_argument("--blind", action="store_true",
                   help="withhold the generated outputs: the room")

    p = verb("import", "restore a claim archive")
    p.add_argument("archive")
    p.add_argument("destination", nargs="?", default=None)

    p = verb("verify", "verify claim identity")
    p.add_argument("claim", nargs="?", default=".")

    p = verb("audit", "rerun acceptance criteria")
    p.add_argument("claim", nargs="?", default=".")
    p.add_argument("--shallow", action="store_true",
                   help="this claim's own gates only")
    p.add_argument("--strict", action="store_true")
    p.add_argument("--no-strict", dest="no_strict", action="store_true")
    p.add_argument("--reuse", action="store_true")
    p.add_argument("--trust", default="self")
    p.add_argument("--mutants", type=int, default=None)
    p.add_argument("--record", default=None)

    p = verb("assess", "measure specification strength")
    p.add_argument("claim", nargs="?", default=".")
    p.add_argument("--mutants", type=int, default=None)

    p = verb("rebuild", "rebuild an implementation from a claim")
    p.add_argument("claim")
    p.add_argument("--producer", default=None)
    p.add_argument("-o", "--into", default=None)
    p.add_argument("--without-guidance", dest="without_guidance",
                   action="store_true")

    p = verb("crosscheck", "compare independent realizations")
    p.add_argument("legs", nargs="*")
    p.add_argument("--mutants", type=int, default=None,
                   help="hold the redo to a declared mutation floor")
    p.add_argument("--tolerance", type=float, default=None)

    p = verb("record", "write an execution record")
    p.add_argument("claim", nargs="?", default=".")
    p.add_argument("-o", "--output", default=None)
    p.add_argument("--key", default=None)
    p.add_argument("--as", dest="identity", default=None)
    p.add_argument("--sign", action="store_true")
    p.add_argument("--check", action="store_true")
    p.add_argument("--signers", default=None)

    p = verb("sign", "authorize a claim or proof")
    p.add_argument("claim", nargs="?", default=".")
    p.add_argument("--key", default=None)
    p.add_argument("--as", dest="identity", default=None)
    p.add_argument("--check", action="store_true")
    p.add_argument("--signers", default=None)
    p.add_argument("-C", "--workspace", default=None)

    p = verb("hook")
    p.add_argument("-C", "--workspace", default=".")

    p = verb("help")
    p.add_argument("topic", nargs="?", default=None)
    p.add_argument("-a", "--all", dest="everything", action="store_true")

    p = verb("completion")
    p.add_argument("shell", nargs="?", default="bash",
                   choices=("bash", "zsh"))

    return top, sub


def verbs() -> list:
    """Every name that dispatches: the fourteen, the accepted older
    spellings, and the plumbing. Nothing else is a ret command."""
    return list(PORCELAIN) + list(ALIASES) + list(PLUMBING)


_FULL_HELP = {}


def _full(name: str) -> str:
    synopsis, body = _SYNOPSIS.get(name, (None, None))
    if synopsis is None:
        return ""
    return (f"NAME\n    ret {name}\n\nSYNOPSIS\n    "
            + synopsis.replace("\n", "\n    ")
            + "\n\nDESCRIPTION\n    " + body.replace("\n", "\n    ") + "\n")


for _name in _SYNOPSIS:
    _FULL_HELP[_name] = _full(_name)
for _name, _text in _TOPICS.items():
    _FULL_HELP[_name] = (f"TOPIC\n    {_name}\n\nSYNOPSIS\n    "
                         f"ret help {_name}\n\nDESCRIPTION\n    "
                         + _text.replace("\n", "\n    ") + "\n")


def _help_topic(topic: str) -> int:
    """The fuller account of one verb or topic."""
    text = _FULL_HELP.get(topic)
    if not text:
        return 2
    print(text.rstrip())
    return 0


def _help_all() -> int:
    """Everything that dispatches, including what the map does not list."""
    print(_DESC)
    print()
    print("Plumbing")
    for name in PLUMBING:
        print(f"    {name:<11} {'(reachable, unlisted above)'}")
    print()
    print("Accepted older spellings")
    if ALIASES:
        for name, target in sorted(ALIASES.items()):
            print(f"    {name:<11} -> {target}")
    else:
        print("    none: the fourteen verbs plus the plumbing are the "
              "whole surface")
    print()
    print("Topics")
    for name in sorted(_TOPICS):
        print(f"    {name:<11} ret help {name}")
    print()
    print(_EPILOG)
    return 0


def _completion(shell: str = "bash") -> int:
    """A completion script generated from the grammar itself."""
    names = " ".join(sorted(verbs()))
    if shell == "zsh":
        print("#compdef ret")
        print(f"_ret() {{ _arguments '1:command:({names})' '*:file:_files' }}")
        print("compdef _ret ret")
        return 0
    print("# bash completion for ret, generated from the grammar")
    print("_ret_completion() {")
    print(f'    local verbs="{names}"')
    print('    if [ "$COMP_CWORD" -eq 1 ]; then')
    print('        COMPREPLY=( $(compgen -W "$verbs" -- '
          '"${COMP_WORDS[1]}") )')
    print("    else")
    print('        COMPREPLY=( $(compgen -f -- '
          '"${COMP_WORDS[COMP_CWORD]}") )')
    print("    fi")
    print("}")
    print("complete -F _ret_completion ret")
    return 0
