"""Argument grammar and help for the ``ret`` command line.

The grammar is kept here so command discovery, help, and completion use the
same set of names.  Execution of a parsed command belongs to the CLI layer.
"""

from __future__ import annotations

import argparse


_DESC = ('Reticuli records and reproduces software claims.\n\n'
         'Authoring\n'
         '    init        initialize a workspace\n'
         '    run         run and observe a command\n'
         '    status      show work, claims, and unresolved inputs\n'
         '    pack        create a claim from a project\n\n'
         'Composition and transport\n'
         '    pull        add another claim as a dependency\n'
         '    export      write a portable claim archive\n'
         '    import      restore a claim archive\n\n'
         'Verification\n'
         '    verify      verify claim identity\n'
         '    audit       rerun acceptance criteria\n'
         '    assess      measure specification strength\n\n'
         'Reconstruction\n'
         '    rebuild     rebuild an implementation from a claim\n'
         '    crosscheck  compare independent realizations\n\n'
         'Evidence\n'
         '    record      write an execution record\n'
         '    sign        authorize a claim or proof')

_EPILOG = ("See 'ret <command> -h' for command usage.\n"
           "See 'ret help <command>' for detailed help; 'ret help -a' lists everything,\n"
           "including accepted older spellings.")

PORCELAIN = (
    "init", "run", "status", "pack", "pull", "export", "import",
    "verify", "audit", "assess", "rebuild", "crosscheck", "record", "sign",
)

# These are command-line conveniences, not additional operations.  Retired
# first-generation verbs deliberately have no entries here.
ALIASES = {"ls": "status", "check": "verify"}

_FULL_HELP = {
    "init": "Initialize a workspace and connect the agent hooks.",
    "run": "Run a shell command in a workspace and record its invocation.",
    "status": "Show the current claim, workspace files, or claim structure.",
    "pack": "Create and optionally accept a claim from project files.",
    "pull": "Add an existing claim as a dependency.",
    "export": "Write a portable claim archive.",
    "import": "Restore a claim archive.",
    "verify": "Compare current pinned bytes with the sealed claim identity.",
    "audit": "Rerun the acceptance gates and earn a fresh verdict.",
    "assess": "Measure the strength of a claim's acceptance criteria.",
    "rebuild": "Regenerate outputs using a producer and the claim's criteria.",
    "crosscheck": "Compare the origin, transfer, and independent rebuild.",
    "record": "Write or check a signed execution record.",
    "sign": "Authorize a claim or proof with a signing key.",
    "hook": "Agent hook plumbing.",
    "help": "Show command help.",
    "completion": "Print shell completion generated from the command grammar.",
}


def _add_verbose_json(command):
    """Add the output switches shared by user-facing commands."""
    command.add_argument("-v", "--verbose", action="store_true",
                         help="include detailed result information")
    command.add_argument("--json", action="store_true",
                         help="print one machine-readable JSON result")
    return command


def _parser():
    """Build the parser and return it with a name-to-subparser map."""
    parser = argparse.ArgumentParser(
        prog="ret", description=_DESC, epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", metavar="command")
    commands = {}

    def add(name, *, aliases=()):
        command = sub.add_parser(name, aliases=list(aliases),
                                 help=_FULL_HELP[name],
                                 description=_FULL_HELP[name])
        commands[name] = command
        for alias in aliases:
            commands[alias] = command
        if name not in ("help", "completion", "hook"):
            _add_verbose_json(command)
        return command

    def path(command, name="directory", *, default="."):
        command.add_argument(name, nargs="?", default=default)

    c = add("init")
    path(c, "workspace")
    c.add_argument("--no-agent", action="store_true")

    c = add("run")
    c.add_argument("cmd", nargs="+", help="command to run")
    c.add_argument("-C", "--workspace", default=".")

    c = add("status", aliases=("ls",))
    path(c)
    c.add_argument("--tree", action="store_true")
    c.add_argument("--claims", action="store_true")
    c.add_argument("--files", action="store_true")
    c.add_argument("--deps", action="store_true")

    c = add("pack")
    path(c, "project")
    c.add_argument("--name")
    c.add_argument("--generated", action="append", default=[])
    c.add_argument("--inputs", action="append", default=[])
    c.add_argument("--inputs-manifest")
    c.add_argument("--accept", action="store_true")

    c = add("pull")
    c.add_argument("claim")
    path(c, "into")

    c = add("export")
    c.add_argument("directory")
    c.add_argument("archive")

    c = add("import")
    c.add_argument("archive")
    path(c, "into")

    c = add("verify", aliases=("check",))
    path(c)

    c = add("audit")
    path(c)
    c.add_argument("--shallow", action="store_true")

    c = add("assess")
    path(c)

    c = add("rebuild")
    c.add_argument("directory")
    c.add_argument("--producer", required=True)
    c.add_argument("--into")
    c.add_argument("--without-guidance", action="store_true")

    c = add("crosscheck")
    c.add_argument("origin")
    c.add_argument("transfer")
    c.add_argument("rebuild")

    c = add("record")
    path(c)
    c.add_argument("--key")
    c.add_argument("--as", dest="as_name")
    c.add_argument("--check", action="store_true")

    c = add("sign")
    path(c)
    c.add_argument("--key")
    c.add_argument("--check", action="store_true")

    c = add("hook")
    c.add_argument("event", nargs="?")
    c.add_argument("args", nargs="*")

    c = add("help")
    c.add_argument("topic", nargs="?")
    c.add_argument("-a", "--all", action="store_true")

    c = add("completion")
    c.add_argument("shell", choices=("bash", "zsh", "fish"), nargs="?",
                   default="bash")
    return parser, commands


def verbs():
    """Return all accepted top-level command spellings."""
    return tuple(PORCELAIN) + tuple(ALIASES) + ("hook", "help", "completion")


def _help_topic(topic):
    """Print help for a command or alias."""
    parser, commands = _parser()
    if topic is None:
        parser.print_help()
        return
    command = commands.get(topic)
    if command is None:
        parser.error(f"unknown help topic: {topic}")
    command.print_help()


def _help_all():
    """Print top-level help and detailed help for every accepted verb."""
    parser, commands = _parser()
    parser.print_help()
    for name in verbs():
        print()
        print(f"{name}: {_FULL_HELP.get(ALIASES.get(name, name), '')}")
        commands[name].print_help()


def _completion(shell="bash"):
    """Print a completion definition using the current parser's verbs."""
    names = " ".join(verbs())
    if shell == "bash":
        print(f'_ret_complete() {{ COMPREPLY=( $(compgen -W "{names}" -- "${{COMP_WORDS[COMP_CWORD]}}") ); }}')
        print("complete -F _ret_complete ret")
    elif shell == "zsh":
        print(f"#compdef ret\n_arguments '1:command:({names})'")
    elif shell == "fish":
        for name in verbs():
            print(f"complete -c ret -f -n '__fish_use_subcommand' -a {name}")
    else:
        raise ValueError(f"unsupported completion shell: {shell}")
