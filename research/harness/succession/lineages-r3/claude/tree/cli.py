"""The human handshake: the argv grammar, help and completion, and `main`
(spec/layers.md, "surface"). Fourteen porcelain verbs, one concept each,
grouped in `-h` by workflow concept; three plumbing entries (`hook`,
`help`, `completion`) read the grammar or serve the coding-agent handshake
rather than acting on a claim. No older spellings dispatch any more --
`spec/layers.md`'s v1 names, and a handful that lived briefly as verbs of
their own, are retired; the parser never registers them, so they fall
through to the same "not a ret command" refusal as any other typo, with
the nearest real verb suggested.

`-h` on a subcommand is concise usage; `--help` is the fuller SYNOPSIS/
DESCRIPTION account `ret help <verb>` also prints -- two different
questions ("how do I invoke this" vs "what does this do"), two different
answers, so each gets its own flag rather than overloading one.

`verbs()` is every name `main` actually dispatches: the fourteen porcelain
verbs plus the three plumbing entries, read straight off the grammar this
module builds, so it cannot drift from what `-h` and `completion` show.
"""
import argparse
import difflib
import sys

from ._cli import dispatch

PORCELAIN = (
    "init", "run", "status", "pack",
    "pull", "export", "import",
    "verify", "audit", "assess",
    "rebuild", "crosscheck",
    "record", "sign",
)
PLUMBING = ("hook", "help", "completion")

_VERSION = "3.0"

_DESC = (
    "Reticuli records and reproduces software claims.\n"
    "\n"
    "Authoring\n"
    "    init        initialize a workspace\n"
    "    run         run and observe a command\n"
    "    status      show work, claims, and unresolved inputs\n"
    "    pack        create a claim from a project\n"
    "\n"
    "Composition and transport\n"
    "    pull        add another claim as a dependency\n"
    "    export      write a portable claim archive\n"
    "    import      restore a claim archive\n"
    "\n"
    "Verification\n"
    "    verify      verify claim identity\n"
    "    audit       rerun acceptance criteria\n"
    "    assess      measure specification strength\n"
    "\n"
    "Reconstruction\n"
    "    rebuild     rebuild an implementation from a claim\n"
    "    crosscheck  compare independent realizations\n"
    "\n"
    "Evidence\n"
    "    record      write an execution record\n"
    "    sign        authorize a claim or proof\n"
)

_EPILOG = (
    "See 'ret <command> -h' for concise usage.\n"
    "See 'ret help <command>' or 'ret <command> --help' for the full account.\n"
    "See 'ret help -a' for everything, including retired spellings.\n"
)

_ENV_HELP = (
    "Environment variables ret reads:\n\n"
    "    RETICULI_PRODUCER   the rebuild producer: a named one (openai,\n"
    "                        anthropic, codex) or a literal shell command\n"
    "    OPENAI_API_KEY      credential for --producer openai\n"
    "    ANTHROPIC_API_KEY   credential for --producer anthropic\n"
    "    RETICULI_KEY        the signing identity for record --sign\n"
    "    RETICULI_SIGNERS    the allowed_signers file record/sign --check\n"
    "                        verify authorizations and attestations against\n"
    "    RETICULI_COLOR      auto (default, a tty) | always | never\n"
    "    RETICULI_GATE_TIMEOUT  a host ceiling on every gate's wall clock\n"
    "    RETICULI_JAILED     already-inside-a-sandbox signal; internal\n"
)

