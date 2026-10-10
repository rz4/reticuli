"""Argument grammar and help for the Reticuli command line.

The command table is the source for parsing, help, and shell completion.
"""

from __future__ import annotations

import argparse
import shlex
import sys


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

# Compatibility spellings that fold into the current porcelain grammar.
ALIASES = {
    "ls": "status", "deps": "status", "structure": "status",
    "review": "sign", "sign-check": "sign", "attest-check": "record",
}

_FULL_HELP = {
    "init": "Initialize a workspace and optionally wire agent hooks.",
    "run": "Run a command and record it in the workspace trace.",
    "status": "Show workspace, claim, dependency, or tree status.",
    "pack": "Build and seal a claim from declared project files and a gate.",
    "pull": "Add a sealed claim as a dependency of this workspace.",
    "export": "Write a portable archive of a sealed claim.",
    "import": "Restore and verify a portable claim archive.",
    "verify": "Check the sealed identity against the pinned bytes present.",
    "audit": "Run the acceptance gates again in a cold room.",
    "assess": "Measure the strength of a claim's specification.",
    "rebuild": "Regrow generated outputs from pinned inputs.",
    "crosscheck": "Compare an original, a transfer, and an independent rebuild.",
    "record": "Write or check a portable execution record.",
    "sign": "Review, sign, or check authorization of a claim or proof.",
    "hook": "Consume one agent hook event from standard input.",
    "help": "Show command help.",
    "completion": "Print shell completion derived from the command grammar.",
}


def _add_verbose_json(command: argparse.ArgumentParser) -> None:
    """Give a porcelain command the common presentation switches."""
    command.add_argument("-v", "--verbose", action="store_true", help="show more detail")
    command.add_argument("--json", action="store_true", help="emit a JSON result")


def _parser() -> tuple[argparse.ArgumentParser, argparse._SubParsersAction]:
    """Construct the complete parser and return it with its command registry."""
    parser = argparse.ArgumentParser(
        prog="ret", description=_DESC, epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version="reticuli")
    sub = parser.add_subparsers(dest="verb", metavar="command", required=True)

    def command(name: str, *, common: bool = True) -> argparse.ArgumentParser:
        child = sub.add_parser(name, help=_FULL_HELP[name], description=_FULL_HELP[name])
        if common:
            _add_verbose_json(child)
        return child

    p = command("init")
    p.add_argument("workspace", nargs="?", default=".")
    p.add_argument("--no-agent", action="store_true")

    p = command("run")
    p.add_argument("--workspace", default=".")
    p.add_argument("command", nargs=argparse.REMAINDER)

    p = command("status")
    p.add_argument("workspace", nargs="?", default=".")
    for flag in ("tree", "claims", "deps", "structure"):
        p.add_argument("--" + flag, action="store_true")

    p = command("pack")
    p.add_argument("root")
    p.add_argument("name")
    p.add_argument("--generated", action="append", default=[])
    p.add_argument("--input", "--inputs", dest="inputs", action="append", default=[])
    p.add_argument("--gate", required=True)
    p.add_argument("--gate-output", required=True)
    p.add_argument("--inputs-manifest")
    p.add_argument("--environment")
    p.add_argument("--format", type=int, dest="claim_format", default=3)
    p.add_argument("--mutation-floor", type=float)
    p.add_argument("--requires", action="append")
    p.add_argument("--by")
    p.add_argument("--accept", action="store_true")

    p = command("pull")
    p.add_argument("claim")
    p.add_argument("workspace", nargs="?", default=".")

    p = command("export")
    p.add_argument("claim")
    p.add_argument("archive")
    p.add_argument("--blind", action="store_true")

    p = command("import")
    p.add_argument("archive")
    p.add_argument("into")

    for name in ("verify", "audit", "assess"):
        p = command(name)
        p.add_argument("claim", nargs="?", default=".")
        if name == "audit":
            p.add_argument("--shallow", action="store_true")
        elif name == "assess":
            p.add_argument("--mutants", type=int, default=100)

    p = command("rebuild")
    p.add_argument("claim")
    p.add_argument("producer")
    p.add_argument("into")
    p.add_argument("--without-guidance", action="store_true")
    p.add_argument("--reuse", action="store_true")

    p = command("crosscheck")
    for machine in ("m1", "m2", "m3"):
        p.add_argument(machine)
    p.add_argument("--mutants", type=int)
    p.add_argument("--record-proof", action="store_true")

    p = command("record")
    p.add_argument("claim", nargs="?", default=".")
    p.add_argument("--output")
    p.add_argument("--key")
    p.add_argument("--as", dest="identity")
    p.add_argument("--check", action="store_true")
    p.add_argument("--signers")

    p = command("sign")
    p.add_argument("claim", nargs="?", default=".")
    p.add_argument("--key")
    p.add_argument("--as", dest="identity")
    p.add_argument("--check", action="store_true")
    p.add_argument("--review", action="store_true")
    p.add_argument("--signers")

    for alias, target in ALIASES.items():
        p = sub.add_parser(alias, help=argparse.SUPPRESS, description=_FULL_HELP[target])
        _add_verbose_json(p)
        p.add_argument("claim", nargs="?", default=".")
        p.set_defaults(canonical=target)

    p = command("hook", common=False)
    p.add_argument("event", nargs="?")
    p = command("help", common=False)
    p.add_argument("topic", nargs="?")
    p.add_argument("-a", "--all", action="store_true")
    p = command("completion", common=False)
    p.add_argument("shell", choices=("bash", "zsh", "fish"), nargs="?", default="bash")
    return parser, sub


def verbs() -> tuple[str, ...]:
    """Return the verb names accepted by the parser."""
    _, sub = _parser()
    return tuple(sub.choices)


def _help_topic(topic: str) -> None:
    """Print detailed help for one command or alias."""
    parser, sub = _parser()
    if topic in sub.choices:
        sub.choices[topic].print_help()
    else:
        parser.error(f"unknown help topic: {topic}")


def _help_all() -> None:
    """Print the top-level help and every accepted command spelling."""
    parser, sub = _parser()
    parser.print_help()
    for name in sub.choices:
        print("\n" + "=" * 8 + " " + name + " " + "=" * 8)
        sub.choices[name].print_help()


def _completion(shell: str = "bash") -> None:
    """Print a completion script from the actual parser registrations."""
    _, sub = _parser()
    names = " ".join(sub.choices)
    if shell == "bash":
        print("_ret_complete() {")
        print("    local cur=${COMP_WORDS[COMP_CWORD]}")
        print(f"    COMPREPLY=( $(compgen -W {shlex.quote(names)} -- \"$cur\") )")
        print("}")
        print("complete -F _ret_complete ret")
    elif shell == "zsh":
        print("#compdef ret")
        print("_arguments '1:command:((" + names + "))'")
    elif shell == "fish":
        for name in sub.choices:
            print(f"complete -c ret -f -n '__fish_use_subcommand' -a {shlex.quote(name)}")
    else:
        raise ValueError(f"unsupported completion shell: {shell}")

