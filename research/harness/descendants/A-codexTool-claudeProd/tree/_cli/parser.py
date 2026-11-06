"""The argv grammar: fourteen verbs, one concept each.

The command surface is a MENTAL MAP a reader goes down top to bottom —
observe, declare, test, reconstruct, compare, preserve — not a flat verb
dump.  A census showed that structure evaporates unless a gate demands it, so
the groups, their order, and their membership are ratified by the surface
criterion; the wording of each line stays free.

Two levels of help, deliberately different.  `ret <verb> -h` is concise
usage, generated from the grammar itself.  `ret help <verb>` (and `--verb
--help`) is the fuller account, which is where a user learns what a verb
MEANS rather than what it takes — the `verify`/`audit` distinction, for
instance, lives there because that is where someone reads it.  `ret help -a`
lists everything, plumbing included.

Completion is generated FROM the parser, so it cannot drift from it.  A
completion table maintained by hand is a second grammar that silently stops
agreeing with the first.
"""
import argparse
import sys

#: The fourteen, in the order the help presents them.
PORCELAIN = ('init', 'run', 'status', 'pack', 'pull', 'export', 'import', 'verify', 'audit', 'assess', 'rebuild', 'crosscheck', 'record', 'sign',)
#: Plumbing: reachable, never in the fourteen-verb map.
PLUMBING = ("hook", "help", "completion")
#: Accepted older spellings.  Empty: the v1 metaphor vocabulary is retired,
#: and the folds (seal -> pack --accept, hooks -> init, tree/claims ->
#: status, attest -> record) left no alias behind.  `spec/layers.md` keeps
#: the rename map; this is the command surface.
ALIASES = {}

_DESC = 'Reticuli records and reproduces software claims.\n\nAuthoring\n    init        initialize a workspace\n    run         run and observe a command\n    status      show work, claims, and unresolved inputs\n    pack        create a claim from a project\n\nComposition and transport\n    pull        add another claim as a dependency\n    export      write a portable claim archive\n    import      restore a claim archive\n\nVerification\n    verify      verify claim identity\n    audit       rerun acceptance criteria\n    assess      measure specification strength\n\nReconstruction\n    rebuild     rebuild an implementation from a claim\n    crosscheck  compare independent realizations\n\nEvidence\n    record      write an execution record\n    sign        authorize a claim or proof'

_EPILOG = "See 'ret <command> -h' for command usage.\nSee 'ret help <command>' for detailed help; 'ret help -a' lists everything,\nincluding accepted older spellings."

#: Every environment variable this tool reads, documented in ONE place.  A
#: variable a tool consults and never names is an undocumented interface.
_ENVIRONMENT = """ENVIRONMENT

    RETICULI_KEY          the ssh key `record --sign` and `sign` use when
                          no --key is given
    RETICULI_SIGNERS      the allowed_signers file that anchors trust; with
                          none reachable, nothing is authorized to you
    RETICULI_PRODUCER     the producer the launcher invokes for a latent
                          claim
    RETICULI_GATE_TIMEOUT a host ceiling on every gate, in seconds; it may
                          tighten a claim's declared bound, never loosen it
    RETICULI_TOLERANCE    the cost band applied when a claim declares none
                          (an observation either way)
    RETICULI_CACHE        where earned verdicts are remembered
    RETICULI_ENV_CACHE    where furnished environments are cached
    RETICULI_COLOR        always | never | auto (the default: a tty)
    RETICULI_VENDOR       the vendor a rebuild declares on its ledger
    RETICULI_MODEL        the model a rebuild declares on its ledger
    RETICULI_PRICE        a price hint handed through to a producer
    RETICULI_AGENT_TURNS  a turn budget handed through to a producer
    RETICULI_JAILED       set BY this tool for a gate: the sandbox it is
                          already inside, so sandboxes do not nest

  A gate sees none of the above except RETICULI_JAILED: its environment is
  scrubbed to a minimal host allowlist, so an inherited secret can never be
  read by a claim's own tests.  A producer is the caller's oracle and keeps
  the caller's HOME; what the caller does not hand over never arrives.
"""