_FULL_HELP = {
    "init": (
        "SYNOPSIS\n    ret init [workspace] [--agent NAME] [--no-agent]\n\n"
        "DESCRIPTION\n"
        "    Mark a directory as a reticuli workspace: create its .reticuli\n"
        "    store if missing. --agent claude additionally wires the\n"
        "    coding-agent hooks into the workspace's Claude Code settings;\n"
        "    --no-agent is the explicit, and default, opt-out. Idempotent.\n"
    ),
    "run": (
        "SYNOPSIS\n    ret run <cmd> [-C workspace]\n\n"
        "DESCRIPTION\n"
        "    Run cmd as a shell command with workspace as its working\n"
        "    directory, and hand back the child's exit code completely\n"
        "    unwrapped, so a session can chain it as a predicate.\n"
    ),
    "status": (
        "SYNOPSIS\n    ret status [workspace] [--all] [--files] [--tree] [--claims]\n\n"
        "DESCRIPTION\n"
        "    Show work, claims, and unresolved inputs. A pure view: it never\n"
        "    executes a gate and never fails -- it reports what is on disk\n"
        "    and names the next rung of the ladder.\n"
    ),
    "pack": (
        "SYNOPSIS\n    ret pack [workspace] [--accept OUTPUT...] [-o PATH] [--name NAME]\n\n"
        "DESCRIPTION\n"
        "    Create a claim from a project: a traced session's draft,\n"
        "    certified cold and sealed at -o/--output, or (with a recipe\n"
        "    already declared in place) the zero-flag seal of exactly that\n"
        "    declaration.\n"
    ),
    "pull": (
        "SYNOPSIS\n    ret pull <source> [workspace]\n\n"
        "DESCRIPTION\n    Add another claim's declared bytes as a dependency.\n"
    ),
    "export": (
        "SYNOPSIS\n    ret export [claim] [tar] [-o PATH] [--blind]\n\n"
        "DESCRIPTION\n"
        "    Write a portable claim archive: the recipe, the pinned inputs,\n"
        "    every present step output. --blind withholds every generated\n"
        "    output -- the room a rebuilder is handed. '-' is the standard\n"
        "    stream.\n"
    ),
    "import": (
        "SYNOPSIS\n    ret import <archive> [workspace]\n\n"
        "DESCRIPTION\n"
        "    Restore a claim archive and verify identity immediately from\n"
        "    the received bytes. '-' is the standard stream.\n"
    ),
    "verify": (
        "SYNOPSIS\n    ret verify [claim]\n\n"
        "DESCRIPTION\n"
        "    Verify claim identity: recompute the root from the bytes\n"
        "    present and compare it to the sealed manifest.\n"
        "    Does not execute acceptance criteria -- that is `ret audit`.\n"
    ),
    "audit": (
        "SYNOPSIS\n    ret audit [claim] [--shallow] [--no-strict] "
        "[--mutants N] [--record PATH]\n\n"
        "DESCRIPTION\n"
        "    Rerun acceptance criteria: re-earn every gate cold, in a\n"
        "    sandboxed room built fresh from the claim's own bytes -- a\n"
        "    claim's gates never read your files by default; --no-strict\n"
        "    opts down. Deep by default (every declared component re-earns\n"
        "    its own gate too); --shallow opts out.\n"
    ),
    "assess": (
        "SYNOPSIS\n    ret assess [claim] [--mutants N]\n\n"
        "DESCRIPTION\n"
        "    Measure specification strength: how much of the claim's\n"
        "    generated Python its own gates actually prove, via deterministic\n"
        "    mutation. A read, never a verdict.\n"
    ),
    "rebuild": (
        "SYNOPSIS\n    ret rebuild [claim] [--producer PRODUCER] [-o PATH]\n\n"
        "DESCRIPTION\n"
        "    Rebuild an implementation from a claim: regrow every generated\n"
        "    output with an external producer until the gates pass. The\n"
        "    claim's own generated sources are withheld from the producer's\n"
        "    room -- it sees only the pinned criteria.\n\n"
        "    --producer openai, --producer anthropic, and --producer codex\n"
        "    each answer to their own name (and preflight their credential\n"
        "    before anything is spent); any other value is any program, run\n"
        "    as a literal shell command.\n"
    ),
    "crosscheck": (
        "SYNOPSIS\n    ret crosscheck [claim] [m2] [m3] [--mutants N]\n\n"
        "DESCRIPTION\n"
        "    Compare independent realizations: the three-machine test. A\n"
        "    leg is a claim directory or a signed record file. Given only\n"
        "    one additional leg (m3), m2 is materialized here as a real,\n"
        "    disclosed byte copy of m1 -- never a silently weakened\n"
        "    two-legged test.\n"
    ),
    "record": (
        "SYNOPSIS\n    ret record [claim] [-o PATH] [--key KEY] [--as NAME] "
        "[--sign] [--check]\n\n"
        "DESCRIPTION\n"
        "    Write an execution record (spec/record.md) at -o/--output,\n"
        "    optionally signed. With no -o, --key together with --as is the\n"
        "    lighter attestation ceremony instead, and --check verifies an\n"
        "    existing attestation.\n"
    ),
    "sign": (
        "SYNOPSIS\n    ret sign [claim] [--key KEY] [--as NAME] [--check]\n\n"
        "DESCRIPTION\n"
        "    Authorize a claim or proof: with no key, emit the review\n"
        "    packet a signer would stand behind; --key together with --as\n"
        "    signs the folded chain root over it; --check verifies an\n"
        "    existing authorization.\n"
    ),
}

_DISPATCH = {
    "init": dispatch.cmd_init,
    "run": dispatch.cmd_run,
    "status": dispatch.cmd_status,
    "pack": dispatch.cmd_pack,
    "pull": dispatch.cmd_pull,
    "export": dispatch.cmd_export,
    "import": dispatch.cmd_import,
    "verify": dispatch.cmd_verify,
    "audit": dispatch.cmd_audit,
    "assess": dispatch.cmd_assess,
    "rebuild": dispatch.cmd_rebuild,
    "crosscheck": dispatch.cmd_crosscheck,
    "record": dispatch.cmd_record,
    "sign": dispatch.cmd_sign,
}


