"""The command-line grammar for Reticuli.

This module contains no command implementations.  It is the single inventory
of command names, arguments, help, and shell completion used by the surface
layer.  Keeping that inventory here means that ``ret help``, completion, and
programmatic callers all see the same grammar.
"""
from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable
from typing import Any


PORCELAIN = (
    "init",
    "run",
    "status",
    "pack",
    "pull",
    "export",
    "import",
    "verify",
    "audit",
    "assess",
    "rebuild",
    "crosscheck",
    "record",
    "sign",
)

# Command aliases belong here (alias -> canonical command), rather than in a
# dispatcher.  There currently are no verb aliases: the old v1 action names
# were deliberately retired.  Older *option* spellings are registered on the
# commands below where retaining one is harmless.
ALIASES: dict[str, str] = {}

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

_EPILOG = """See 'ret <command> -h' for command usage.
See 'ret help <command>' for detailed help; 'ret help -a' lists everything,
including accepted older spellings."""

_FULL_HELP: dict[str, str] = {
    "init": "Initialize a workspace. Unless --no-agent is used, init also wires the supported coding-agent hooks.",
    "run": "Run a shell command in an initialized workspace and append it to the authoring trace.",
    "status": "Show claim lifecycle state. --tree, --claims, --files, and --deps select structural views.",
    "pack": "Turn a project and its declared criteria into a content-addressed claim.",
    "pull": "Materialize another claim and its component closure as a dependency.",
    "export": "Write a deterministic portable archive. --blind omits generated implementation bytes.",
    "import": "Restore an archive and verify the imported claim identity before accepting it.",
    "verify": "Recompute sealed identity only. This command does not execute acceptance gates.",
    "audit": "Re-run acceptance gates cold and sandboxed; deep auditing includes composed claims.",
    "assess": "Measure available evidence such as deterministic mutation strength without changing identity.",
    "rebuild": "Regrow generated outputs from pinned criteria, then run gates and seal the result.",
    "crosscheck": "Compare origin, transfer, and independent-rebuild legs using the three-machine predicate.",
    "record": "Write a portable execution record; optionally sign it or check an existing record signature.",
    "sign": "Authorize the current claim/proof ceremony with an explicitly selected human key.",
    "hook": "Receive one coding-agent hook event on standard input.",
    "completion": "Generate shell completion directly from this command grammar.",
    "help": "Show detailed command help, or use -a to show every topic.",
}


