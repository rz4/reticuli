"""Argument grammar and generated help for the ``ret`` command."""

from __future__ import annotations

import argparse


_DESC = "Reticuli records and reproduces software claims.\n\nAuthoring\n    init        initialize a workspace\n    run         run and observe a command\n    status      show work, claims, and unresolved inputs\n    pack        create a claim from a project\n\nComposition and transport\n    pull        add another claim as a dependency\n    export      write a portable claim archive\n    import      restore a claim archive\n\nVerification\n    verify      verify claim identity\n    audit       rerun acceptance criteria\n    assess      measure specification strength\n\nReconstruction\n    rebuild     rebuild an implementation from a claim\n    crosscheck  compare independent realizations\n\nEvidence\n    record      write an execution record\n    sign        authorize a claim or proof"
_EPILOG = "See 'ret <command> -h' for command usage.\nSee 'ret help <command>' for detailed help; 'ret help -a' lists everything,\nincluding accepted older spellings."

PORCELAIN = (
    "init", "run", "status", "pack", "pull", "export", "import",
    "verify", "audit", "assess", "rebuild", "crosscheck", "record", "sign",
)

# The command names in this table are accepted spellings of current actions.
# Retired v1 commands intentionally have no entries.
ALIASES: dict[str, str] = {
    "ls": "status",
    "check": "verify",
}

_FULL_HELP: dict[str, str] = {
    "init": "Initialize a workspace and wire its agent hooks.",
    "run": "Run a command in the workspace and observe it.",
    "status": "Show the workspace, claims, dependencies, or file tree.",
    "pack": "Create a claim from a project and its acceptance gate.",
    "pull": "Add a claim as a dependency of this workspace.",
    "export": "Write a portable claim archive.",
    "import": "Restore a portable claim archive.",
    "verify": "Compare present pinned bytes with the sealed claim identity.",
    "audit": "Rerun a claim's acceptance criteria.",
    "assess": "Measure the strength of a claim's criteria.",
    "rebuild": "Regrow generated outputs from the claim's pinned inputs.",
    "crosscheck": "Compare original, transported, and independently rebuilt claims.",
    "record": "Write or check a portable execution record.",
    "sign": "Authorize a claim or proof with an SSH key.",
    "hook": "Handle an agent hook event.",
    "help": "Show command help.",
    "completion": "Print shell completion derived from this command grammar.",
}


def _add_verbose_json(command: argparse.ArgumentParser) -> None:
    """Add the shared presentation flags to an action parser."""
    command.add_argument("-v", "--verbose", action="store_true", help="show more detail")
    command.add_argument("--json", action="store_true", help="emit JSON")


def _parser() -> tuple[argparse.ArgumentParser, argparse._SubParsersAction]:
    """Construct the complete command grammar and return its subparsers."""
    top = argparse.ArgumentParser(
        prog="ret", description=_DESC, epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    top.add_argument("--version", action="store_true", help="show version")
    commands = top.add_subparsers(dest="command", metavar="command")

    def add(name: str) -> argparse.ArgumentParser:
        aliases = [alias for alias, target in ALIASES.items() if target == name]
        command = commands.add_parser(name, aliases=aliases, help=_FULL_HELP[name],
                                      description=_FULL_HELP[name])
        _add_verbose_json(command)
        return command

    p = add("init")
    p.add_argument("directory", nargs="?", default=".")
    p.add_argument("--no-agent", action="store_true")

    p = add("run")
    p.add_argument("command_line", nargs=argparse.REMAINDER)

    p = add("status")
    p.add_argument("directory", nargs="?", default=".")
    for flag in ("tree", "claims", "deps", "files"):
        p.add_argument("--" + flag, action="store_true")

    p = add("pack")
    p.add_argument("directory", nargs="?", default=".")
    p.add_argument("--name")
    p.add_argument("--generated", action="append", default=[])
    p.add_argument("--input", action="append", default=[])
    p.add_argument("--gate")
    p.add_argument("--gate-output")
    p.add_argument("--accept", action="store_true")
    p.add_argument("--inputs-manifest")
    p.add_argument("--environment")

    p = add("pull")
    p.add_argument("source")
    p.add_argument("--into", default=".")

    p = add("export")
    p.add_argument("directory")
    p.add_argument("archive")
    p.add_argument("--blind", action="store_true")

    p = add("import")
    p.add_argument("archive")
    p.add_argument("into")

    p = add("verify")
    p.add_argument("directory", nargs="?", default=".")

    p = add("audit")
    p.add_argument("directory", nargs="?", default=".")
    p.add_argument("--shallow", action="store_true")

    p = add("assess")
    p.add_argument("directory", nargs="?", default=".")
    p.add_argument("--mutants", type=int, default=100)

    p = add("rebuild")
    p.add_argument("directory")
    p.add_argument("into")
    p.add_argument("--producer")
    p.add_argument("--without-guidance", action="store_true")

    p = add("crosscheck")
    p.add_argument("m1")
    p.add_argument("m2")
    p.add_argument("m3")
    p.add_argument("--mutants", type=int)

    p = add("record")
    p.add_argument("directory", nargs="?", default=".")
    p.add_argument("--output")
    p.add_argument("--key")
    p.add_argument("--as", dest="principal")
    p.add_argument("--check", action="store_true")

    p = add("sign")
    p.add_argument("directory", nargs="?", default=".")
    p.add_argument("--key")
    p.add_argument("--as", dest="principal")
    p.add_argument("--check", action="store_true")

    p = commands.add_parser("hook", help=_FULL_HELP["hook"])
    p.add_argument("event", nargs="?")
    p = commands.add_parser("help", help=_FULL_HELP["help"])
    p.add_argument("topic", nargs="?")
    p.add_argument("-a", "--all", action="store_true")
    p = commands.add_parser("completion", help=_FULL_HELP["completion"])
    p.add_argument("shell", choices=("bash", "zsh", "fish"), nargs="?", default="bash")
    return top, commands


def verbs() -> tuple[str, ...]:
    """Names accepted by the current grammar, including aliases."""
    _, commands = _parser()
    return tuple(commands.choices)


def _help_all() -> None:
    """Print the full command guide, including accepted aliases."""
    top, commands = _parser()
    print(top.format_help().rstrip())
    for name in PORCELAIN:
        print("\n" + commands.choices[name].format_help().rstrip())
    if ALIASES:
        print("\nAccepted older spellings:")
        for alias, current in sorted(ALIASES.items()):
            print(f"  {alias} → {current}")


def _help_topic(topic: str | None = None) -> None:
    """Print help for one command, or the overview when no topic is given."""
    top, commands = _parser()
    if topic is None:
        print(top.format_help(), end="")
    elif topic in commands.choices:
        print(commands.choices[topic].format_help(), end="")
    else:
        top.error(f"unknown help topic: {topic}")


def _completion(shell: str = "bash") -> None:
    """Print shell completion using the command names in the parser."""
    names = " ".join(verbs())
    if shell == "bash":
        print(f'_ret_complete() {{ COMPREPLY=( $(compgen -W "{names}" -- "${{COMP_WORDS[COMP_CWORD]}}") ); }}')
        print("complete -F _ret_complete ret")
    elif shell == "zsh":
        print("#compdef ret")
        print(f"_arguments '1:command:({names})'")
    elif shell == "fish":
        for name in verbs():
            print(f"complete -c ret -f -a {name}")
    else:
        raise ValueError(f"unsupported shell: {shell}")
