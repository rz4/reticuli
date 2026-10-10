"""The argv grammar: the fourteen porcelain verbs, the folded aliases
(older accepted spellings of a still-live verb), and the plumbing
(`hook`, `help`, `completion`). `verbs()` and shell completion are both
read off the same built parser, so neither can drift from the other or
from `-h`.
"""
import argparse
import sys

PORCELAIN = (
    "init", "run", "status", "pack",
    "pull", "export", "import",
    "verify", "audit", "assess",
    "rebuild", "crosscheck",
    "record", "sign",
)

PLUMBING = ("hook", "help", "completion")

# Older spellings still accepted for a live porcelain verb, e.g.
# {"old-name": "canonical-name"}. Empty until a spelling is retired
# into this table rather than dropped outright.
ALIASES = {}

_SHORT_HELP = {
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
    "record": "write an execution record",
    "sign": "authorize a claim or proof",
    "hook": "internal: the coding-agent hook entry point",
    "help": "show detailed help for a command",
    "completion": "print a shell completion script",
}

_FULL_HELP = {
    name: f"ret {name} -- {text}" for name, text in _SHORT_HELP.items()
}

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


def _add_verbose_json(sp: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """The two flags every porcelain verb shares: `--json` (the
    machine-readable envelope) and `-v/--verbose` (extra diagnostic
    detail on top of the one-line human report)."""
    sp.add_argument("--json", action="store_true", help="emit a single JSON envelope on stdout")
    sp.add_argument("-v", "--verbose", action="store_true", help="include extra diagnostic detail")
    return sp


def _parser():
    """Build the top-level parser and its subparsers action. Returns
    `(parser, subparsers_action)`; every other function in this module
    reads the grammar back off the action rather than keeping a second
    copy of the verb list."""
    p = argparse.ArgumentParser(
        prog="ret",
        description=_DESC,
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="verb", metavar="<command>")
    for name in PORCELAIN + PLUMBING:
        aliases = sorted(old for old, canonical in ALIASES.items() if canonical == name)
        sp = sub.add_parser(name, aliases=aliases, help=_SHORT_HELP.get(name, ""))
        if name in PORCELAIN:
            _add_verbose_json(sp)
    return p, sub


def verbs():
    """Every name the parser answers to: the porcelain verbs, their
    folded aliases, and the plumbing -- read straight off the built
    grammar, so this can never drift from what `-h` actually shows."""
    _, sub = _parser()
    return list(sub.choices.keys())


def _help_topic(name: str) -> int:
    """`ret help <name>`: the detailed help for one verb or alias,
    resolving an alias to its canonical entry first."""
    canonical = ALIASES.get(name, name)
    text = _FULL_HELP.get(canonical)
    if text is None:
        print(f"ret: help: no such command: {name}", file=sys.stderr)
        return 1
    print(text)
    return 0


def _help_all() -> int:
    """`ret help -a`: every porcelain verb and plumbing command, plus
    every accepted older spelling, each resolved to its full help."""
    for name in PORCELAIN + PLUMBING:
        print(_FULL_HELP[name])
    for old, canonical in sorted(ALIASES.items()):
        print(f"ret {old} -- older spelling of '{canonical}'")
    return 0


def _completion(shell: str) -> int:
    """Print a completion script for `shell` to stdout, generated from
    `verbs()` so the completions can never list a verb that is not
    actually registered."""
    names = " ".join(sorted(verbs()))
    if shell == "bash":
        print(f"""_ret_complete() {{
    local cur
    cur="${{COMP_WORDS[COMP_CWORD]}}"
    COMPREPLY=($(compgen -W "{names}" -- "$cur"))
}}
complete -F _ret_complete ret""")
        return 0
    print(f"ret: completion: unsupported shell: {shell}", file=sys.stderr)
    return 1
