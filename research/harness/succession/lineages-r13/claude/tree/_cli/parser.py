"""The argv grammar: the fourteen porcelain verbs, the plumbing verbs
(`hook`, `help`, `completion`), and whatever older spellings are still
accepted (`ALIASES`). Nothing here reaches into any other module -- the
grammar stands on its own; every other `_cli` module reads the parsed
`argparse.Namespace` this module hands back, never the grammar itself.

`_parser()` builds the one `argparse.ArgumentParser` the whole CLI shares
and returns it together with its subparsers action's own `choices`
mapping -- that mapping is the grammar's ground truth (every porcelain
verb, every accepted alias, and the plumbing, each already pointing at
its own subparser), so `verbs()` reads it back rather than keeping a
second list that could drift from what `_parser()` actually registered.
`_completion` builds a bash completion script the same way, from
`verbs()`, so the completion list cannot name a verb the parser does not
accept, nor omit one it does.
"""
import argparse
import sys

# The fourteen porcelain verbs, grouped the way `_DESC` and `_help_all`
# present them to a human.
PORCELAIN = (
    "init", "run", "status", "pack",
    "pull", "export", "import",
    "verify", "audit", "assess",
    "rebuild", "crosscheck",
    "record", "sign",
)

# Older verb spellings still accepted, mapped to the porcelain verb each
# is folded into as an `argparse` subparser alias. Nothing from the v1
# grammar survives this way any more (see the gate's own `RETIRED` list);
# the dict stays because `verbs()`, `_parser()`, and `_help_all` all read
# it regardless of whether anything is in it right now.
ALIASES = {}

_DESC = 'Reticuli records and reproduces software claims.\n\nAuthoring\n    init        initialize a workspace\n    run         run and observe a command\n    status      show work, claims, and unresolved inputs\n    pack        create a claim from a project\n\nComposition and transport\n    pull        add another claim as a dependency\n    export      write a portable claim archive\n    import      restore a claim archive\n\nVerification\n    verify      verify claim identity\n    audit       rerun acceptance criteria\n    assess      measure specification strength\n\nReconstruction\n    rebuild     rebuild an implementation from a claim\n    crosscheck  compare independent realizations\n\nEvidence\n    record      write an execution record\n    sign        authorize a claim or proof'

_EPILOG = "See 'ret <command> -h' for command usage.\nSee 'ret help <command>' for detailed help; 'ret help -a' lists everything,\nincluding accepted older spellings."

# One line of detail per verb, shown by `ret help <verb>` beyond the one
# line `-h` already gives; keyed by porcelain verb, never by an alias (an
# alias resolves to its target before this dict is consulted).
_FULL_HELP = {
    "init": "init [path] [--no-agent]\n\n"
            "Mark a directory as a workspace: make its `.reticuli` store\n"
            "if it is not there yet, and -- unless --no-agent -- wire the\n"
            "coding-agent handshake so a traced session can begin.",
    "run": "run <cmd> [ws]\n\n"
           "Run `cmd` as a shell command with `ws` (default: the current\n"
           "directory) as its working directory, tracing it into the\n"
           "workspace's draft trace first if `ws` is marked.",
    "status": "status [path] [--tree] [--claims]\n\n"
               "Show a claim's work, its phase, and its unresolved inputs.\n"
               "--tree shows the dependency tree; --claims lists every\n"
               "sealed claim in the workspace's registry.",
    "pack": "pack [path] [--accept]\n\n"
            "Create a claim from a project directory. --accept seals it\n"
            "once packed, the same ground a freshly sealed claim stands\n"
            "on.",
    "pull": "pull <component> [path]\n\n"
            "Add another claim as a dependency, materialized under the\n"
            "workspace at `path` (default: the current directory).",
    "export": "export [path] [--out FILE]\n\n"
               "Write a portable claim archive.",
    "import": "import <archive> [path]\n\n"
               "Restore a claim archive into `path` (default: the current\n"
               "directory).",
    "verify": "verify [path]\n\n"
               "Verify a claim's identity: the sealed root against what\n"
               "the bytes present recompute to.",
    "audit": "audit [path]\n\n"
              "Rerun a claim's acceptance criteria.",
    "assess": "assess [path]\n\n"
               "Measure how strongly a claim's acceptance criteria pin\n"
               "down its own implementation.",
    "rebuild": "rebuild [path] [--producer NAME] [--into DIR]\n\n"
                "Rebuild an implementation from a claim, blind to the one\n"
                "already on disk.",
    "crosscheck": "crosscheck <path> [path...]\n\n"
                   "Compare independent realizations of the same claim.",
    "record": "record [path] [--key KEY] [--as NAME] [--check]\n\n"
               "Write an execution record. --check reviews a record\n"
               "already written instead of writing a new one.",
    "sign": "sign [path] [--key KEY]\n\n"
             "Authorize a claim or proof.",
}


