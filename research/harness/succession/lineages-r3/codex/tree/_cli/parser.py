"""Argument grammar and help for the ``ret`` command line.

The command table is the source for parsing, help, verb discovery, and shell
completion.  Older operations that became flags are deliberately absent.
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

# These spellings are accepted for convenience; retired v1 verbs are not.
ALIASES = {"ls": "status", "check": "verify"}

_HELP = {
    "init": "initialize a workspace",
    "run": "run and observe a command",
    "status": "show work, claims, and unresolved inputs",
    "pack": "create a claim from a project",
    "pull": "add another claim as a dependency",
    "export": "write a portable claim archive",
    "import": "restore a claim archive",
    "verify": "verify claim identity",
    "audit": "rerun acceptance criteria",
    "assess": "measure specification strength",
    "rebuild": "rebuild an implementation from a claim",
    "crosscheck": "compare independent realizations",
    "record": "write or check an execution record",
    "sign": "authorize a claim or proof",
    "hook": "receive an agent hook event",
    "help": "show command help",
    "completion": "write shell completion code",
}
_FULL_HELP = dict(_HELP)


def _add_verbose_json(command: argparse.ArgumentParser) -> None:
    """Add the shared presentation flags to a command."""
    command.add_argument("-v", "--verbose", action="store_true", help="show more detail")
    command.add_argument("--json", action="store_true", help="write machine readable JSON")


def _parser() -> tuple[argparse.ArgumentParser, dict[str, argparse.ArgumentParser]]:
    """Construct the grammar and return the top parser and command parsers."""
    top = argparse.ArgumentParser(
        prog="ret", description=_DESC, epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    top.add_argument("--version", action="store_true", help="show version")
    sub = top.add_subparsers(dest="command", metavar="command")
    commands: dict[str, argparse.ArgumentParser] = {}
    for name in (*PORCELAIN, "hook", "help", "completion"):
        commands[name] = sub.add_parser(name, help=_HELP[name], description=_HELP[name])

    commands["init"].add_argument("workspace", nargs="?", default=".")
    commands["init"].add_argument("--no-agent", action="store_true")
    commands["run"].add_argument("script", help="shell command to execute")
    commands["run"].add_argument("--workspace", default=".")

    status = commands["status"]
    status.add_argument("workspace", nargs="?", default=".")
    status.add_argument("--tree", action="store_true", help="show dependency tree")
    status.add_argument("--claims", action="store_true", help="list sealed claims")
    status.add_argument("--deps", action="store_true", help="show dependencies")

    pack = commands["pack"]
    pack.add_argument("project", nargs="?", default=".")
    pack.add_argument("--name")
    pack.add_argument("--generated", action="append", default=[])
    pack.add_argument("--input", action="append", default=[])
    pack.add_argument("--gate")
    pack.add_argument("--gate-output")
    pack.add_argument("--accept", action="store_true", help="accept and seal the generated claim")
    pack.add_argument("--inputs-manifest")
    pack.add_argument("--environment")
    pack.add_argument("--format", type=int, dest="claim_format")

    commands["pull"].add_argument("claim")
    commands["pull"].add_argument("--workspace", default=".")
    commands["export"].add_argument("claim")
    commands["export"].add_argument("archive")
    commands["export"].add_argument("--blind", action="store_true")
    commands["import"].add_argument("archive")
    commands["import"].add_argument("into")
    commands["verify"].add_argument("claim", nargs="?", default=".")
    commands["audit"].add_argument("claim", nargs="?", default=".")
    commands["audit"].add_argument("--shallow", action="store_true")
    commands["assess"].add_argument("claim", nargs="?", default=".")
    commands["assess"].add_argument("--mutants", type=int, default=100)

    rebuild = commands["rebuild"]
    rebuild.add_argument("claim")
    rebuild.add_argument("into")
    rebuild.add_argument("--producer")
    rebuild.add_argument("--without-guidance", action="store_true")
    crosscheck = commands["crosscheck"]
    for leg in ("m1", "m2", "m3"):
        crosscheck.add_argument(leg)
    crosscheck.add_argument("--record-proof", action="store_true")

    record = commands["record"]
    record.add_argument("claim", nargs="?", default=".")
    record.add_argument("--key")
    record.add_argument("--as", dest="signer")
    record.add_argument("--check", action="store_true")
    sign = commands["sign"]
    sign.add_argument("claim", nargs="?", default=".")
    sign.add_argument("--key")
    sign.add_argument("--as", dest="signer")
    sign.add_argument("--check", action="store_true")

    commands["hook"].add_argument("event", nargs="?")
    commands["help"].add_argument("topic", nargs="?")
    commands["help"].add_argument("-a", "--all", action="store_true")
    commands["completion"].add_argument("shell", choices=("bash",), nargs="?", default="bash")

    for alias, target in ALIASES.items():
        commands[alias] = sub.add_parser(alias, help=f"alias for {target}", description=_HELP[target])
        # The alias has the same options and positional arguments as its target.
        for action in commands[target]._actions:
            if action.dest != "help":
                commands[alias]._add_action(action)
        commands[alias].set_defaults(command=target)

    for name, command in commands.items():
        if name not in ("help", "completion", "hook"):
            _add_verbose_json(command)
    return top, commands


def verbs() -> tuple[str, ...]:
    """Return every accepted top-level command spelling."""
    return (*PORCELAIN, *ALIASES, "hook", "help", "completion")


def _help_topic(topic: str | None = None) -> None:
    top, commands = _parser()
    if topic is None:
        print(top.format_help(), end="")
    elif topic in commands:
        print(commands[topic].format_help(), end="")
    else:
        top.error(f"unknown help topic: {topic}")


def _help_all() -> None:
    top, commands = _parser()
    print(top.format_help(), end="")
    for name in verbs():
        print(commands[name].format_help(), end="")


def _completion(shell: str = "bash") -> None:
    """Print completion from the command grammar, including command options."""
    if shell != "bash":
        raise ValueError(f"unsupported shell: {shell}")
    _, commands = _parser()
    words = " ".join(verbs())
    print("_ret_complete() {")
    print("    local current=${COMP_WORDS[COMP_CWORD]}")
    print("    if [[ $COMP_CWORD -eq 1 ]]; then")
    print(f"        COMPREPLY=( $(compgen -W '{words}' -- \"$current\") )")
    print("        return")
    print("    fi")
    print("    case ${COMP_WORDS[1]} in")
    for name in verbs():
        flags = " ".join(dict.fromkeys(option for action in commands[name]._actions
                                       for option in action.option_strings))
        print(f"        {name}) COMPREPLY=( $(compgen -W '{flags}' -- \"$current\") ) ;;")
    print("    esac")
    print("}")
    print("complete -F _ret_complete ret")


if __name__ == "__main__":
    _help_topic(sys.argv[1] if len(sys.argv) > 1 else None)
