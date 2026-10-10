"""Argument grammar and help for the ``ret`` command.

Keep command registration in one place: help, topic lookup, and shell
completion all read the same argparse subparsers.
"""

from __future__ import annotations

import argparse
import sys


_DESC = "Reticuli records and reproduces software claims.\n\nAuthoring\n    init        initialize a workspace\n    run         run and observe a command\n    status      show work, claims, and unresolved inputs\n    pack        create a claim from a project\n\nComposition and transport\n    pull        add another claim as a dependency\n    export      write a portable claim archive\n    import      restore a claim archive\n\nVerification\n    verify      verify claim identity\n    audit       rerun acceptance criteria\n    assess      measure specification strength\n\nReconstruction\n    rebuild     rebuild an implementation from a claim\n    crosscheck  compare independent realizations\n\nEvidence\n    record      write an execution record\n    sign        authorize a claim or proof"
_EPILOG = "See 'ret <command> -h' for command usage.\nSee 'ret help <command>' for detailed help; 'ret help -a' lists everything,\nincluding accepted older spellings."

PORCELAIN = (
    "init", "run", "status", "pack", "pull", "export", "import",
    "verify", "audit", "assess", "rebuild", "crosscheck", "record", "sign",
)

# Short, still accepted spellings. Retired v1 command names are deliberately
# absent: the corresponding operations are options on the current commands.
ALIASES: dict[str, str] = {"ls": "status", "check": "verify"}

_SUMMARIES = {
    "init": "initialize a workspace", "run": "run and observe a command",
    "status": "show work, claims, and unresolved inputs",
    "pack": "create a claim from a project",
    "pull": "add another claim as a dependency",
    "export": "write a portable claim archive",
    "import": "restore a claim archive", "verify": "verify claim identity",
    "audit": "rerun acceptance criteria",
    "assess": "measure specification strength",
    "rebuild": "rebuild an implementation from a claim",
    "crosscheck": "compare independent realizations",
    "record": "write an execution record",
    "sign": "authorize a claim or proof",
    "hook": "receive a coding agent hook",
    "help": "show detailed command help",
    "completion": "print shell completion",
}

_FULL_HELP = {
    "init": "Create the workspace store and install agent hooks unless disabled.",
    "run": "Run a command in the workspace and record its exit status.",
    "status": "Show workspace state. --tree shows structure; --claims lists stored claims.",
    "pack": "Turn a project, its generated files, inputs, and gate into a claim.",
    "pull": "Add a sealed claim and its dependencies to the workspace.",
    "export": "Write a portable archive of a sealed claim.",
    "import": "Restore and verify a portable claim archive.",
    "verify": "Compare the present pinned bytes with the sealed claim root.",
    "audit": "Rerun gates to earn a fresh verdict; --shallow skips dependencies.",
    "assess": "Measure how strongly the gates test generated Python code.",
    "rebuild": "Regrow generated files from pinned inputs and rerun gates.",
    "crosscheck": "Compare three independently obtained claim legs.",
    "record": "Write or check a signed execution record.",
    "sign": "Authorize a verified, proven claim with a signing key.",
    "hook": "Read one agent hook payload from standard input.",
    "help": "Show this command's detailed help, or all command help with -a.",
    "completion": "Generate completion for bash, zsh, or fish.",
}


def _add_verbose_json(command: argparse.ArgumentParser) -> None:
    """Add the common output switches to one command parser."""
    command.add_argument("-v", "--verbose", action="store_true", help="show details")
    command.add_argument("--json", action="store_true", help="write one JSON result")


