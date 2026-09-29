"""Argument grammar and help for the ``ret`` command.

The parser is the single source of truth for command names and shell
completion.  Command execution belongs to the CLI's other modules.
"""

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

# Older surface spellings that still have a direct, unambiguous meaning.
# The retired v1 verbs are intentionally absent.
ALIASES: dict[str, str] = {}

_FULL_HELP = {
    "init": "Initialize a workspace and its agent hooks.",
    "run": "Run and observe a command in an initialized workspace.",
    "status": "Show work, claims, and unresolved inputs.",
    "pack": "Create a claim from a project.",
    "pull": "Add another claim as a dependency.",
    "export": "Write a portable claim archive.",
    "import": "Restore a portable claim archive.",
    "verify": "Verify claim identity.",
    "audit": "Rerun acceptance criteria.",
    "assess": "Measure specification strength.",
    "rebuild": "Rebuild an implementation from a claim.",
    "crosscheck": "Compare independent realizations.",
    "record": "Write an execution record.",
    "sign": "Authorize a claim or proof.",
    "hook": "Receive an agent hook event.",
    "help": "Show command help.",
    "completion": "Print a shell completion script.",
}


def _add_verbose_json(command: argparse.ArgumentParser) -> None:
    """Add the common presentation switches to a command parser."""
    command.add_argument("-v", "--verbose", action="store_true", help="show details")
    command.add_argument("--json", action="store_true", help="write JSON output")


def _parser() -> tuple[argparse.ArgumentParser, argparse._SubParsersAction]:
    """Build the public grammar and return its parser and command action."""
    top = argparse.ArgumentParser(
        prog="ret", description=_DESC, epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    commands = top.add_subparsers(dest="command", metavar="command")
    for name in PORCELAIN:
        command = commands.add_parser(
            name, help=_FULL_HELP[name], description=_FULL_HELP[name],
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        _add_verbose_json(command)
    for alias, target in ALIASES.items():
        command = commands.add_parser(
            alias, help=f"alias for {target}", description=_FULL_HELP[target],
        )
        _add_verbose_json(command)
        command.set_defaults(command=target)
    hook = commands.add_parser("hook", help=argparse.SUPPRESS)
    hook.add_argument("event", nargs="?")
    help_command = commands.add_parser("help", help="show detailed help")
    help_command.add_argument("topic", nargs="?")
    help_command.add_argument("-a", "--all", action="store_true")
    completion = commands.add_parser("completion", help="print shell completion")
    completion.add_argument("shell", choices=("bash", "zsh", "fish"))
    return top, commands


def verbs() -> tuple[str, ...]:
    """Return exactly the command names accepted by the grammar."""
    _, commands = _parser()
    return tuple(commands.choices)


def _help_topic(topic: str) -> None:
    """Print the detailed help for one command."""
    top, commands = _parser()
    if topic in commands.choices:
        commands.choices[topic].print_help()
    else:
        top.error(f"unknown help topic: {topic}")


def _help_all() -> None:
    """Print top level and command help."""
    top, commands = _parser()
    top.print_help()
    for name in commands.choices:
        print()
        commands.choices[name].print_help()


def _completion(shell: str) -> None:
    """Print completion for the current grammar."""
    words = " ".join(verbs())
    if shell == "bash":
        print(f'_ret_complete() {{ COMPREPLY=( $(compgen -W "{words}" -- "${{COMP_WORDS[COMP_CWORD]}}") ); }}')
        print("complete -F _ret_complete ret")
    elif shell == "zsh":
        print(f"#compdef ret\n_arguments '1:command:({words})'")
    elif shell == "fish":
        for name in verbs():
            print(f"complete -c ret -f -n '__fish_use_subcommand' -a {name}")
    else:
        raise ValueError(f"unsupported shell: {shell}")
