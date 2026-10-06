"""Argument grammar and help for the ``ret`` command.

Keep the command list in one place: help, topic lookup, and shell completion
all describe the same argparse grammar.
"""

from __future__ import annotations

import argparse
from collections.abc import Iterable


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

# The old command spelling remains useful in interactive work; the retired
# v1 verbs are intentionally absent from this table.
ALIASES: dict[str, str] = {"ls": "status"}

_FULL_HELP: dict[str, str] = {
    "init": "Initialize a workspace and optionally wire an agent.",
    "run": "Run a command in the workspace and observe its writes.",
    "status": "Show workspace work, claims, dependencies, or the claim tree.",
    "pack": "Create a claim from project inputs, outputs, and acceptance criteria.",
    "pull": "Add a claim as a dependency of the current workspace.",
    "export": "Write a portable archive of a claim.",
    "import": "Restore a claim archive into a workspace.",
    "verify": "Recompute and compare claim identity without running gates.",
    "audit": "Re-earn acceptance verdicts by running the gates.",
    "assess": "Measure the strength of the claim's specification.",
    "rebuild": "Regrow generated outputs from the claim's pinned inputs.",
    "crosscheck": "Compare original, transferred, and independent realizations.",
    "record": "Write or check a signed execution record.",
    "sign": "Authorize a claim or a recorded proof with a key.",
    "hook": "Handle the coding agent hook protocol.",
    "completion": "Print shell completion generated from the command grammar.",
    "help": "Show command help or list every accepted command.",
}


def _add_verbose_json(command: argparse.ArgumentParser) -> None:
    """Add the common human and machine output switches."""
    command.add_argument("-v", "--verbose", action="store_true", help="show details")
    command.add_argument("--json", action="store_true", help="write JSON")


def _parser() -> tuple[argparse.ArgumentParser, argparse._SubParsersAction]:
    """Build the command grammar and return its parser and command action."""
    parser = argparse.ArgumentParser(
        prog="ret", description=_DESC, epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    commands = parser.add_subparsers(dest="verb", metavar="command")

    def add(name: str) -> argparse.ArgumentParser:
        aliases = [alias for alias, target in ALIASES.items() if target == name]
        command = commands.add_parser(
            name, aliases=aliases, help=_FULL_HELP[name],
            description=_FULL_HELP[name],
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        _add_verbose_json(command)
        return command

    p = add("init")
    p.add_argument("workspace", nargs="?", default=".")
    p.add_argument("--no-agent", action="store_true")

    p = add("run")
    p.add_argument("command", nargs=argparse.REMAINDER)
    p.add_argument("--workspace", default=".")
    p.add_argument("--producer")

    p = add("status")
    p.add_argument("path", nargs="?", default=".")
    for flag in ("claims", "tree", "files", "deps"):
        p.add_argument("--" + flag, action="store_true")

    p = add("pack")
    p.add_argument("project", nargs="?", default=".")
    p.add_argument("--name")
    p.add_argument("--accept", action="store_true")
    p.add_argument("--inputs-manifest")

    p = add("pull")
    p.add_argument("claim")
    p.add_argument("--into", default=".")

    p = add("export")
    p.add_argument("claim")
    p.add_argument("archive", nargs="?")

    p = add("import")
    p.add_argument("archive")
    p.add_argument("--into", default=".")

    p = add("verify")
    p.add_argument("claim", nargs="?", default=".")

    p = add("audit")
    p.add_argument("claim", nargs="?", default=".")
    p.add_argument("--shallow", action="store_true")

    p = add("assess")
    p.add_argument("claim", nargs="?", default=".")

    p = add("rebuild")
    p.add_argument("claim")
    p.add_argument("--producer")
    p.add_argument("--into")
    p.add_argument("--without-guidance", action="store_true")

    p = add("crosscheck")
    p.add_argument("original")
    p.add_argument("transfer")
    p.add_argument("rebuild")

    p = add("record")
    p.add_argument("claim", nargs="?", default=".")
    p.add_argument("--key")
    p.add_argument("--as", dest="identity")
    p.add_argument("--check", action="store_true")

    p = add("sign")
    p.add_argument("claim", nargs="?", default=".")
    p.add_argument("--key")
    p.add_argument("--as", dest="identity")
    p.add_argument("--check", action="store_true")

    p = commands.add_parser("hook", help=_FULL_HELP["hook"])
    p.add_argument("event", nargs="?")
    p.add_argument("--workspace", default=".")

    p = commands.add_parser("help", help=_FULL_HELP["help"])
    p.add_argument("topic", nargs="?")
    p.add_argument("-a", "--all", action="store_true")

    p = commands.add_parser("completion", help=_FULL_HELP["completion"])
    p.add_argument("shell", choices=("bash", "zsh", "fish"), nargs="?", default="bash")
    return parser, commands


def verbs() -> tuple[str, ...]:
    """Every accepted first argument, in the grammar's display order."""
    _, commands = _parser()
    return tuple(commands.choices)


def _help_all() -> None:
    """Print top-level help followed by each command's full usage."""
    parser, commands = _parser()
    print(parser.format_help(), end="")
    for name in (*PORCELAIN, "hook", "help", "completion"):
        print("\n" + commands.choices[name].format_help(), end="")
    if ALIASES:
        print("\nAccepted older spellings:")
        for alias, target in ALIASES.items():
            print(f"  {alias} -> {target}")


def _help_topic(topic: str) -> None:
    """Print one command's detailed help, accepting its aliases."""
    parser, commands = _parser()
    if topic in commands.choices:
        print(commands.choices[topic].format_help(), end="")
    else:
        parser.error(f"unknown help topic: {topic}")


def _completion(shell: str = "bash") -> None:
    """Emit a small completion script from the live command grammar."""
    parser, commands = _parser()
    names = " ".join(commands.choices)
    if shell == "bash":
        print("_ret_complete() {\n"
              "    local cur=\"${COMP_WORDS[COMP_CWORD]}\"\n"
              f"    COMPREPLY=($(compgen -W '{names}' -- \"$cur\"))\n"
              "}\ncomplete -F _ret_complete ret")
    elif shell == "zsh":
        print("#compdef ret\n_arguments '1:command:({})'".format(names))
    elif shell == "fish":
        for name in commands.choices:
            print(f"complete -c ret -f -n '__fish_use_subcommand' -a '{name}'")
    else:
        parser.error(f"unsupported shell: {shell}")