def _add_verbose_json(parser) -> None:
    """The two flags every porcelain verb's own subparser carries: `-v`
    for the detail block a verb's result expands into, `--json` for the
    envelope instead of the one-line human summary."""
    parser.add_argument("-v", "--verbose", action="store_true",
                         help="show the detail block for this verb's result")
    parser.add_argument("--json", action="store_true",
                         help="print the result as a single JSON envelope")


def _add_porcelain_args(verb: str, sp) -> None:
    """The verb-specific positionals and flags beyond `-v`/`--json`."""
    if verb == "init":
        sp.add_argument("path", nargs="?", default=".")
        sp.add_argument("--no-agent", action="store_true")
    elif verb == "run":
        sp.add_argument("cmd")
        sp.add_argument("ws", nargs="?", default=".")
    elif verb == "status":
        sp.add_argument("path", nargs="?", default=".")
        sp.add_argument("--tree", action="store_true")
        sp.add_argument("--claims", action="store_true")
    elif verb == "pack":
        sp.add_argument("path", nargs="?", default=".")
        sp.add_argument("--accept", action="store_true")
    elif verb == "pull":
        sp.add_argument("component")
        sp.add_argument("path", nargs="?", default=".")
    elif verb == "export":
        sp.add_argument("path", nargs="?", default=".")
        sp.add_argument("--out")
    elif verb == "import":
        sp.add_argument("archive")
        sp.add_argument("path", nargs="?", default=".")
    elif verb in ("verify", "audit", "assess"):
        sp.add_argument("path", nargs="?", default=".")
    elif verb == "rebuild":
        sp.add_argument("path", nargs="?", default=".")
        sp.add_argument("--producer")
        sp.add_argument("--into")
    elif verb == "crosscheck":
        sp.add_argument("paths", nargs="+")
    elif verb == "record":
        sp.add_argument("path", nargs="?", default=".")
        sp.add_argument("--key")
        sp.add_argument("--as", dest="as_name")
        sp.add_argument("--check", action="store_true")
    elif verb == "sign":
        sp.add_argument("path", nargs="?", default=".")
        sp.add_argument("--key")


def _parser():
    """The one `argparse.ArgumentParser` the whole CLI shares, and its
    subparsers action's own `choices` mapping -- every porcelain verb,
    every accepted alias, and the plumbing, each already pointing at its
    own subparser. That mapping, not a second hand-kept list, is what
    `verbs()` and `_completion` read back."""
    p = argparse.ArgumentParser(
        prog="ret",
        description=_DESC,
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="verb")

    for verb in PORCELAIN:
        aliases = sorted(a for a, target in ALIASES.items() if target == verb)
        sp = sub.add_parser(verb, aliases=aliases)
        _add_verbose_json(sp)
        _add_porcelain_args(verb, sp)

    hook_p = sub.add_parser("hook")
    hook_p.add_argument("event", nargs="?")

    help_p = sub.add_parser("help")
    help_p.add_argument("topic", nargs="?")
    help_p.add_argument("-a", "--all", action="store_true")

    completion_p = sub.add_parser("completion")
    completion_p.add_argument("shell", nargs="?", default="bash")

    return p, sub.choices


def verbs():
    """Every verb spelling the parser actually accepts: the fourteen
    porcelain verbs, each accepted alias, and the plumbing (`hook`,
    `help`, `completion`) -- read straight off `_parser()`'s own
    subparsers, so this can never drift from what `-h` shows."""
    _, choices = _parser()
    return set(choices)


def _help_all() -> None:
    """`ret help -a`: the full grammar, including accepted older
    spellings -- `_DESC`'s groups, then any alias, then the plumbing."""
    print(_DESC)
    print()
    if ALIASES:
        print("Accepted older spellings:")
        for alias in sorted(ALIASES):
            print(f"    {alias:<12}{ALIASES[alias]}")
        print()
    print("Plumbing")
    print("    hook        forward a coding-agent event")
    print("    help        show this help, or detail for one command")
    print("    completion  print a shell completion script")
    print()
    print(_EPILOG)


def _help_topic(name: str) -> None:
    """`ret help <command>`: the detailed help for one verb, resolving an
    alias to the porcelain verb it is folded into first; an unknown name
    refuses rather than guessing."""
    _, choices = _parser()
    canonical = ALIASES.get(name, name)
    if canonical not in choices:
        print(f"ret: help: no such command: {name!r}", file=sys.stderr)
        return
    text = _FULL_HELP.get(canonical)
    if text is not None:
        print(text)
    else:
        print(choices[canonical].format_help())


def _completion(shell: str) -> None:
    """A shell completion script generated from `verbs()` -- the grammar
    the parser itself accepts -- so it cannot name a verb `_parser()` does
    not register, nor omit one it does. Only `bash` is implemented."""
    if shell != "bash":
        print(f"# completion not available for {shell!r}; only bash is supported",
              file=sys.stderr)
        return
    words = " ".join(sorted(verbs()))
    print(
        "_ret_completion() {\n"
        "    local cur\n"
        '    cur="${COMP_WORDS[COMP_CWORD]}"\n'
        f'    COMPREPLY=( $(compgen -W "{words}" -- "$cur") )\n'
        "}\n"
        "complete -F _ret_completion ret"
    )
