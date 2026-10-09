"""The command line grammar and its help and completion views."""

from __future__ import annotations

import argparse


_DESC = """Reticuli records and reproduces software claims.

Authoring
    init        initialize a workspace
    run         run and observe a command
    status      show work, claims, and unresolved inputs
    pack        create a claim from a project

Composition and transport
    pull        add another claim as a dependency
    export      write a portable claim archive
    import      restore a claim archive

Verification
    verify      verify claim identity
    audit       rerun acceptance criteria
    assess      measure specification strength

Reconstruction
    rebuild     rebuild an implementation from a claim
    crosscheck  compare independent realizations

Evidence
    record      write an execution record
    sign        authorize a claim or proof"""

_EPILOG = ("See 'ret <command> -h' for command usage.\n"
           "See 'ret help <command>' for detailed help; 'ret help -a' lists everything,\n"
           "including accepted older spellings.")

PORCELAIN = (
    "init", "run", "status", "pack", "pull", "export", "import",
    "verify", "audit", "assess", "rebuild", "crosscheck", "record", "sign",
)

# Older spellings which still express a current operation. Retired commands
# with changed meaning are deliberately absent from this table.
ALIASES: dict[str, str] = {}
_FULL_HELP: dict[str, str] = {}


def _add_verbose_json(command: argparse.ArgumentParser) -> None:
    """Add the common output controls to one action."""
    command.add_argument("-v", "--verbose", action="store_true", help="show more detail")
    command.add_argument("--json", action="store_true", help="print a JSON result")


def _parser() -> tuple[argparse.ArgumentParser, argparse._SubParsersAction]:
    """Construct the grammar once for parsing, help, and completion."""
    parser = argparse.ArgumentParser(
        prog="ret", description=_DESC, epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="store_true", help="show the version")
    commands = parser.add_subparsers(dest="command", metavar="command")

    def action(name: str, description: str) -> argparse.ArgumentParser:
        command = commands.add_parser(
            name, aliases=[alias for alias, target in ALIASES.items() if target == name],
            help=description, description=description,
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        _add_verbose_json(command)
        return command

    init = action("init", "initialize a workspace and wire the coding agent")
    init.add_argument("workspace", nargs="?", default=".")
    init.add_argument("--no-agent", action="store_true", help="skip agent hook setup")

    run = action("run", "run and observe a shell command")
    run.add_argument("command_text", nargs="+", metavar="command")
    run.add_argument("--workspace", default=".")

    status = action("status", "show work, claims, and unresolved inputs")
    status.add_argument("path", nargs="?", default=".")
    status.add_argument("--tree", action="store_true", help="show dependency structure")
    status.add_argument("--claims", action="store_true", help="list claims")
    status.add_argument("--files", action="store_true", help="show declared files")

    pack = action("pack", "create a claim from a project")
    pack.add_argument("path", nargs="?", default=".")
    pack.add_argument("--name")
    pack.add_argument("--generated", action="append", default=[])
    pack.add_argument("--input", "--inputs", dest="inputs", action="append", default=[])
    pack.add_argument("--gate")
    pack.add_argument("--gate-output")
    pack.add_argument("--inputs-manifest")
    pack.add_argument("--environment")
    pack.add_argument("--accept", action="store_true", help="accept and seal the claim")

    pull = action("pull", "add another claim as a dependency")
    pull.add_argument("claim")
    pull.add_argument("--workspace", default=".")

    export = action("export", "write a portable claim archive")
    export.add_argument("claim")
    export.add_argument("archive")
    export.add_argument("--blind", action="store_true")

    import_command = action("import", "restore a claim archive")
    import_command.add_argument("archive")
    import_command.add_argument("into")

    verify = action("verify", "verify claim identity")
    verify.add_argument("claim", nargs="?", default=".")

    audit = action("audit", "rerun acceptance criteria")
    audit.add_argument("claim", nargs="?", default=".")
    audit.add_argument("--shallow", action="store_true")

    assess = action("assess", "measure specification strength")
    assess.add_argument("claim", nargs="?", default=".")
    assess.add_argument("--mutants", type=int, default=20)

    rebuild = action("rebuild", "rebuild an implementation from a claim")
    rebuild.add_argument("claim")
    rebuild.add_argument("into")
    rebuild.add_argument("--producer")
    rebuild.add_argument("--without-guidance", action="store_true")
    rebuild.add_argument("--reuse", action="store_true")

    crosscheck = action("crosscheck", "compare independent realizations")
    crosscheck.add_argument("m1")
    crosscheck.add_argument("m2")
    crosscheck.add_argument("m3")
    crosscheck.add_argument("--mutants", type=int)
    crosscheck.add_argument("--record-proof", action="store_true")

    record = action("record", "write or check an execution record")
    record.add_argument("claim", nargs="?", default=".")
    record.add_argument("--key", help="SSH signing key")
    record.add_argument("--as", dest="identity", help="signer identity")
    record.add_argument("--check", action="store_true", help="check an existing record")
    record.add_argument("--output")

    sign = action("sign", "authorize a claim or proof")
    sign.add_argument("claim", nargs="?", default=".")
    sign.add_argument("--key")
    sign.add_argument("--as", dest="identity")
    sign.add_argument("--check", action="store_true")

    hook = commands.add_parser("hook", help="receive an agent hook event")
    hook.add_argument("event", nargs="?")
    help_command = commands.add_parser("help", help="show command help")
    help_command.add_argument("topic", nargs="?")
    help_command.add_argument("-a", "--all", action="store_true", help="show all commands")
    completion = commands.add_parser("completion", help="print shell completion")
    completion.add_argument("shell", choices=("bash", "zsh", "fish"))
    return parser, commands


def verbs() -> tuple[str, ...]:
    """List every accepted top-level command from the grammar."""
    _, commands = _parser()
    return tuple(commands.choices)


def _help_topic(topic: str) -> None:
    """Print usage for one registered command."""
    parser, commands = _parser()
    if topic in commands.choices:
        print(commands.choices[topic].format_help(), end="")
    else:
        parser.error(f"unknown command: {topic}")


def _help_all() -> None:
    """Print top-level help followed by help for each accepted command."""
    parser, commands = _parser()
    print(parser.format_help(), end="")
    for name in verbs():
        print(commands.choices[name].format_help(), end="")


def _completion(shell: str) -> None:
    """Print shell completion from the same registered command names."""
    names = " ".join(verbs())
    if shell == "bash":
        print("_ret_complete() {\n"
              f"    COMPREPLY=( $(compgen -W '{names}' -- \"${{COMP_WORDS[COMP_CWORD]}}\") )\n"
              "}\ncomplete -F _ret_complete ret")
    elif shell == "zsh":
        print(f"#compdef ret\n_arguments '1:command:({names})'")
    elif shell == "fish":
        print(f"complete -c ret -f -n '__fish_use_subcommand' -a '{names}'")
    else:
        raise ValueError(f"unsupported shell: {shell}")
