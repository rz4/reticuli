"""Argument grammar and help for the Reticuli command line."""

from __future__ import annotations

import argparse
import shlex


_DESC = "Reticuli records and reproduces software claims.\n\nAuthoring\n    init        initialize a workspace\n    run         run and observe a command\n    status      show work, claims, and unresolved inputs\n    pack        create a claim from a project\n\nComposition and transport\n    pull        add another claim as a dependency\n    export      write a portable claim archive\n    import      restore a claim archive\n\nVerification\n    verify      verify claim identity\n    audit       rerun acceptance criteria\n    assess      measure specification strength\n\nReconstruction\n    rebuild     rebuild an implementation from a claim\n    crosscheck  compare independent realizations\n\nEvidence\n    record      write an execution record\n    sign        authorize a claim or proof"
_EPILOG = "See 'ret <command> -h' for command usage.\nSee 'ret help <command>' for detailed help; 'ret help -a' lists everything,\nincluding accepted older spellings."

PORCELAIN = (
    "init", "run", "status", "pack", "pull", "export", "import",
    "verify", "audit", "assess", "rebuild", "crosscheck", "record", "sign",
)

# The older short spelling is kept in the grammar, so help and completion
# report the same set of accepted command words.
ALIASES = {"ls": "status"}
_PLUMBING = ("hook", "help", "completion")

_FULL_HELP = {
    "init": "Initialize a workspace and wire its agent hooks.",
    "run": "Run a shell command and record it in the workspace trace.",
    "status": "Show the current workspace, claims, and unresolved inputs.",
    "pack": "Create and seal a claim from project files and a gate.",
    "pull": "Add a claim's declared contents to this workspace.",
    "export": "Write a portable archive of a sealed claim.",
    "import": "Restore and verify a portable claim archive.",
    "verify": "Compare present pinned bytes with the sealed identity.",
    "audit": "Run the declared gates again to earn their verdicts.",
    "assess": "Measure the strength of a claim's criteria.",
    "rebuild": "Regrow generated outputs from pinned inputs.",
    "crosscheck": "Compare an original, transfer, and independent rebuild.",
    "record": "Write a portable execution record.",
    "sign": "Authorize a reviewed claim or proof.",
    "hook": "Receive an agent hook event on standard input.",
    "help": "Show command help.",
    "completion": "Print a shell completion script.",
}


def _add_verbose_json(command: argparse.ArgumentParser) -> None:
    """Add the common presentation flags to a command parser."""
    command.add_argument("-v", "--verbose", action="store_true", help="show details")
    command.add_argument("--json", action="store_true", help="write JSON output")