# ===========================================================================
# -h vs --help: concise usage, and the fuller SYNOPSIS/DESCRIPTION account.
# ===========================================================================


class _ShortHelp(argparse.Action):
    def __init__(self, option_strings, dest, **kwargs):
        kwargs.setdefault("nargs", 0)
        kwargs.setdefault("default", argparse.SUPPRESS)
        super().__init__(option_strings, dest, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        parser.print_usage()
        parser.exit()


class _FullHelp(argparse.Action):
    def __init__(self, option_strings, dest, verb=None, **kwargs):
        kwargs.setdefault("nargs", 0)
        kwargs.setdefault("default", argparse.SUPPRESS)
        super().__init__(option_strings, dest, **kwargs)
        self.verb = verb

    def __call__(self, parser, namespace, values, option_string=None):
        print(_FULL_HELP.get(self.verb) or parser.format_help())
        parser.exit()


def _add_verbose_json(p):
    p.add_argument("-v", "--verbose", action="store_true", help="show extra detail")
    p.add_argument("--json", action="store_true", help="emit a machine-readable JSON envelope")
    return p


def _porcelain(sub, name):
    sp = sub.add_parser(name, help=argparse.SUPPRESS, add_help=False)
    sp.add_argument("-h", action=_ShortHelp, help="show concise usage")
    sp.add_argument("--help", action=_FullHelp, verb=name, help="show the full account")
    _add_verbose_json(sp)
    return sp


def _build_parser():
    p = argparse.ArgumentParser(
        prog="ret", description=_DESC, epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--version", action="store_true", help="show the version and exit")
    p.add_argument("--color", choices=("auto", "always", "never"), default="auto",
                    help="colorize terminal output")

    sub = p.add_subparsers(dest="verb", metavar="<command>", help=argparse.SUPPRESS)

    sp = _porcelain(sub, "init")
    sp.add_argument("workspace", nargs="?", default=".")
    sp.add_argument("--agent", metavar="NAME")
    sp.add_argument("--no-agent", action="store_true")

    sp = _porcelain(sub, "run")
    sp.add_argument("cmd")
    sp.add_argument("-C", "--workspace", dest="workspace", default=".", metavar="WORKSPACE")

    sp = _porcelain(sub, "status")
    sp.add_argument("workspace", nargs="?", default=".")
    sp.add_argument("--all", action="store_true")
    sp.add_argument("--files", action="store_true")
    sp.add_argument("--tree", action="store_true")
    sp.add_argument("--claims", action="store_true")

    sp = _porcelain(sub, "pack")
    sp.add_argument("workspace", nargs="?", default=".")
    sp.add_argument("--accept", nargs="+", metavar="OUTPUT")
    sp.add_argument("-o", "--output", metavar="PATH")
    sp.add_argument("--name", metavar="NAME")
    sp.add_argument("--pytest", action="store_true",
                     help="the declared recipe's gate is `pytest`")
    sp.add_argument("--environment", metavar="PATH",
                     help="a hash-pinned requirements file, a pinned input")

    sp = _porcelain(sub, "pull")
    sp.add_argument("source")
    sp.add_argument("workspace", nargs="?", default=".")

    sp = _porcelain(sub, "export")
    sp.add_argument("claim", nargs="?", default=".")
    sp.add_argument("tar", nargs="?", default=None)
    sp.add_argument("-o", "--out", metavar="PATH")
    sp.add_argument("--blind", action="store_true")

    sp = _porcelain(sub, "import")
    sp.add_argument("archive")
    sp.add_argument("workspace", nargs="?", default=".")

    sp = _porcelain(sub, "verify")
    sp.add_argument("claim", nargs="?", default=".")

    sp = _porcelain(sub, "audit")
    sp.add_argument("claim", nargs="?", default=".")
    sp.add_argument("--shallow", action="store_true")
    sp.add_argument("--no-strict", action="store_true")
    sp.add_argument("--mutants", type=int, default=None)
    sp.add_argument("--record", metavar="PATH")

    sp = _porcelain(sub, "assess")
    sp.add_argument("claim", nargs="?", default=".")
    sp.add_argument("--mutants", type=int, default=None)

    sp = _porcelain(sub, "rebuild")
    sp.add_argument("claim", nargs="?", default=".")
    sp.add_argument("--producer", metavar="PRODUCER")
    sp.add_argument("-o", "--out", metavar="PATH")

    sp = _porcelain(sub, "crosscheck")
    sp.add_argument("claim", nargs="?", default=".")
    sp.add_argument("legs", nargs="*", metavar="m2-or-m3")
    sp.add_argument("--mutants", type=int, default=None)

    sp = _porcelain(sub, "record")
    sp.add_argument("claim", nargs="?", default=".")
    sp.add_argument("--key", metavar="KEY")
    sp.add_argument("--as", dest="as_", metavar="NAME")
    sp.add_argument("--check", action="store_true")
    sp.add_argument("-o", "--output", metavar="PATH")
    sp.add_argument("--sign", action="store_true")

    sp = _porcelain(sub, "sign")
    sp.add_argument("claim", nargs="?", default=".")
    sp.add_argument("--key", metavar="KEY")
    sp.add_argument("--as", dest="as_", metavar="NAME")
    sp.add_argument("--check", action="store_true")

    sp = sub.add_parser("hook", help=argparse.SUPPRESS, add_help=True)
    sp.add_argument("-C", "--workspace", dest="workspace", default=".", metavar="WORKSPACE")
    _add_verbose_json(sp)

    sp = sub.add_parser("help", help=argparse.SUPPRESS, add_help=True)
    sp.add_argument("topic", nargs="?", default=None)
    sp.add_argument("-a", "--all", action="store_true")

    sp = sub.add_parser("completion", help=argparse.SUPPRESS, add_help=True)
    sp.add_argument("shell", nargs="?", default="bash", choices=("bash",))

    return p, sub.choices


def verbs():
    """Every name `main` dispatches: the fourteen porcelain verbs plus the
    three plumbing entries. No aliases remain -- this IS the grammar.
    """
    return sorted(PORCELAIN + PLUMBING)


# ===========================================================================
# help -a / completion: generated from the grammar, never hand-duplicated.
# ===========================================================================


def _help_topic(name):
    if name == "environment":
        print(_ENV_HELP)
        return
    text = _FULL_HELP.get(name)
    if text is not None:
        print(text)
        return
    _, choices = _build_parser()
    sp = choices.get(name)
    if sp is None:
        print(f"ret: help: no such command: {name}", file=sys.stderr)
        return
    print(sp.format_help())


def _help_all():
    print(_DESC)
    print()
    print("Plumbing")
    print("    hook        the coding-agent hook entry point")
    print()
    print("Accepted older spellings")
    print("    (none -- the fourteen porcelain verbs are the grammar)")


def _completion(shell):
    names = " ".join(verbs())
    if shell != "bash":
        print(f"# completion for {shell!r} is not supported", file=sys.stderr)
        return
    print(
        "_ret_complete() {\n"
        '    local cur="${COMP_WORDS[COMP_CWORD]}"\n'
        f'    COMPREPLY=( $(compgen -W "{names}" -- "$cur") )\n'
        "}\n"
        "complete -F _ret_complete ret"
    )


def _version_line():
    return f"ret {_VERSION}"


# ===========================================================================
# main
# ===========================================================================


def _first_token(argv):
    for tok in argv:
        if not tok.startswith("-"):
            return tok
    return None


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)

    _, choices = _build_parser()
    verb_tok = _first_token(argv)
    if verb_tok is not None and verb_tok not in choices:
        hint = difflib.get_close_matches(verb_tok, choices.keys(), n=1)
        msg = f"{verb_tok} is not a ret command"
        if hint:
            msg += f". Did you mean {hint[0]}?"
        print(f"ret: {msg}", file=sys.stderr)
        return 2

    parser, _choices = _build_parser()
    args = parser.parse_args(argv)

    if getattr(args, "version", False):
        print(_version_line())
        return 0

    verb = args.verb
    if verb is None:
        parser.print_help()
        return 1

    if verb == "help":
        if args.all:
            _help_all()
            return 0
        if args.topic:
            _help_topic(args.topic)
            return 0
        parser.print_help()
        return 0

    if verb == "completion":
        _completion(args.shell)
        return 0

    if verb == "hook":
        return dispatch.cmd_hook(args)

    if verb == "run":
        return dispatch.cmd_run(args)

    handler = _DISPATCH.get(verb)
    if handler is None:
        parser.error(f"unknown command: {verb}")
        return 2

    try:
        return handler(args)
    except KeyboardInterrupt:
        raise
    except Exception as exc:  # last-resort guard: a refusal, never a traceback
        import reticuli.kernel as kernel
        if isinstance(exc, kernel.ClaimError):
            from ._cli import dispatch as _d
            return _d._refuse(args, verb, str(exc), 1)
        print(f"ret: {verb}: {exc}", file=sys.stderr)
        return 1