def _add_verbose_json(command: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Add the output options shared by ordinary porcelain commands."""

    command.add_argument("-v", "--verbose", action="store_true",
                         help="show supporting details")
    command.add_argument("--json", action="store_true",
                         help="emit one machine-readable JSON result")
    command.add_argument("--color", "--colour", choices=("auto", "always", "never"),
                         default="auto", help="control ANSI colour output")
    return command


def _aliases_for(command: str) -> list[str]:
    return [alias for alias, target in ALIASES.items() if target == command]


def _add_claim(command: argparse.ArgumentParser, *, nargs: str | None = "?",
               default: str | None = ".") -> None:
    options: dict[str, Any] = {"help": "claim or workspace directory"}
    if nargs is not None:
        options["nargs"] = nargs
    if default is not None:
        options["default"] = default
    command.add_argument("claim", **options)


def _parser() -> tuple[argparse.ArgumentParser, dict[str, argparse.ArgumentParser]]:
    """Construct and return ``(parser, command_parsers)``.

    A fresh parser is returned on every call so embedders may adjust an
    instance without changing later help or completion output.
    """

    parser = argparse.ArgumentParser(
        prog="ret",
        description=_DESC,
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subcommands = parser.add_subparsers(dest="verb", metavar="<command>",
                                        required=True)
    commands: dict[str, argparse.ArgumentParser] = {}

    def add(name: str, summary: str, *, output: bool = True) -> argparse.ArgumentParser:
        command = subcommands.add_parser(
            name,
            aliases=_aliases_for(name),
            help=summary,
            description=_FULL_HELP[name],
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        command.set_defaults(command=name)
        if output:
            _add_verbose_json(command)
        commands[name] = command
        for alias in _aliases_for(name):
            commands[alias] = command
        return command

    command = add("init", "initialize a workspace")
    command.add_argument("path", nargs="?", default=".", help="workspace directory")
    command.add_argument("--no-agent", action="store_true",
                         help="do not install coding-agent hooks")

    command = add("run", "run and observe a command", output=False)
    command.add_argument("-C", "--directory", default=".", metavar="PATH",
                         help="workspace directory")
    command.add_argument("argv", nargs=argparse.REMAINDER, metavar="COMMAND",
                         help="shell command to run")

    command = add("status", "show work, claims, and unresolved inputs")
    command.add_argument("paths", nargs="*", default=["."], metavar="PATH")
    view = command.add_mutually_exclusive_group()
    view.add_argument("--tree", action="store_true", help="show component hierarchy")
    view.add_argument("--claims", action="store_true", help="list registered claims")
    view.add_argument("--files", action="store_true", help="show declared file roles")
    view.add_argument("--deps", action="store_true", help="show dependency edges")

    command = add("pack", "create a claim from a project")
    command.add_argument("project", nargs="?", default=".")
    command.add_argument("--name", help="claim name")
    command.add_argument("--generated", "--produce", action="append", default=[],
                         metavar="PATH", help="generated path or pattern (repeatable)")
    command.add_argument("--input", "--seed", action="append", default=[],
                         metavar="PATH", help="pinned input path or pattern (repeatable)")
    command.add_argument("--gate", help="acceptance command")
    command.add_argument("--gate-output", metavar="PATH", help="gate verdict file")
    command.add_argument("--into", metavar="PATH", help="claim destination")
    command.add_argument("--format", dest="claim_format", type=int, default=3)
    command.add_argument("--inputs-manifest", metavar="PATH")
    command.add_argument("--environment", metavar="PATH")
    command.add_argument("--require", action="append", default=[], metavar="TOOL")
    command.add_argument("--mutation-floor", type=float)
    command.add_argument("--accept", action="store_true",
                         help="accept an observed authoring session")

    command = add("pull", "add another claim as a dependency")
    command.add_argument("claim", help="claim to add")
    command.add_argument("workspace", nargs="?", default=".")

    command = add("export", "write a portable claim archive")
    _add_claim(command)
    command.add_argument("archive", help="archive path")
    command.add_argument("--blind", action="store_true",
                         help="omit generated implementation bytes")

    command = add("import", "restore a claim archive")
    command.add_argument("archive", help="archive path")
    command.add_argument("into", nargs="?", default=".", help="destination directory")

    command = add("verify", "verify claim identity")
    _add_claim(command)

    command = add("audit", "rerun acceptance criteria")
    _add_claim(command)
    command.add_argument("--shallow", action="store_true",
                         help="do not recursively audit components")

    command = add("assess", "measure specification strength")
    _add_claim(command)
    command.add_argument("--mutants", type=int, default=100,
                         help="maximum deterministic mutants")
    command.add_argument("--heldout", metavar="COMMAND",
                         help="verifier-supplied held-out check")

    command = add("rebuild", "rebuild an implementation from a claim")
    _add_claim(command)
    command.add_argument("--producer", required=True, metavar="COMMAND")
    command.add_argument("--into", required=True, metavar="PATH")
    command.add_argument("--produce-from", metavar="PATH")
    command.add_argument("--input-from", "--seed-from", metavar="PATH")
    command.add_argument("--without-guidance", "--no-request",
                         dest="guidance", action="store_false", default=True)

    command = add("crosscheck", "compare independent realizations")
    command.add_argument("m1", metavar="M1")
    command.add_argument("m2", metavar="M2")
    command.add_argument("m3", metavar="M3")
    command.add_argument("--tolerance", type=float)
    command.add_argument("--mutants", type=int)
    command.add_argument("--record-proof", action="store_true",
                         help="attach a passing proof to M1")
    command.add_argument("--shallow", action="store_true")

    command = add("record", "write an execution record")
    _add_claim(command)
    command.add_argument("path", nargs="?", help="record output path")
    command.add_argument("--key", metavar="PRIVATE_KEY",
                         help="sign the resulting record or attestation")
    command.add_argument("--as", dest="identity", metavar="IDENTITY",
                         help="signer identity")
    command.add_argument("--check", action="store_true",
                         help="check an existing record or attestation")
    command.add_argument("--signers", metavar="ALLOWED_SIGNERS")

    command = add("sign", "authorize a claim or proof")
    _add_claim(command)
    command.add_argument("--key", required=True, metavar="PRIVATE_KEY")
    command.add_argument("--as", dest="identity", required=True,
                         metavar="IDENTITY")
    command.add_argument("--signers", metavar="ALLOWED_SIGNERS")

    command = add("hook", "receive a coding-agent hook event", output=False)
    command.add_argument("event", nargs="?", help=argparse.SUPPRESS)

    command = add("help", "show detailed command help", output=False)
    command.add_argument("topic", nargs="?", choices=PORCELAIN + ("hook", "completion"))
    command.add_argument("-a", "--all", action="store_true",
                         help="show all command topics")

    command = add("completion", "generate shell completion", output=False)
    command.add_argument("shell", choices=("bash", "zsh", "fish"))

    return parser, commands


def verbs() -> tuple[str, ...]:
    """Return every command token accepted by the root parser.

    The result is read from argparse's subparser action instead of duplicating
    the list, which keeps completion and parser registration in lockstep.
    """

    parser, _ = _parser()
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return tuple(action.choices)
    return ()


def _topic_name(topic: Any) -> str | None:
    if isinstance(topic, argparse.Namespace):
        return getattr(topic, "topic", None)
    if topic is None or isinstance(topic, str):
        return topic
    return str(topic)


def _help_topic(topic: Any = None) -> int:
    """Print detailed help for one topic; return a command-style status."""

    name = _topic_name(topic)
    parser, commands = _parser()
    if not name:
        parser.print_help()
        return 0
    target = ALIASES.get(name, name)
    command = commands.get(target)
    if command is None:
        print(f"ret: help: unknown command {name!r}", file=sys.stderr)
        return 2
    command.print_help()
    detail = _FULL_HELP.get(target)
    if detail and detail != command.description:
        print("\n" + detail)
    return 0


def _help_all(_args: Any = None) -> int:
    """Print root help followed by every porcelain and plumbing topic."""

    parser, commands = _parser()
    parser.print_help()
    for name in PORCELAIN + ("hook", "completion", "help"):
        print("\n" + "=" * 78)
        commands[name].print_help()
    if ALIASES:
        print("\nAccepted command aliases:")
        for alias in sorted(ALIASES):
            print(f"  {alias} -> {ALIASES[alias]}")
    return 0


def _completion(shell: Any = "bash") -> int:
    """Write completion source for *shell*, generated from :func:`verbs`."""

    if isinstance(shell, argparse.Namespace):
        shell = getattr(shell, "shell", "bash")
    shell = str(shell)
    words = " ".join(verbs())
    if shell == "bash":
        print("_reticuli_complete() {")
        print("    local cur=${COMP_WORDS[COMP_CWORD]}")
        print(f'    COMPREPLY=( $(compgen -W "{words}" -- "$cur") )')
        print("}")
        print("complete -F _reticuli_complete ret")
    elif shell == "zsh":
        print("#compdef ret")
        print(f"_arguments '1:command:({words})' '*::argument:->args'")
    elif shell == "fish":
        for word in verbs():
            canonical = ALIASES.get(word, word)
            description = _FULL_HELP.get(canonical, "")
            print(f"complete -c ret -n '__fish_use_subcommand' -a {word!r} -d {description!r}")
    else:
        raise ValueError(f"unsupported completion shell: {shell}")
    return 0


__all__ = [
    "ALIASES", "PORCELAIN", "_DESC", "_EPILOG", "_FULL_HELP",
    "_add_verbose_json", "_completion", "_help_all", "_help_topic",
    "_parser", "verbs",
]
