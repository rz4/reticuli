"""Argument grammar and help for the ``ret`` command.

Keep the command names in one place so help, dispatch, and completion use
the same vocabulary.
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

# Accepted short forms. Retired v1 command names are deliberately absent.
ALIASES = {"ls": "status", "check": "verify", "build": "rebuild"}
_FULL_HELP = {}


def _add_verbose_json(command: argparse.ArgumentParser) -> None:
    """Attach the shared presentation options to a command."""
    command.add_argument("-v", "--verbose", action="store_true", help="show details")
    command.add_argument("--json", action="store_true", help="write one JSON result")


def _parser() -> tuple[argparse.ArgumentParser, argparse._SubParsersAction]:
    p = argparse.ArgumentParser(
        prog="ret", description=_DESC, epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--version", action="version", version="reticuli")
    sub = p.add_subparsers(dest="verb", metavar="command")
    commands = {}

    def add(name: str, help_text: str) -> argparse.ArgumentParser:
        aliases = [alias for alias, target in ALIASES.items() if target == name]
        command = sub.add_parser(name, aliases=aliases, help=help_text,
                                 description=help_text)
        _add_verbose_json(command)
        commands[name] = command
        return command

    c = add("init", "initialize a workspace")
    c.add_argument("directory", nargs="?", default=".")
    c.add_argument("--no-agent", action="store_true")

    c = add("run", "run and observe a command")
    c.add_argument("command", nargs=argparse.REMAINDER)
    c.add_argument("-C", "--directory", default=".")

    c = add("status", "show work, claims, and unresolved inputs")
    c.add_argument("directory", nargs="?", default=".")
    c.add_argument("--tree", action="store_true")
    c.add_argument("--claims", action="store_true")
    c.add_argument("--deps", action="store_true")

    c = add("pack", "create a claim from a project")
    c.add_argument("directory", nargs="?", default=".")
    c.add_argument("--name")
    c.add_argument("--inputs", nargs="*")
    c.add_argument("--inputs-manifest")
    c.add_argument("--output", action="append")
    c.add_argument("--gate")
    c.add_argument("--verdict")
    c.add_argument("--accept", action="store_true")

    c = add("pull", "add another claim as a dependency")
    c.add_argument("claim")
    c.add_argument("--into", default=".")

    c = add("export", "write a portable claim archive")
    c.add_argument("claim")
    c.add_argument("archive")

    c = add("import", "restore a claim archive")
    c.add_argument("archive")
    c.add_argument("into")

    c = add("verify", "verify claim identity")
    c.add_argument("claim", nargs="?", default=".")

    c = add("audit", "rerun acceptance criteria")
    c.add_argument("claim", nargs="?", default=".")
    c.add_argument("--shallow", action="store_true")

    c = add("assess", "measure specification strength")
    c.add_argument("claim", nargs="?", default=".")
    c.add_argument("--mutants", type=int, default=10)

    c = add("rebuild", "rebuild an implementation from a claim")
    c.add_argument("claim")
    c.add_argument("--producer")
    c.add_argument("--into")
    c.add_argument("--without-guidance", action="store_true")
    c.add_argument("--reuse", action="store_true")

    c = add("crosscheck", "compare independent realizations")
    c.add_argument("m1")
    c.add_argument("m2")
    c.add_argument("m3")
    c.add_argument("--mutants", type=int)
    c.add_argument("--record", action="store_true")

    c = add("record", "write an execution record")
    c.add_argument("claim", nargs="?", default=".")
    c.add_argument("--key")
    c.add_argument("--as", dest="principal")
    c.add_argument("--check", action="store_true")
    c.add_argument("--into")

    c = add("sign", "authorize a claim or proof")
    c.add_argument("claim", nargs="?", default=".")
    c.add_argument("--key")
    c.add_argument("--as", dest="principal")
    c.add_argument("--check", action="store_true")

    c = sub.add_parser("hook", help="receive an authoring hook")
    c.add_argument("event", nargs="?")
    c = sub.add_parser("help", help="show command help")
    c.add_argument("topic", nargs="?")
    c.add_argument("-a", "--all", action="store_true")
    c = sub.add_parser("completion", help="print shell completion")
    c.add_argument("shell", nargs="?", default="bash", choices=("bash", "zsh", "fish"))

    _FULL_HELP.clear()
    _FULL_HELP.update(commands)
    _FULL_HELP.update({name: sub.choices[name] for name in ("hook", "help", "completion")})
    return p, sub


def verbs() -> list[str]:
    """Return every accepted top-level command spelling."""
    return [*PORCELAIN, *ALIASES, "hook", "help", "completion"]


def _help_all() -> None:
    p, _ = _parser()
    print(p.format_help(), end="")
    for name in verbs():
        print(f"\nret {name}\n")
        print(_FULL_HELP[name].format_help(), end="")


def _help_topic(topic: str | None = None) -> None:
    p, _ = _parser()
    if topic is None:
        print(p.format_help(), end="")
    elif topic in _FULL_HELP:
        print(_FULL_HELP[topic].format_help(), end="")
    else:
        p.error(f"unknown command: {topic}")


def _completion(shell: str = "bash") -> None:
    """Print a small completion script generated from the accepted grammar."""
    words = " ".join(verbs())
    if shell == "bash":
        print(f"_ret_complete() {{ COMPREPLY=( $(compgen -W '{words}' -- \"${{COMP_WORDS[COMP_CWORD]}}\") ); }}")
        print("complete -F _ret_complete ret")
    elif shell == "zsh":
        print(f"#compdef ret\n_arguments '1:command:({words})'")
    elif shell == "fish":
        for word in verbs():
            print(f"complete -c ret -f -a {word}")
    else:
        raise ValueError(f"unsupported shell: {shell}")


__all__ = ["PORCELAIN", "ALIASES", "verbs", "_parser", "_help_all",
           "_help_topic", "_completion"]
