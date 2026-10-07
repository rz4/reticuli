"""Argument grammar and help for the ``ret`` command line."""

from __future__ import annotations

import argparse


_DESC = ("Reticuli records and reproduces software claims.\n\nAuthoring\n"
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

# Small, unambiguous spellings that resolve to an existing porcelain command.
ALIASES = {"ls": "status", "check": "verify"}

_FULL_HELP = {
    "init": "Initialize a workspace and optionally wire its agent hooks.",
    "run": "Run a command and record it in the workspace trace.",
    "status": "Show a workspace, its claims, or its dependency tree.",
    "pack": "Make and optionally accept a claim from a project.",
    "pull": "Add a sealed claim as a workspace dependency.",
    "export": "Write a portable archive of a claim.",
    "import": "Restore a claim from a portable archive.",
    "verify": "Compare present pinned bytes with the sealed identity.",
    "audit": "Rerun the acceptance criteria to earn the verdict.",
    "assess": "Measure the gates with deterministic mutations.",
    "rebuild": "Regrow generated outputs from pinned inputs.",
    "crosscheck": "Compare an original, a transfer, and an independent rebuild.",
    "record": "Write or check a signed execution record.",
    "sign": "Authorize a claim or check its authorization.",
    "hook": "Receive an agent hook event from standard input.",
    "help": "Show command help, or all command help with -a.",
    "completion": "Generate shell completion from this command grammar.",
}


def _add_verbose_json(command: argparse.ArgumentParser) -> None:
    command.add_argument("-v", "--verbose", action="store_true", help="show details")
    command.add_argument("--json", action="store_true", help="print a JSON result")


def _parser() -> tuple[argparse.ArgumentParser, argparse._SubParsersAction]:
    top = argparse.ArgumentParser(
        prog="ret", description=_DESC, epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    _add_verbose_json(top)
    commands = top.add_subparsers(dest="verb", metavar="command", required=True)

    def add(name: str) -> argparse.ArgumentParser:
        command = commands.add_parser(
            name, help=_FULL_HELP[name], description=_FULL_HELP[name],
            allow_abbrev=False,
        )
        _add_verbose_json(command)
        return command

    init = add("init")
    init.add_argument("directory", nargs="?", default=".")
    init.add_argument("--no-agent", action="store_true")

    run = add("run")
    run.add_argument("command")
    run.add_argument("--directory", default=".")

    status = add("status")
    status.add_argument("directory", nargs="?", default=".")
    status.add_argument("--tree", action="store_true")
    status.add_argument("--claims", action="store_true")

    pack = add("pack")
    pack.add_argument("root", nargs="?", default=".")
    pack.add_argument("--name")
    pack.add_argument("--generated", action="append", default=[])
    pack.add_argument("--input", dest="inputs", action="append", default=[])
    pack.add_argument("--gate")
    pack.add_argument("--gate-output")
    pack.add_argument("--inputs-manifest")
    pack.add_argument("--environment")
    pack.add_argument("--accept", action="store_true")

    pull = add("pull")
    pull.add_argument("claim")
    pull.add_argument("--workspace", default=".")

    export = add("export")
    export.add_argument("claim")
    export.add_argument("archive")
    export.add_argument("--blind", action="store_true")

    import_ = add("import")
    import_.add_argument("archive")
    import_.add_argument("into")

    for name in ("verify", "audit", "assess"):
        command = add(name)
        command.add_argument("claim", nargs="?", default=".")
        if name == "audit":
            command.add_argument("--shallow", action="store_true")
        elif name == "assess":
            command.add_argument("--mutants", type=int, default=100)

    rebuild = add("rebuild")
    rebuild.add_argument("claim")
    rebuild.add_argument("producer")
    rebuild.add_argument("into")
    rebuild.add_argument("--without-guidance", action="store_true")
    rebuild.add_argument("--reuse", action="store_true")

    crosscheck = add("crosscheck")
    for machine in ("m1", "m2", "m3"):
        crosscheck.add_argument(machine)
    crosscheck.add_argument("--mutants", type=int)
    crosscheck.add_argument("--tolerance", type=float)
    crosscheck.add_argument("--record-proof", action="store_true")

    record = add("record")
    record.add_argument("claim", nargs="?", default=".")
    record.add_argument("--output")
    record.add_argument("--key")
    record.add_argument("--as", dest="identity")
    record.add_argument("--check", action="store_true")

    sign = add("sign")
    sign.add_argument("claim", nargs="?", default=".")
    sign.add_argument("--key")
    sign.add_argument("--as", dest="identity")
    sign.add_argument("--check", action="store_true")

    hook = add("hook")
    help_ = add("help")
    help_.add_argument("topic", nargs="?")
    help_.add_argument("-a", "--all", action="store_true")
    completion = add("completion")
    completion.add_argument("shell", choices=("bash", "zsh", "fish"), nargs="?", default="bash")

    for alias, canonical in ALIASES.items():
        command = commands.add_parser(alias, help=f"alias for {canonical}", allow_abbrev=False)
        _add_verbose_json(command)
        if canonical == "status":
            command.add_argument("directory", nargs="?", default=".")
            command.add_argument("--tree", action="store_true")
            command.add_argument("--claims", action="store_true")
        elif canonical == "verify":
            command.add_argument("claim", nargs="?", default=".")
        command.set_defaults(canonical=canonical)

    return top, commands


def verbs() -> tuple[str, ...]:
    """Return all accepted top-level commands, including aliases."""
    return (*PORCELAIN, *ALIASES, "hook", "help", "completion")


def _help_topic(topic: str) -> None:
    parser, commands = _parser()
    if topic in ALIASES:
        topic = ALIASES[topic]
    for action in commands._choices_actions:
        if action.dest == topic:
            commands.choices[topic].print_help()
            return
    parser.error(f"unknown help topic: {topic}")


def _help_all() -> None:
    parser, commands = _parser()
    print(parser.format_help(), end="")
    for name in verbs():
        print(commands.choices[name].format_help(), end="")


def _completion(shell: str = "bash") -> None:
    """Print completion candidates derived from the parser's registered verbs."""
    _, commands = _parser()
    names = " ".join(commands.choices)
    if shell == "bash":
        print(f'_ret_complete() {{ COMPREPLY=( $(compgen -W "{names}" -- "${{COMP_WORDS[COMP_CWORD]}}") ); }}')
        print("complete -F _ret_complete ret")
    elif shell == "zsh":
        print(f"#compdef ret\n_arguments '1:command:({names})'")
    elif shell == "fish":
        for name in commands.choices:
            print(f"complete -c ret -f -a {name}")
    else:
        raise ValueError(f"unsupported shell: {shell}")
