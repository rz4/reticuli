"""The public command-line grammar and its help and completion views."""

from __future__ import annotations

import argparse
import sys


_DESC = ("Reticuli records and reproduces software claims.\n\n"
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
         "    sign        authorize a claim or proof")

_EPILOG = ("See 'ret <command> -h' for command usage.\n"
           "See 'ret help <command>' for detailed help; 'ret help -a' lists everything,\n"
           "including accepted older spellings.")

PORCELAIN = (
    "init", "run", "status", "pack", "pull", "export", "import",
    "verify", "audit", "assess", "rebuild", "crosscheck", "record", "sign",
)

# Accepted spellings with the same argument grammar as their canonical verb.
ALIASES: dict[str, str] = {
    "ls": "status",
    "check": "verify",
    "redo": "rebuild",
}

_FULL_HELP: dict[str, str] = {
    "init": "Initialize a workspace and install its agent hook.",
    "run": "Run a command in a workspace and record it.",
    "status": "Show the current work, claims, and unresolved inputs.",
    "pack": "Create and seal a claim from a project.",
    "pull": "Add another claim as a dependency.",
    "export": "Write a portable claim archive.",
    "import": "Restore a portable claim archive.",
    "verify": "Verify the content address of a claim.",
    "audit": "Rerun a claim's acceptance criteria.",
    "assess": "Measure the strength of a claim's criteria.",
    "rebuild": "Rebuild an implementation from a claim.",
    "crosscheck": "Compare independent realizations.",
    "record": "Write or check an execution record.",
    "sign": "Authorize a claim or proof.",
    "hook": "Receive an agent hook event.",
    "help": "Show command help.",
    "completion": "Print a shell completion script.",
}


def _add_verbose_json(command: argparse.ArgumentParser) -> None:
    """Add the common output switches to a command parser."""
    command.add_argument("-v", "--verbose", action="store_true", help="show details")
    command.add_argument("--json", action="store_true", help="print machine-readable JSON")


def _configure(command: argparse.ArgumentParser, verb: str) -> None:
    """Register one command's arguments."""
    if verb in PORCELAIN:
        _add_verbose_json(command)
    if verb == "init":
        command.add_argument("directory", nargs="?", default=".")
        command.add_argument("--no-agent", action="store_true")
    elif verb == "run":
        command.add_argument("--directory", default=".")
        command.add_argument("command", nargs=argparse.REMAINDER)
    elif verb == "status":
        command.add_argument("directory", nargs="?", default=".")
        for flag in ("tree", "claims", "deps", "structure"):
            command.add_argument("--" + flag, action="store_true")
    elif verb == "pack":
        command.add_argument("directory", nargs="?", default=".")
        command.add_argument("--name")
        command.add_argument("--into")
        command.add_argument("--generated", action="append", default=[])
        command.add_argument("--input", action="append", default=[])
        command.add_argument("--inputs-manifest")
        command.add_argument("--gate", action="append", default=[])
        command.add_argument("--accept", action="store_true")
    elif verb == "pull":
        command.add_argument("claim")
        command.add_argument("--workspace", default=".")
    elif verb == "export":
        command.add_argument("claim")
        command.add_argument("archive")
        command.add_argument("--blind", action="store_true")
    elif verb == "import":
        command.add_argument("archive")
        command.add_argument("into")
    elif verb in ("verify", "audit", "assess"):
        command.add_argument("claim")
        if verb == "audit":
            command.add_argument("--shallow", action="store_true")
        if verb == "assess":
            command.add_argument("--mutants", type=int, default=100)
    elif verb == "rebuild":
        command.add_argument("claim")
        command.add_argument("--producer")
        command.add_argument("--into")
        command.add_argument("--without-guidance", action="store_true")
    elif verb == "crosscheck":
        for name in ("m1", "m2", "m3"):
            command.add_argument(name)
        command.add_argument("--mutants", type=int)
    elif verb == "record":
        command.add_argument("claim")
        command.add_argument("--key")
        command.add_argument("--as", dest="identity")
        command.add_argument("--check", action="store_true")
    elif verb == "sign":
        command.add_argument("claim")
        command.add_argument("--key", required=True)
        command.add_argument("--as", dest="identity")
        command.add_argument("--check", action="store_true")
    elif verb == "hook":
        command.add_argument("event", nargs="?")
    elif verb == "help":
        command.add_argument("topic", nargs="?")
        command.add_argument("-a", "--all", action="store_true")
    elif verb == "completion":
        command.add_argument("shell", choices=("bash",), nargs="?", default="bash")


def _parser() -> tuple[argparse.ArgumentParser, argparse._SubParsersAction]:
    parser = argparse.ArgumentParser(
        prog="ret", description=_DESC, epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    commands = parser.add_subparsers(dest="verb", metavar="<command>")
    for verb in (*PORCELAIN, "hook", "help", "completion"):
        command = commands.add_parser(verb, help=_FULL_HELP[verb],
                                      description=_FULL_HELP[verb])
        _configure(command, verb)
    for alias, target in ALIASES.items():
        command = commands.add_parser(alias, help=f"alias for {target}",
                                      description=_FULL_HELP[target])
        _configure(command, target)
        command.set_defaults(verb=target)
    return parser, commands


def verbs() -> tuple[str, ...]:
    """Return the names accepted by the command grammar."""
    return tuple(_parser()[1].choices)


def _help_topic(topic: str) -> None:
    """Print detailed help for a command or alias."""
    parser, commands = _parser()
    if topic not in commands.choices:
        parser.error(f"unknown command: {topic}")
    print(commands.choices[topic].format_help(), end="")


def _help_all() -> None:
    """Print all commands and their usage, including aliases."""
    parser, commands = _parser()
    print(parser.format_help(), end="")
    for name, command in commands.choices.items():
        print(f"\n{name}\n{command.format_help()}", end="")


def _completion(shell: str = "bash") -> None:
    """Print completion based on the registered grammar."""
    if shell != "bash":
        raise ValueError(f"unsupported shell: {shell}")
    _, commands = _parser()
    words = " ".join(commands.choices)
    print("_ret_complete() {\n"
          "    if (( COMP_CWORD == 1 )); then\n"
          f"        COMPREPLY=( $(compgen -W '{words}' -- \"${{COMP_WORDS[COMP_CWORD]}}\") )\n"
          "    fi\n"
          "}\n"
          "complete -F _ret_complete ret")


def main(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse arguments, handling grammar-only help and completion requests."""
    parser, _ = _parser()
    args = parser.parse_args(argv)
    if args.verb == "help":
        if args.all:
            _help_all()
        elif args.topic:
            _help_topic(args.topic)
        else:
            parser.print_help()
    elif args.verb == "completion":
        _completion(args.shell)
    return args


if __name__ == "__main__":
    main(sys.argv[1:])