def _parser() -> tuple[argparse.ArgumentParser, argparse._SubParsersAction]:
    """Build the complete grammar, including accepted aliases and plumbing."""
    parser = argparse.ArgumentParser(
        prog="ret", description=_DESC, epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version="reticuli")
    commands = parser.add_subparsers(dest="command", metavar="command")

    def add(name: str, *, aliases: tuple[str, ...] = ()) -> argparse.ArgumentParser:
        command = commands.add_parser(name, aliases=list(aliases), help=_FULL_HELP[name])
        if name not in _PLUMBING:
            _add_verbose_json(command)
        return command

    def path(command: argparse.ArgumentParser, default: str = ".") -> None:
        command.add_argument("directory", nargs="?", default=default, help="claim or workspace directory")

    p = add("init")
    path(p)
    p.add_argument("--no-agent", action="store_true", help="skip agent hook setup")

    p = add("run")
    p.add_argument("shell_command", help="shell command to execute")
    p.add_argument("--directory", default=".", help="workspace directory")

    p = add("status", aliases=tuple(k for k, v in ALIASES.items() if v == "status"))
    path(p)
    for flag in ("claims", "tree", "deps"):
        p.add_argument("--" + flag, action="store_true", help="show " + flag)

    p = add("pack")
    path(p)
    p.add_argument("--name", help="claim name")
    p.add_argument("--generated", nargs="+", metavar="PATTERN", help="generated file patterns")
    p.add_argument("--input", action="append", default=[], metavar="PATTERN", help="pinned input pattern")
    p.add_argument("--gate", help="acceptance command")
    p.add_argument("--output", help="gate verdict file")
    p.add_argument("--accept", action="store_true", help="seal the claim")
    p.add_argument("--inputs-manifest", metavar="FILE")
    p.add_argument("--environment", metavar="FILE")

    p = add("pull")
    p.add_argument("source", help="claim to pull")
    p.add_argument("--into", default=".", help="workspace directory")

    p = add("export")
    p.add_argument("directory", help="claim directory")
    p.add_argument("archive", help="output archive")
    p.add_argument("--blind", action="store_true", help="omit generated files")

    p = add("import")
    p.add_argument("archive", help="archive to restore")
    p.add_argument("into", help="target directory")

    p = add("verify")
    path(p)

    p = add("audit")
    path(p)
    p.add_argument("--shallow", action="store_true", help="audit only this claim")

    p = add("assess")
    path(p)
    p.add_argument("--mutants", type=int, default=32, help="maximum mutants to test")

    p = add("rebuild")
    p.add_argument("directory", help="source claim")
    p.add_argument("--producer", required=True, help="producer command")
    p.add_argument("--into", required=True, help="target directory")
    p.add_argument("--without-guidance", action="store_true", help="withhold producer hints")

    p = add("crosscheck")
    for machine in ("m1", "m2", "m3"):
        p.add_argument(machine, help="claim directory or record")
    p.add_argument("--mutants", type=int, default=0, help="mutants to test")

    p = add("record")
    path(p)
    p.add_argument("--into", metavar="FILE", help="record destination")
    p.add_argument("--key", metavar="FILE", help="signing key")
    p.add_argument("--as", dest="identity", metavar="NAME", help="signer identity")
    p.add_argument("--check", action="store_true", help="check a record")

    p = add("sign")
    path(p)
    p.add_argument("--key", metavar="FILE", help="signing key")
    p.add_argument("--as", dest="identity", metavar="NAME", help="signer identity")
    p.add_argument("--check", action="store_true", help="check authorization")

    add("hook")
    p = add("help")
    p.add_argument("topic", nargs="?", help="command to explain")
    p.add_argument("-a", "--all", action="store_true", help="list all accepted commands")
    p = add("completion")
    p.add_argument("shell", nargs="?", default="bash", choices=("bash",), help="target shell")
    return parser, commands


def verbs() -> tuple[str, ...]:
    """List every command word accepted by the grammar."""
    _, commands = _parser()
    return tuple(commands.choices)


def _help_topic(topic: str) -> str:
    """Return detailed help for a command or accepted alias."""
    parser, commands = _parser()
    if topic not in commands.choices:
        raise ValueError(f"unknown command: {topic}")
    canonical = ALIASES.get(topic, topic)
    return _FULL_HELP[canonical] + "\n\n" + commands.choices[topic].format_help()


def _help_all() -> str:
    """Return top level help and the full accepted command list."""
    parser, _ = _parser()
    return parser.format_help() + "\nCommands: " + ", ".join(verbs()) + "\n"


def _completion(shell: str = "bash") -> None:
    """Print shell completion words drawn from the actual argument grammar."""
    if shell != "bash":
        raise ValueError(f"unsupported shell: {shell}")
    parser, commands = _parser()
    words = set(commands.choices)
    words.update(option for option in parser._option_string_actions)
    for command in set(commands.choices.values()):
        words.update(command._option_string_actions)
    options = " ".join(shlex.quote(word) for word in sorted(words))
    print(f"_ret_complete() {{ COMPREPLY=( $(compgen -W \"{options}\" -- \"${{COMP_WORDS[COMP_CWORD]}}\") ); }}")
    print("complete -F _ret_complete ret")