_FULL_HELP = {
    "init": """SYNOPSIS
    ret init [<path>] [--agent <name>] [--no-agent]

  Mark a directory as a workspace: a store for claims, and git-native
  ignores so residue never lands in a commit.  Agent wiring rides this verb
  because the handshake is not a separate concept to learn; --agent claude
  installs the hooks idempotently, preserving everything else in the
  agent's settings.
""",
    "run": """SYNOPSIS
    ret run <command> [-C <workspace>]

  Observe a command and return its exit code UNCHANGED, so `ret run` is
  usable as a predicate exactly where the bare command was.  The command's
  own stdout and stderr pass straight through; this wrapper adds nothing to
  either stream.
""",
    "status": """SYNOPSIS
    ret status [<path>] [--all] [--files] [--tree] [--claims] [--deps]

  The one view.  It READS and REPORTS, never executes, so every form is
  instant and what it says about execution is a dated receipt rather than a
  fact established now.  Every form ends with `next`: the first rung on the
  confidence ladder this claim has not yet earned.

  On a session it shows the authoring triad -- observed, declared,
  unresolved.  On a claim it shows identity, the audit receipt, the
  measurement, the proof, and the statements.  --files lists every declared
  file by role, hiding none.
""",
    "pack": """SYNOPSIS
    ret pack [<path>] [--accept <verdict> -o <claim>] [--name <name>]
             [--generated <glob>] [--gate <command>] [--pytest]
             [--environment <file>] [--carried <glob>] [--force]

  The single authoring boundary: a project or a session becomes a claim.
  Three sources, one verb -- a traced session (--accept), a declared recipe
  already in the directory (no flags at all), or flags naming the gate and
  the implementation.

  A claim's boundary is DECLARED, never inferred from provenance: a gate
  whose every decider is generated is refused as vacuous, because its
  verdict would depend on no claim.
""",
    "pull": """SYNOPSIS
    ret pull <claim> [<workspace>]

  Add another claim as a dependency of this workspace.  The whole closure
  travels, so the pulled claim STANDS ALONE -- with its source removed it
  still verifies and its chain still re-earns -- and it stays compact: each
  dependency's bytes appear once, never once per path that reaches them.
""",
    "export": """SYNOPSIS
    ret export <claim> [<archive>] [-o <archive>] [--blind]

  Write a portable archive of exactly the claim's declared content: no
  ledger, no stray file from your working directory.  The archive is
  byte-deterministic, so it can itself be cited by digest.

  --blind withholds the generated outputs.  That is the rebuilder's ROOM:
  the identity travels whole, because the root never covered the
  implementation, and what the archive withholds is exactly what a producer
  is asked to regrow.  `-` is the standard stream.
""",
    "import": """SYNOPSIS
    ret import <archive> <destination>

  Restore an archive and verify the identity from the RECEIVED bytes --
  which is the whole point: nothing corrupted or substituted in transit,
  judged from what arrived rather than from what the sender said.  `-` is
  the standard stream.
""",
    "verify": """SYNOPSIS
    ret verify [<claim>] [--json] [-v]

  Recompute the root from the bytes present and compare it with the sealed
  manifest.  Identity ONLY, in milliseconds.

  Does not execute acceptance criteria.  That division is load-bearing: a
  root says what a claim IS, never that it currently holds, and a verdict is
  earned only by running the gates.  `ret audit` is the verb that re-earns
  one; a tool that ran gates under the name `verify` would blur the one
  distinction the whole design exists to keep sharp.
""",
    "audit": """SYNOPSIS
    ret audit [<claim>] [--shallow] [--no-strict] [--mutants <n>]
              [--record <path>] [--json] [-v]

  Re-execute every gate, cold and sandboxed, and re-check that the claim
  still holds.  The ONLY verb that re-earns a verdict: it deletes nothing
  and trusts nothing, so a stored "passed" is never evidence.

  Composed claims audit recursively by default -- a component's own criteria
  are re-run on the bytes THIS claim ships, because this claim's gate is
  blind to a forgery its own check does not exercise.  --shallow is the
  explicit, honest opt-down to this claim's own gates.  Judging happens in
  the strict jail unless --no-strict opts down.
""",
    "assess": """SYNOPSIS
    ret assess [<claim>] [--mutants <n>] [--json] [-v]

  Measure how much the criteria actually prove: how wide the equivalence
  class the root names really is.  Reported in three buckets -- measured,
  not measured, not applicable -- because one number would hide which of
  them a reader should act on.  The measurement is left as root-stamped
  residue, and read back only while the root still matches.
""",
    "rebuild": """SYNOPSIS
    ret rebuild <claim> --producer <name|command> -o <destination>
                [--without-guidance] [--json] [-v]

  Regrow the generated outputs from the pinned inputs alone, in a fresh
  room, until the gates pass.

  The generated sources are withheld from that room.  The producer sees the
  recipe, the criteria and the fixtures, and nothing else, so a pass
  measures what the acceptance criteria carry rather than what a copy
  carried.  --without-guidance withholds the producer hints too, which
  measures what the criteria alone carry.

  A producer is any program: a command is run verbatim, with the caller's
  reachability and the caller's HOME, because a model CLI's credential lives
  there.  The shipped adapters also answer to their names, and a named
  producer preflights its credential before any money moves:

      --producer openai       an OpenAI SDK producer (OPENAI_API_KEY)
      --producer anthropic    an Anthropic SDK producer (ANTHROPIC_API_KEY)
      --producer codex        the codex CLI, driven non-interactively
      --producer claude       the claude CLI, driven non-interactively
""",
    "crosscheck": """SYNOPSIS
    ret crosscheck <m1> [<m2>] <m3> [--mutants <n>] [--tolerance <t>]
                   [--json] [-v]

  The three-machine test.  M1 verifies in place, M2 is the claim received
  elsewhere from the transferred bytes alone, M3 is an independent rebuild.
  Valid when all three share one root, every gate re-earns, and every
  condition the claim DECLARED holds.

  Roles are inferred from position, never named by a leg: a record cannot
  misstate its role, only its facts.  Given two realizations, a real
  byte-copy M2 is materialized and the result discloses that it was.

  --mutants holds the redo to a declared mutation floor.  The verdict is
  three-valued: a declared condition this run could not measure makes it
  `incomplete`, which can never accept.
""",
    "record": """SYNOPSIS
    ret record <claim> [-o <path>] [--key <key>] [--sign] [--as <identity>]
               [--check] [--signers <file>] [--json] [-v]

  Write an execution record: the one document this project promises other
  programs may parse.  Emitting one EARNS the verdicts first -- a record
  states what this machine established, not what it was told.

  A record is about a ROOT, so an unsealed or drifted claim gets a refusal
  instead.  A record whose gates failed is valid and worth keeping: a failed
  rebuild is evidence about the claim.

  --key/--as attests this build inside the claim; --check verifies the
  attestations already there; -o writes the record itself, signed in the
  record's own namespace when a key is given.
""",
    "sign": """SYNOPSIS
    ret sign <claim> [--key <key>] [--as <identity>] [--check]
             [--signers <file>] [--json] [-v]

  The human ceremony, never an agent's act.  With no key it emits the review
  PACKET -- what a signer would be standing behind -- and with a key it
  authorizes that packet by digest, so the reviewable artifact cannot later
  be anything other than what was signed.

  SIGNED means AUTHORIZED by a signer you anchor AND PROVEN by a recorded
  crosscheck.  Both halves are verifier-relative: with no reachable
  allowed_signers file, --check refuses, because unanchored a signature is
  valid for whatever key is embedded in it and the honest answer is that
  nothing is authorized to you.
""",
    "hook": """SYNOPSIS
    ret hook [-C <workspace>]

  Plumbing.  Reads one agent hook payload on standard input and records it
  as a session observation, or does nothing: no session, no-op, and a file
  outside the session is ignored.  Silent, always exit 0 -- a handshake that
  failed an agent's tool call would be worse than no handshake.
""",
    "help": """SYNOPSIS
    ret help [<topic>] [-a]

  The fuller account of a verb, or of a topic.  `ret help -a` lists
  everything, plumbing included.  `ret help environment` documents every
  variable this tool reads.
""",
    "completion": """SYNOPSIS
    ret completion <bash|zsh>

  Emit a shell completion script, generated FROM the parser -- so it cannot
  drift from the grammar it completes.
""",
    "environment": _ENVIRONMENT,
}


