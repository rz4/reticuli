"""Argument grammar for the Reticuli command line."""

from __future__ import annotations

import argparse


_DESC = (
    "Reticuli records and reproduces software claims.\n\n"
    "Authoring\n"
    "    init        initialize a workspace\n"
    "    run         run and observe a command\n"
    "    status      show work, claims, and unresolved inputs\n"
    "    pack        create a claim from a project\n\n"
    "Composition and transport\n"
    "    pull        add another claim as a dependency\n"
    "    export      write a portable claim archive\n"
    "    import      restore a claim archive\n\n"
    "Verification\n"
    "    verify      verify claim identity\n"
    "    audit       rerun acceptance criteria\n"
    "    assess      measure specification strength\n\n"
    "Reconstruction\n"
    "    rebuild     rebuild an implementation from a claim\n"
    "    crosscheck  compare independent realizations\n\n"
    "Evidence\n"
    "    record      write an execution record\n"
    "    sign        authorize a claim or proof"
)
_EPILOG = (
    "See 'ret <command> -h' for command usage.\n"
    "See 'ret help <command>' for detailed help; 'ret help -a' lists everything,\n"
    "including accepted older spellings."
)

PORCELAIN = (
    "init", "run", "status", "pack", "pull", "export", "import",
    "verify", "audit", "assess", "rebuild", "crosscheck", "record", "sign",
)
# Short spellings are entered into the same subparser as their long forms.
ALIASES = {"ls": "status", "check": "verify"}
_FULL_HELP = {}


def _add_verbose_json(command):
    """Add the common output controls to a command parser."""
    command.add_argument("-v", "--verbose", action="store_true", help="show details")
    command.add_argument("--json", action="store_true", help="write JSON output")
    return command


def _parser():
    """Return the root parser and its subparser registry."""
    root = argparse.ArgumentParser(
        prog="ret", description=_DESC, epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    root.add_argument("--version", action="version", version="reticuli")
    commands = root.add_subparsers(dest="command", metavar="command")

    def add(name, summary, *, aliases=()):
        item = commands.add_parser(name, aliases=list(aliases), help=summary,
                                   description=summary, allow_abbrev=False)
        _add_verbose_json(item)
        return item

    item = add("init", "initialize a workspace")
    item.add_argument("workspace", nargs="?", default=".")
    item.add_argument("--no-agent", action="store_true")
    item.add_argument("--producer")

    item = add("run", "run and observe a command")
    item.add_argument("argv", nargs=argparse.REMAINDER)
    item.add_argument("--workspace", default=".")
    item.add_argument("--producer")

    item = add("status", "show work, claims, and unresolved inputs", aliases=("ls",))
    item.add_argument("path", nargs="?", default=".")
    item.add_argument("--tree", action="store_true")
    item.add_argument("--claims", action="store_true")
    item.add_argument("--deps", action="store_true")

    item = add("pack", "create a claim from a project")
    item.add_argument("path", nargs="?", default=".")
    item.add_argument("--name")
    item.add_argument("--generated", action="append", default=[])
    item.add_argument("--input", action="append", default=[])
    item.add_argument("--gate")
    item.add_argument("--gate-output")
    item.add_argument("--accept", action="store_true")

    item = add("pull", "add another claim as a dependency")
    item.add_argument("claim")
    item.add_argument("--into", default=".")

    item = add("export", "write a portable claim archive")
    item.add_argument("claim")
    item.add_argument("archive")
    item.add_argument("--blind", action="store_true")

    item = add("import", "restore a claim archive")
    item.add_argument("archive")
    item.add_argument("into")

    item = add("verify", "verify claim identity", aliases=("check",))
    item.add_argument("claim", nargs="?", default=".")

    item = add("audit", "rerun acceptance criteria")
    item.add_argument("claim", nargs="?", default=".")
    item.add_argument("--shallow", action="store_true")

    item = add("assess", "measure specification strength")
    item.add_argument("claim", nargs="?", default=".")
    item.add_argument("--mutants", type=int, default=100)

    item = add("rebuild", "rebuild an implementation from a claim")
    item.add_argument("claim")
    item.add_argument("into")
    item.add_argument("--producer")
    item.add_argument("--without-guidance", action="store_true")

    item = add("crosscheck", "compare independent realizations")
    item.add_argument("m1")
    item.add_argument("m2")
    item.add_argument("m3")
    item.add_argument("--mutants", type=int)
    item.add_argument("--record-proof", action="store_true")

    item = add("record", "write an execution record")
    item.add_argument("claim", nargs="?", default=".")
    item.add_argument("--output")
    item.add_argument("--key")
    item.add_argument("--as", dest="identity")
    item.add_argument("--check", action="store_true")

    item = add("sign", "authorize a claim or proof")
    item.add_argument("claim", nargs="?", default=".")
    item.add_argument("--key")
    item.add_argument("--as", dest="identity")
    item.add_argument("--check", action="store_true")

    help_parser = commands.add_parser("help", help="show command help")
    help_parser.add_argument("topic", nargs="?")
    help_parser.add_argument("-a", "--all", action="store_true")
    completion = commands.add_parser("completion", help="print shell completion")
    completion.add_argument("shell", choices=("bash", "zsh", "fish"), nargs="?", default="bash")
    hook = commands.add_parser("hook", help="process an agent hook event")
    hook.add_argument("event", nargs="?")
    return root, commands


def verbs():
    """Return every command spelling accepted by the grammar."""
    _, commands = _parser()
    return tuple(commands.choices)


def _help_topic(topic):
    """Print help for one command spelling."""
    root, commands = _parser()
    command = commands.choices.get(topic)
    if command is None:
        root.error(f"unknown help topic: {topic}")
    command.print_help()


def _help_all():
    """Print root help followed by detailed help for each command."""
    root, commands = _parser()
    root.print_help()
    seen = set()
    for name, command in commands.choices.items():
        if id(command) in seen:
            continue
        seen.add(id(command))
        print(f"\n{name}\n")
        command.print_help()


def _completion(shell="bash"):
    """Print a completion script derived from the registered commands."""
    root, commands = _parser()
    words = " ".join(commands.choices)
    if shell == "bash":
        print("_ret_complete() {")
        print(f'    COMPREPLY=( $(compgen -W "{words}" -- "${{COMP_WORDS[COMP_CWORD]}}") )')
        print("}")
        print("complete -F _ret_complete ret")
    elif shell == "zsh":
        print(f"#compdef ret\n_arguments '1:command:({words})'")
    elif shell == "fish":
        for name in commands.choices:
            print(f"complete -c ret -f -a {name}")
    else:
        root.error(f"unsupported shell: {shell}")

