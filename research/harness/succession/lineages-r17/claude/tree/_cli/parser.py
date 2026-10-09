"""The argv grammar (`spec/layers.md`): verbs, aliases, help, completion.

Fourteen porcelain verbs are grouped under `_DESC` for `ret -h`; a small set
of folded aliases reach the same subparsers under older or shorter spellings;
`hook`, `help`, and `completion` are plumbing -- present in `verbs()` but not
advertised as porcelain. `verbs()` is derived from the actual argparse
subparsers action, not a parallel list, so it cannot drift from what the
parser accepts.
"""
import argparse
import sys

PORCELAIN = (
    "init", "run", "status", "pack",
    "pull", "export", "import",
    "verify", "audit", "assess",
    "rebuild", "crosscheck",
    "record", "sign",
)

ALIASES = {
    "st": "status",
    "ver": "verify",
}

_SHORT_HELP = {
    "init": "initialize a workspace",
    "run": "run and observe a command",
    "status": "show work, claims, and unresolved inputs",
    "pack": "create a claim from a project",
    "pull": "add another claim as a dependency",
    "export": "write a portable claim archive",
    "import": "restore a claim archive",
    "verify": "verify claim identity",
    "audit": "rerun acceptance criteria",
    "assess": "measure specification strength",
    "rebuild": "rebuild an implementation from a claim",
    "crosscheck": "compare independent realizations",
    "record": "write an execution record",
    "sign": "authorize a claim or proof",
}

_FULL_HELP = {
    verb: f"ret {verb} -- {text}." for verb, text in _SHORT_HELP.items()
}

_DESC = 'Reticuli records and reproduces software claims.\n\nAuthoring\n    init        initialize a workspace\n    run         run and observe a command\n    status      show work, claims, and unresolved inputs\n    pack        create a claim from a project\n\nComposition and transport\n    pull        add another claim as a dependency\n    export      write a portable claim archive\n    import      restore a claim archive\n\nVerification\n    verify      verify claim identity\n    audit       rerun acceptance criteria\n    assess      measure specification strength\n\nReconstruction\n    rebuild     rebuild an implementation from a claim\n    crosscheck  compare independent realizations\n\nEvidence\n    record      write an execution record\n    sign        authorize a claim or proof'

_EPILOG = "See 'ret <command> -h' for command usage.\nSee 'ret help <command>' for detailed help; 'ret help -a' lists everything,\nincluding accepted older spellings."


def _add_verbose_json(sub) -> None:
    """Add the two flags every porcelain verb accepts."""
    sub.add_argument("-v", "--verbose", action="store_true", help="verbose output")
    sub.add_argument("--json", action="store_true", help="emit a machine-readable envelope")


def _parser():
    """Build the top-level parser. Returns `(parser, subparsers_action)`."""
    p = argparse.ArgumentParser(
        prog="ret",
        description=_DESC,
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="verb", metavar="command")

    for verb in PORCELAIN:
        aliases = sorted(a for a, canon in ALIASES.items() if canon == verb)
        sp = sub.add_parser(verb, aliases=aliases, help=_SHORT_HELP[verb])
        _add_verbose_json(sp)

    sub.add_parser("hook", help=argparse.SUPPRESS)
    sub.add_parser("help", help="show this message, or detailed help for one command")
    sub.add_parser("completion", help="print a shell completion script")

    return p, sub


def verbs():
    """Every name the parser actually accepts as a subcommand."""
    _, sub = _parser()
    return set(sub.choices.keys())


def _help_topic(topic: str) -> None:
    """`ret help <command>` -- detailed help for one verb or alias."""
    canon = ALIASES.get(topic, topic)
    if canon in _FULL_HELP:
        print(_FULL_HELP[canon])
    else:
        print(f"no help for {topic!r}", file=sys.stderr)


def _help_all() -> None:
    """`ret help -a` -- everything, including accepted older spellings."""
    print(_DESC)
    print()
    print("Plumbing")
    print("    hook        the coding-agent hook handshake")
    print("    completion  print a shell completion script")
    print("    help        show this message, or detailed help for one command")
    if ALIASES:
        print()
        print("Accepted older spellings")
        for alias, canon in sorted(ALIASES.items()):
            print(f"    {alias:<10}  {canon}")


def _completion(shell: str) -> None:
    """Print a completion script generated from the grammar."""
    names = " ".join(sorted(verbs()))
    if shell == "bash":
        print(f'''_ret_complete() {{
    local cur
    cur="${{COMP_WORDS[COMP_CWORD]}}"
    COMPREPLY=( $(compgen -W "{names}" -- "$cur") )
}}
complete -F _ret_complete ret''')
    elif shell == "zsh":
        print(f'''#compdef ret
_ret_complete() {{
    local -a commands
    commands=({names})
    _describe 'command' commands
}}
compdef _ret_complete ret''')
    else:
        raise ValueError(f"unsupported shell: {shell!r}")
