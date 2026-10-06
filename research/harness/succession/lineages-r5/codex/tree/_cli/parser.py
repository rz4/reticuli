"""Argument grammar and help for the ``ret`` command.

Keep command names in one place so help, dispatch, and shell completion agree.
This module only parses arguments; command execution belongs to the CLI.
"""

from __future__ import annotations

import argparse
import sys


_DESC = ('Reticuli records and reproduces software claims.\n\nAuthoring\n    init        initialize a workspace\n    run         run and observe a command\n    status      show work, claims, and unresolved inputs\n    pack        create a claim from a project\n\nComposition and transport\n    pull        add another claim as a dependency\n    export      write a portable claim archive\n    import      restore a claim archive\n\nVerification\n    verify      verify claim identity\n    audit       rerun acceptance criteria\n    assess      measure specification strength\n\nReconstruction\n    rebuild     rebuild an implementation from a claim\n    crosscheck  compare independent realizations\n\nEvidence\n    record      write an execution record\n    sign        authorize a claim or proof')
_EPILOG = "See 'ret <command> -h' for command usage.\nSee 'ret help <command>' for detailed help; 'ret help -a' lists everything,\nincluding accepted older spellings."

PORCELAIN = (
    "init", "run", "status", "pack", "pull", "export", "import",
    "verify", "audit", "assess", "rebuild", "crosscheck", "record", "sign",
)

# Older spellings that still have a clear, current meaning. Retired v1 verbs
# are deliberately absent: their meanings are expressed through options on
# the porcelain commands instead.
ALIASES: dict[str, str] = {
    "ls": "status",
    "test": "audit",
    "build": "rebuild",
}

_FULL_HELP: dict[str, str] = {
    "init": "Initialize a workspace and wire its agent hooks.",
    "run": "Run a command in an initialized workspace and record the observation.",
    "status": "Show workspace and claim status; --tree and --claims select views.",
    "pack": "Create a claim from a project; --accept approves its generated files.",
    "pull": "Add another claim as a dependency.",
    "export": "Write a portable claim archive.",
    "import": "Restore a portable claim archive.",
    "verify": "Verify a claim's content identity.",
    "audit": "Run acceptance criteria against the current claim.",
    "assess": "Measure the strength of pinned criteria.",
    "rebuild": "Rebuild generated files; --without-guidance withholds producer hints.",
    "crosscheck": "Compare independent realizations of a claim.",
    "record": "Write or check a signed execution record.",
    "sign": "Authorize a claim or a proof.",
    "hook": "Run a workspace hook.",
    "help": "Show command help.",
    "completion": "Print shell completion from the registered command grammar.",
}


def _add_verbose_json(command: argparse.ArgumentParser) -> None:
    """Add the common machine output and diagnostic options."""
    command.add_argument("-v", "--verbose", action="store_true", help="show more detail")
    command.add_argument("--json", action="store_true", help="write JSON output")


def _parser() -> tuple[argparse.ArgumentParser, dict[str, argparse.ArgumentParser]]:
    """Build the CLI parser and return it with its command parsers."""
    top = argparse.ArgumentParser(
        prog="ret", description=_DESC, epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    top.add_argument("--version", action="version", version="reticuli")
    commands = top.add_subparsers(dest="verb", metavar="command")
    result: dict[str, argparse.ArgumentParser] = {}
    for name in PORCELAIN + ("hook", "help", "completion"):
        command = commands.add_parser(name, help=_FULL_HELP[name],
                                      description=_FULL_HELP[name])
        result[name] = command
        if name not in ("help", "completion"):
            _add_verbose_json(command)
    for alias, target in ALIASES.items():
        command = commands.add_parser(alias, help=f"alias for {target}",
                                      description=_FULL_HELP[target])
        result[alias] = command
        _add_verbose_json(command)

    for name in ("init", "status", "pack", "verify", "audit", "assess",
                 "rebuild", "crosscheck", "record", "sign", "hook"):
        result[name].add_argument("directory", nargs="?", default=".")
    result["init"].add_argument("--no-agent", action="store_true")
    result["run"].add_argument("command", nargs=argparse.REMAINDER)
    result["run"].add_argument("--workspace", default=".")
    result["status"].add_argument("--tree", action="store_true")
    result["status"].add_argument("--claims", action="store_true")
    result["pack"].add_argument("--accept", action="store_true")
    result["pack"].add_argument("--inputs-manifest")
    result["pull"].add_argument("claim")
    result["pull"].add_argument("--into", default=".")
    result["export"].add_argument("directory")
    result["export"].add_argument("archive")
    result["import"].add_argument("archive")
    result["import"].add_argument("directory", nargs="?", default=".")
    result["rebuild"].add_argument("--without-guidance", action="store_true")
    result["record"].add_argument("--key")
    result["record"].add_argument("--as", dest="identity")
    result["record"].add_argument("--check", action="store_true")
    result["sign"].add_argument("--key")
    result["help"].add_argument("topic", nargs="?")
    result["help"].add_argument("-a", "--all", action="store_true")
    result["completion"].add_argument("shell", choices=("bash", "zsh", "fish"))
    # Alias parsers take the same common directory argument as their targets.
    for alias in ALIASES:
        result[alias].add_argument("directory", nargs="?", default=".")
    return top, result


def verbs() -> tuple[str, ...]:
    """Return every accepted command name in grammar order."""
    return PORCELAIN + ("hook", "help", "completion") + tuple(ALIASES)


def _help_topic(topic: str) -> None:
    """Print detailed help for one command."""
    top, commands = _parser()
    if topic not in commands:
        top.error(f"unknown help topic: {topic}")
    commands[topic].print_help()


def _help_all() -> None:
    """Print the complete command help, including aliases."""
    top, commands = _parser()
    top.print_help()
    for name in verbs():
        print()
        commands[name].print_help()


def _completion(shell: str = "bash") -> None:
    """Print command-name completion derived from the grammar."""
    names = " ".join(verbs())
    if shell == "bash":
        print(f'_ret_complete() {{ COMPREPLY=( $(compgen -W "{names}" -- "${{COMP_WORDS[COMP_CWORD]}}") ); }}')
        print("complete -F _ret_complete ret")
    elif shell == "zsh":
        print(f"#compdef ret\n_arguments '1:command:({names})'")
    elif shell == "fish":
        for name in verbs():
            print(f"complete -c ret -f -n '__fish_use_subcommand' -a {name}")
    else:
        raise ValueError(f"unsupported shell: {shell}")