class _Top(argparse.ArgumentParser):
    """The top-level parser, whose help IS the grouped map.

    Written out rather than assembled by argparse: the groups and their
    order are the contract, and a formatter that re-flowed them would make
    the map depend on terminal width.
    """

    def format_help(self) -> str:
        return (f"usage: ret [-h] [--version] <command> [<args>]\n\n"
                f"{_DESC}\n\n{_EPILOG}\n")

    def error(self, message):
        print(f"ret: {message}", file=sys.stderr)
        raise SystemExit(2)


def _add_verbose_json(parser) -> None:
    """The three registers every answering verb offers."""
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="the explanatory account")
    parser.add_argument("--json", action="store_true",
                        help="the machine envelope")
    parser.add_argument("--color", choices=("auto", "always", "never"),
                        default="auto", help="colour, as ls does it")


def _sub(subparsers, name: str, **kwargs):
    """A verb parser whose -h is usage and whose --help is the account."""
    parser = subparsers.add_parser(name, add_help=False, prog=f"ret {name}",
                                   **kwargs)
    parser.add_argument("-h", action="help", help="concise usage")
    parser.add_argument("--help", action="store_true", dest="full_help",
                        help="the fuller account")
    return parser


def _parser():
    """Build the grammar; hand back the parser and its verb table."""
    top = _Top(prog="ret", add_help=False)
    top.add_argument("-h", "--help", action="store_true", dest="top_help")
    top.add_argument("--version", action="store_true")
    # Plain ArgumentParser for the verbs: _Top's help IS the grouped map,
    # and a verb inheriting it would answer `ret verify -h` with the map
    # instead of that verb's own usage.
    subparsers = top.add_subparsers(dest="cmd", metavar="",
                                    parser_class=argparse.ArgumentParser)
    table = {}

    table["init"] = _sub(subparsers, "init")
    table["init"].add_argument("path", nargs="?", default=".")
    table["init"].add_argument("--agent", default=None,
                               help="wire an agent's hooks (e.g. claude)")
    table["init"].add_argument("--no-agent", action="store_true")
    _add_verbose_json(table["init"])

    table["run"] = _sub(subparsers, "run")
    table["run"].add_argument("command", nargs="+")
    table["run"].add_argument("-C", "--workspace", default=".")

    table["status"] = _sub(subparsers, "status")
    table["status"].add_argument("path", nargs="?", default=".")
    table["status"].add_argument("--all", action="store_true",
                                 help="the whole ledger of this claim")
    table["status"].add_argument("--files", action="store_true",
                                 help="every declared file, by role")
    table["status"].add_argument("--tree", action="store_true",
                                 help="what this claim is made of")
    table["status"].add_argument("--claims", action="store_true",
                                 help="the claims this workspace knows")
    table["status"].add_argument("--deps", action="store_true",
                                 help="the component DAG")
    _add_verbose_json(table["status"])

    table["pack"] = _sub(subparsers, "pack")
    table["pack"].add_argument("path", nargs="?", default=".")
    table["pack"].add_argument("--name", default=None)
    table["pack"].add_argument("--root", default=None,
                               help="an expected root to confirm")
    table["pack"].add_argument("--generated", action="append", default=None,
                               help="a glob of regrowable outputs")
    table["pack"].add_argument("--carried", action="append", default=None,
                               help="a glob of files that ship, never regrow")
    table["pack"].add_argument("--gate", default=None,
                               help="the command that decides acceptance")
    table["pack"].add_argument("--pytest", action="store_true",
                               help="use pytest as the gate")
    table["pack"].add_argument("--environment", default=None,
                               help="a hash-pinned requirements file")
    table["pack"].add_argument("--inputs-manifest", default=None,
                               dest="inputs_manifest")
    table["pack"].add_argument("--mutation-floor", default=None, type=float,
                               dest="mutation_floor")
    table["pack"].add_argument("--requires", action="append", default=None)
    table["pack"].add_argument("--accept", action="append", default=None,
                               help="a verdict this session earned")
    table["pack"].add_argument("-o", "--output", default=None,
                               help="where the claim is written")
    table["pack"].add_argument("--into", default=None)
    table["pack"].add_argument("--force", action="store_true")
    _add_verbose_json(table["pack"])

    table["pull"] = _sub(subparsers, "pull")
    table["pull"].add_argument("claim")
    table["pull"].add_argument("workspace", nargs="?", default=".")
    _add_verbose_json(table["pull"])

    table["export"] = _sub(subparsers, "export")
    table["export"].add_argument("claim")
    table["export"].add_argument("archive", nargs="?", default=None)
    table["export"].add_argument("-o", "--output", default=None)
    table["export"].add_argument("--blind", action="store_true",
                                 help="withhold the generated outputs")
    _add_verbose_json(table["export"])

    table["import"] = _sub(subparsers, "import")
    table["import"].add_argument("archive")
    table["import"].add_argument("dest", nargs="?", default=".")
    _add_verbose_json(table["import"])

    table["verify"] = _sub(subparsers, "verify")
    table["verify"].add_argument("claim", nargs="?", default=".")
    _add_verbose_json(table["verify"])

    table["audit"] = _sub(subparsers, "audit")
    table["audit"].add_argument("claim", nargs="?", default=".")
    table["audit"].add_argument("--shallow", action="store_true",
                                help="this claim's own gates only")
    table["audit"].add_argument("--no-strict", action="store_true",
                                dest="no_strict")
    table["audit"].add_argument("--strict", action="store_true")
    table["audit"].add_argument("--reuse", action="store_true")
    table["audit"].add_argument("--trust", default="self")
    table["audit"].add_argument("--mutants", default=None, type=int)
    table["audit"].add_argument("--record", default=None,
                                help="preserve this execution as a record")
    table["audit"].add_argument("--progress", action="store_true")
    table["audit"].add_argument("--quiet", action="store_true")
    _add_verbose_json(table["audit"])

    table["assess"] = _sub(subparsers, "assess")
    table["assess"].add_argument("claim", nargs="?", default=".")
    table["assess"].add_argument("--mutants", default=None, type=int)
    _add_verbose_json(table["assess"])

    table["rebuild"] = _sub(subparsers, "rebuild")
    table["rebuild"].add_argument("claim")
    table["rebuild"].add_argument("--producer", default=None)
    table["rebuild"].add_argument("-o", "--output", default=None)
    table["rebuild"].add_argument("--without-guidance", action="store_true",
                                  dest="without_guidance")
    _add_verbose_json(table["rebuild"])

    table["crosscheck"] = _sub(subparsers, "crosscheck")
    table["crosscheck"].add_argument("legs", nargs="*")
    table["crosscheck"].add_argument("--mutants", default=None, type=int,
                                     help="hold the redo to a mutation floor")
    table["crosscheck"].add_argument("--tolerance", default=None, type=float)
    _add_verbose_json(table["crosscheck"])

    table["record"] = _sub(subparsers, "record")
    table["record"].add_argument("claim", nargs="?", default=".")
    table["record"].add_argument("-o", "--output", default=None)
    table["record"].add_argument("--key", default=None)
    table["record"].add_argument("--as", dest="identity", default=None)
    table["record"].add_argument("--sign", action="store_true")
    table["record"].add_argument("--check", action="store_true")
    table["record"].add_argument("--signers", default=None)
    _add_verbose_json(table["record"])

    table["sign"] = _sub(subparsers, "sign")
    table["sign"].add_argument("claim", nargs="?", default=".")
    table["sign"].add_argument("--key", default=None)
    table["sign"].add_argument("--as", dest="identity", default=None)
    table["sign"].add_argument("--check", action="store_true")
    table["sign"].add_argument("--signers", default=None)
    _add_verbose_json(table["sign"])

    table["hook"] = _sub(subparsers, "hook")
    table["hook"].add_argument("-C", "--workspace", default=".")

    table["help"] = _sub(subparsers, "help")
    table["help"].add_argument("topic", nargs="?", default=None)
    table["help"].add_argument("-a", "--all", action="store_true",
                               dest="all_topics")

    table["completion"] = _sub(subparsers, "completion")
    table["completion"].add_argument("shell", nargs="?", default="bash")

    return top, table


