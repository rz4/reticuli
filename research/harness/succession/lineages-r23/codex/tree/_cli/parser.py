"""Argument grammar and help for the Reticuli command line."""

from __future__ import annotations

import argparse


_DESC = "Reticuli records and reproduces software claims.\n\nAuthoring\n    init        initialize a workspace\n    run         run and observe a command\n    status      show work, claims, and unresolved inputs\n    pack        create a claim from a project\n\nComposition and transport\n    pull        add another claim as a dependency\n    export      write a portable claim archive\n    import      restore a claim archive\n\nVerification\n    verify      verify claim identity\n    audit       rerun acceptance criteria\n    assess      measure specification strength\n\nReconstruction\n    rebuild     rebuild an implementation from a claim\n    crosscheck  compare independent realizations\n\nEvidence\n    record      write an execution record\n    sign        authorize a claim or proof"
_EPILOG = "See 'ret <command> -h' for command usage.\nSee 'ret help <command>' for detailed help; 'ret help -a' lists everything,\nincluding accepted older spellings."

PORCELAIN = (
    "init", "run", "status", "pack", "pull", "export", "import",
    "verify", "audit", "assess", "rebuild", "crosscheck", "record", "sign",
)
# Shortcuts are registered on the same parsers as their canonical commands.
ALIASES = {"ls": "status", "check": "verify"}
_FULL_HELP = {
    "init": "Initialize a workspace and, by default, wire its agent hook.",
    "run": "Run a command in a workspace and record its exit code.",
    "status": "Show workspace state, claims, and unresolved dependencies.",
    "pack": "Create and seal a claim from generated files and pinned inputs.",
    "pull": "Add another sealed claim as a dependency.",
    "export": "Write a portable archive of a sealed claim.",
    "import": "Restore a portable claim archive.",
    "verify": "Compare present pinned bytes with the sealed claim identity.",
    "audit": "Run acceptance gates again and report their earned verdicts.",
    "assess": "Measure the strength of a claim's acceptance criteria.",
    "rebuild": "Regrow generated files from pinned inputs with a producer.",
    "crosscheck": "Compare original, transferred, and independently rebuilt claims.",
    "record": "Write or check a portable execution record.",
    "sign": "Authorize a claim or check an existing authorization.",
    "hook": "Receive an agent hook event.",
}


def _add_verbose_json(command: argparse.ArgumentParser) -> None:
    """Add the output controls shared by porcelain commands."""
    command.add_argument("-v", "--verbose", action="store_true", help="show detailed output")
    command.add_argument("--json", action="store_true", help="write a JSON result")


def _parser():
    """Build the parser and return it with its command parsers."""
    top = argparse.ArgumentParser(
        prog="ret", description=_DESC, epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    commands = top.add_subparsers(dest="command", metavar="command")
    result = {}
    for name in PORCELAIN:
        aliases = [alias for alias, target in ALIASES.items() if target == name]
        command = commands.add_parser(name, aliases=aliases,
                                      help=_FULL_HELP[name],
                                      description=_FULL_HELP[name])
        command.set_defaults(verb=name)
        _add_verbose_json(command)
        result[name] = command
        for alias in aliases:
            result[alias] = command

    result["init"].add_argument("directory", nargs="?", default=".")
    result["init"].add_argument("--no-agent", action="store_true")
    result["run"].add_argument("shell_command")
    result["run"].add_argument("--directory", default=".")
    result["status"].add_argument("directory", nargs="?", default=".")
    for flag in ("tree", "claims", "deps"):
        result["status"].add_argument("--" + flag, action="store_true")
    result["pack"].add_argument("directory", nargs="?", default=".")
    result["pack"].add_argument("--name")
    result["pack"].add_argument("--generated", action="append", default=[])
    result["pack"].add_argument("--input", action="append", default=[])
    result["pack"].add_argument("--gate")
    result["pack"].add_argument("--gate-output")
    result["pack"].add_argument("--accept", action="store_true")
    result["pull"].add_argument("claim")
    result["pull"].add_argument("--workspace", default=".")
    result["export"].add_argument("claim")
    result["export"].add_argument("archive")
    result["export"].add_argument("--blind", action="store_true")
    result["import"].add_argument("archive")
    result["import"].add_argument("into")
    for name in ("verify", "audit", "assess", "record", "sign"):
        result[name].add_argument("claim", nargs="?", default=".")
    result["audit"].add_argument("--shallow", action="store_true")
    result["assess"].add_argument("--mutants", type=int, default=100)
    result["rebuild"].add_argument("claim")
    result["rebuild"].add_argument("into")
    result["rebuild"].add_argument("--producer", required=True)
    result["rebuild"].add_argument("--without-guidance", action="store_true")
    for leg in ("m1", "m2", "m3"):
        result["crosscheck"].add_argument(leg)
    result["crosscheck"].add_argument("--record-proof", action="store_true")
    result["record"].add_argument("--key")
    result["record"].add_argument("--as", dest="identity")
    result["record"].add_argument("--check", action="store_true")
    result["sign"].add_argument("--key")
    result["sign"].add_argument("--as", dest="identity")
    result["sign"].add_argument("--check", action="store_true")

    hook = commands.add_parser("hook", help="receive an agent hook event")
    hook.set_defaults(verb="hook")
    result["hook"] = hook
    help_command = commands.add_parser("help", help="show command help")
    help_command.add_argument("topic", nargs="?")
    help_command.add_argument("-a", "--all", action="store_true")
    help_command.set_defaults(verb="help")
    result["help"] = help_command
    completion = commands.add_parser("completion", help="print shell completion")
    completion.add_argument("shell", choices=("bash",))
    completion.set_defaults(verb="completion")
    result["completion"] = completion
    return top, result


def verbs():
    """All accepted command words, in their displayed order."""
    return (*PORCELAIN, *ALIASES, "hook", "help", "completion")


def _help_topic(topic):
    top, commands = _parser()
    if topic is None:
        print(top.format_help(), end="")
        return
    if topic not in commands:
        raise ValueError(f"unknown command: {topic}")
    print(commands[topic].format_help(), end="")


def _help_all():
    top, commands = _parser()
    print(top.format_help(), end="")
    for name in verbs():
        print(commands[name].format_help(), end="")


def _completion(shell):
    """Print completion words generated from the registered grammar."""
    if shell != "bash":
        raise ValueError(f"unsupported shell: {shell}")
    top, commands = _parser()
    words = " ".join(commands)
    print("_ret_complete() {\n"
          f"    COMPREPLY=( $(compgen -W '{words}' -- \"${{COMP_WORDS[COMP_CWORD]}}\") )\n"
          "}\n"
          "complete -F _ret_complete ret")