def _parser() -> tuple[argparse.ArgumentParser, dict[str, argparse.ArgumentParser]]:
    """Build and return the root parser and its complete command lookup."""
    root = argparse.ArgumentParser(
        prog="ret", description=_DESC, epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    root.add_argument("--version", action="version", version="reticuli")
    sub = root.add_subparsers(dest="verb", metavar="command")
    commands: dict[str, argparse.ArgumentParser] = {}

    for name in (*PORCELAIN, "hook", "help", "completion"):
        aliases = [alias for alias, target in ALIASES.items() if target == name]
        command = sub.add_parser(name, aliases=aliases, help=_SUMMARIES[name],
                                 description=_FULL_HELP[name])
        commands[name] = command
        commands.update({alias: command for alias in aliases})
        if name not in ("hook", "help", "completion"):
            _add_verbose_json(command)

    commands["init"].add_argument("workspace", nargs="?", default=".")
    commands["init"].add_argument("--no-agent", action="store_true")

    commands["run"].add_argument("command", nargs=argparse.REMAINDER)

    status = commands["status"]
    status.add_argument("path", nargs="?", default=".")
    modes = status.add_mutually_exclusive_group()
    modes.add_argument("--tree", action="store_true", help="show claim structure")
    modes.add_argument("--claims", action="store_true", help="list stored claims")
    modes.add_argument("--deps", action="store_true", help="show dependency links")
    status.add_argument("--files", action="store_true", help="show declared files")

    pack = commands["pack"]
    pack.add_argument("project", nargs="?", default=".")
    pack.add_argument("--name")
    pack.add_argument("--generated", action="append", default=[], metavar="PATTERN")
    pack.add_argument("--input", "--inputs", action="append", default=[], metavar="PATTERN")
    pack.add_argument("--gate")
    pack.add_argument("--output", dest="gate_output")
    pack.add_argument("--inputs-manifest")
    pack.add_argument("--environment")
    pack.add_argument("--format", type=int, dest="claim_format")
    pack.add_argument("--mutation-floor", type=float)
    pack.add_argument("--by")
    pack.add_argument("--accept", action="store_true", help="accept a reviewed claim")

    commands["pull"].add_argument("claim")
    commands["pull"].add_argument("--workspace", default=".")

    export = commands["export"]
    export.add_argument("claim")
    export.add_argument("archive")
    export.add_argument("--blind", action="store_true")

    imported = commands["import"]
    imported.add_argument("archive")
    imported.add_argument("into")

    commands["verify"].add_argument("claim", nargs="?", default=".")
    audit = commands["audit"]
    audit.add_argument("claim", nargs="?", default=".")
    audit.add_argument("--shallow", action="store_true")
    assess = commands["assess"]
    assess.add_argument("claim", nargs="?", default=".")
    assess.add_argument("--mutants", type=int, default=100)

    rebuild = commands["rebuild"]
    rebuild.add_argument("claim")
    rebuild.add_argument("into")
    rebuild.add_argument("--producer")
    rebuild.add_argument("--without-guidance", action="store_true")
    rebuild.add_argument("--reuse", action="store_true")

    crosscheck = commands["crosscheck"]
    crosscheck.add_argument("m1")
    crosscheck.add_argument("m2")
    crosscheck.add_argument("m3")
    crosscheck.add_argument("--mutants", type=int)
    crosscheck.add_argument("--record-proof", action="store_true")

    record = commands["record"]
    record.add_argument("claim", nargs="?", default=".")
    record.add_argument("--into")
    record.add_argument("--key")
    record.add_argument("--as", dest="identity")
    record.add_argument("--check", action="store_true")
    record.add_argument("--anchor")

    sign = commands["sign"]
    sign.add_argument("claim", nargs="?", default=".")
    sign.add_argument("--key")
    sign.add_argument("--as", dest="identity")
    sign.add_argument("--check", action="store_true")
    sign.add_argument("--anchor")

    help_command = commands["help"]
    help_command.add_argument("topic", nargs="?")
    help_command.add_argument("-a", "--all", action="store_true")
    commands["completion"].add_argument("shell", choices=("bash", "zsh", "fish"))
    return root, commands


def verbs() -> tuple[str, ...]:
    """Return every accepted command spelling from the grammar."""
    _, commands = _parser()
    return tuple(commands)


def _help_topic(topic: str) -> None:
    """Print detailed help for one accepted command spelling."""
    root, commands = _parser()
    if topic not in commands:
        root.error(f"unknown help topic: {topic}")
    commands[topic].print_help()


def _help_all() -> None:
    """Print root help followed by help for each command."""
    root, commands = _parser()
    root.print_help()
    for name in (*PORCELAIN, "hook", "help", "completion"):
        print()
        commands[name].print_help()


def _completion(shell: str) -> None:
    """Print completion built from registered verbs and option actions."""
    _, commands = _parser()
    names = " ".join(commands)
    if shell == "bash":
        print("_ret_complete() {")
        print("    local cur=${COMP_WORDS[COMP_CWORD]}")
        print("    if (( COMP_CWORD == 1 )); then")
        print(f'        COMPREPLY=( $(compgen -W "{names}" -- "$cur") )')
        print("        return")
        print("    fi")
        print("    case ${COMP_WORDS[1]} in")
        for name, command in commands.items():
            flags = " ".join(option for action in command._actions
                             for option in action.option_strings)
            print(f'        {name}) COMPREPLY=( $(compgen -W "{flags}" -- "$cur") ) ;;')
        print("    esac")
        print("}")
        print("complete -F _ret_complete ret")
    elif shell == "zsh":
        print("#compdef ret")
        print(f"_arguments '1:command:({names})' '*::option:->options'")
    elif shell == "fish":
        for name in commands:
            print(f"complete -c ret -f -n '__fish_use_subcommand' -a '{name}'")
    else:
        raise ValueError(f"unsupported shell: {shell}")


if __name__ == "__main__":
    _parser()[0].print_help(sys.stdout)