def verbs() -> list:
    """Every name that dispatches — the map, the aliases, and the plumbing."""
    return list(PORCELAIN) + list(ALIASES) + list(PLUMBING)


def _help_topic(name: str) -> int:
    """The fuller account of one verb or topic."""
    topic = ALIASES.get(name, name)
    text = _FULL_HELP.get(topic)
    if not text:
        print(f"ret: help: no topic {name!r}; try `ret help -a`",
              file=sys.stderr)
        return 2
    print(text.rstrip())
    return 0


def _help_all() -> int:
    """Everything, plumbing and older spellings included."""
    print(_DESC)
    print()
    print("Plumbing")
    for name in PLUMBING:
        print(f"    {name}")
    print()
    print("Accepted older spellings")
    if ALIASES:
        for name, target in sorted(ALIASES.items()):
            print(f"    {name} -> {target}")
    else:
        print("    none: the fourteen plus plumbing are the whole grammar")
    print()
    print("Topics")
    print("    environment    every variable this tool reads")
    print()
    print(_EPILOG)
    return 0


def _completion(shell: str = "bash") -> int:
    """A completion script, generated from the grammar it completes."""
    names = " ".join(verbs())
    if shell == "zsh":
        print("#compdef ret")
        print(f'_ret() {{ _arguments "1: :({names})" "*::arg:->args" }}')
        print("_ret \"$@\"")
        return 0
    print("# bash completion for ret, generated from the parser")
    print("_ret_complete() {")
    print("    local cur=${COMP_WORDS[COMP_CWORD]}")
    print(f'    local verbs="{names}"')
    print('    if [ "$COMP_CWORD" -eq 1 ]; then')
    print('        COMPREPLY=( $(compgen -W "$verbs" -- "$cur") )')
    print("    else")
    print('        COMPREPLY=( $(compgen -f -- "$cur") )')
    print("    fi")
    print("}")
    print("complete -F _ret_complete ret")
    return 0
