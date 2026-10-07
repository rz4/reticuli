"""reticuli._cli.parser: the argv grammar.

The parser registers exactly the fourteen porcelain verbs (`PORCELAIN`),
whatever folded aliases are still accepted (`ALIASES` -- currently empty:
every v1 verb spelling that once worked has been retired outright rather
than kept as a working alias; see `_RETIRED_FOLD` for where each one
went), and the plumbing (`hook`, `help`, `completion`). `verbs()` reads
the names back off the built parser's own subparsers, so it and the help
text and the completion script can never drift from the grammar actually
registered here.

`_parser()` builds the top-level `argparse.ArgumentParser` and its
subparsers action; `verbs()` is every name they answer to. `_help_topic`
and `_help_all` back the `help` verb; `_completion` prints a shell
completion script. `_add_verbose_json` is the `-v/--verbose`, `--json`,
`--color` trio every porcelain verb shares.

Stdlib only.
"""
import argparse
import sys

# ---- the grammar itself ------------------------------------------------------

PORCELAIN = (
    "init", "run", "status", "pack",
    "pull", "export", "import",
    "verify", "audit", "assess",
    "rebuild", "crosscheck",
    "record", "sign",
)

# Folded aliases: an older spelling that still routes to a current verb.
# Empty today -- every v1 verb name either kept its spelling unchanged or
# was retired outright (`_RETIRED_FOLD`), so there is nothing left to
# alias. A dict, not a tuple, because an alias names the single verb it
# routes to.
ALIASES = {}

_VERB_HELP = {
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
    "hook": "report one coding-agent hook event (plumbing)",
    "help": "show detailed help for a command",
    "completion": "print a shell completion script",
}

# Where each retired v1 verb's behavior actually lives now -- the same
# foldings `checks/parser_check.py` documents inline. These names are
# never registered as subparsers or aliases; they only back `help`'s
# pointer to the replacement.
_RETIRED_FOLD = {
    "condense": "folded into: pack (what v1 called sealing is now pack --accept)",
    "seal": "folded into: pack --accept",
    "realize": "folded into: rebuild",
    "prove": "folded into: crosscheck",
    "mint": "folded into: sign",
    "records": "folded into: status --claims",
    "claims": "folded into: status --claims",
    "hydrate": "folded into: rebuild (component chains rebuild with it)",
    "inspect": "folded into: status",
    "hooks": "folded into: init (wires the agent)",
    "tree": "folded into: status --tree",
    "attest": "folded into: record --key --as / --check",
}

_DESC = 'Reticuli records and reproduces software claims.\n\nAuthoring\n    init        initialize a workspace\n    run         run and observe a command\n    status      show work, claims, and unresolved inputs\n    pack        create a claim from a project\n\nComposition and transport\n    pull        add another claim as a dependency\n    export      write a portable claim archive\n    import      restore a claim archive\n\nVerification\n    verify      verify claim identity\n    audit       rerun acceptance criteria\n    assess      measure specification strength\n\nReconstruction\n    rebuild     rebuild an implementation from a claim\n    crosscheck  compare independent realizations\n\nEvidence\n    record      write an execution record\n    sign        authorize a claim or proof'
_EPILOG = "See 'ret <command> -h' for command usage.\nSee 'ret help <command>' for detailed help; 'ret help -a' lists everything,\nincluding accepted older spellings."

_FULL_HELP = {
    "init": (
        "ret init [path] [--no-agent]\n\n"
        "    Mark a directory as a reticuli session: create the .reticuli\n"
        "    store and, unless --no-agent withholds it, wire the coding-agent\n"
        "    hooks into the project. Idempotent."
    ),
    "run": (
        "ret run <cmd> [--workspace path]\n\n"
        "    Run one command (a literal shell command, or a known producer\n"
        "    name) inside a workspace and return its exit code unchanged.\n"
        "    Appended to the session's draft trace when the workspace is\n"
        "    already a session."
    ),
    "status": (
        "ret status [path] [--tree] [--claims]\n\n"
        "    Show a claim's or session's state: name, root, phase, and the\n"
        "    next rung on the ladder. --tree shows its declared step\n"
        "    structure; --claims lists every sealed claim in the registry."
    ),
    "pack": (
        "ret pack [path] [--accept] [--name NAME] [--inputs-manifest FILE]\n\n"
        "    Create a claim from a project: write its recipe and pinned\n"
        "    inputs. --accept also computes the root and writes the\n"
        "    manifest (what v1 called sealing)."
    ),
    "pull": (
        "ret pull <component>\n\n"
        "    Add another claim as a dependency, materializing it under the\n"
        "    current claim's components."
    ),
    "export": (
        "ret export [path] [--out FILE]\n\n"
        "    Write a portable claim archive."
    ),
    "import": (
        "ret import <archive> [--into path]\n\n"
        "    Restore a claim archive into a directory."
    ),
    "verify": (
        "ret verify [path]\n\n"
        "    Recompute the root from the bytes present and compare it with\n"
        "    the sealed manifest. Identity only -- no gate is executed."
    ),
    "audit": (
        "ret audit [path]\n\n"
        "    Re-execute every gate, cold and sandboxed, composed claims\n"
        "    included. The only verb that re-earns a verdict."
    ),
    "assess": (
        "ret assess [path]\n\n"
        "    Measure specification strength: mutation kill rate and which\n"
        "    files decide each gate."
    ),
    "rebuild": (
        "ret rebuild [path] --producer NAME [--into DIR] [--without-guidance]\n\n"
        "    Regrow the generated outputs until the gates pass; the ledger\n"
        "    records what it cost. --without-guidance withholds every\n"
        "    producer hint, so a pass measures what the criteria alone\n"
        "    carry."
    ),
    "crosscheck": (
        "ret crosscheck --m1 LEG --m2 LEG --m3 LEG\n\n"
        "    The three-machine test: compare independent realizations. A\n"
        "    leg is a claim directory or a record file."
    ),
    "record": (
        "ret record [path] [--key KEY] [--as STATEMENT] [--check]\n\n"
        "    Write an execution record, or (--check) verify one already\n"
        "    written."
    ),
    "sign": (
        "ret sign [path] [--key KEY]\n\n"
        "    A human signs the root. Never an agent's act."
    ),
    "hook": (
        "ret hook <event>\n\n"
        "    Plumbing: record one coding-agent hook event into the\n"
        "    session's draft trace. Not meant to be typed by hand."
    ),
    "help": (
        "ret help [command] [-a/--all]\n\n"
        "    Show detailed help for one command, or (-a) list every\n"
        "    command this parser knows, including retired spellings and\n"
        "    where they went."
    ),
    "completion": (
        "ret completion [bash|zsh]\n\n"
        "    Print a shell completion script for the named shell\n"
        "    (default: bash)."
    ),
}


def _add_verbose_json(parser: argparse.ArgumentParser) -> None:
    """The `-v/--verbose`, `--json`, `--color` trio every porcelain verb
    shares -- the flags `reticuli._cli.output._finish` reads back off
    `args`."""
    parser.add_argument("-v", "--verbose", action="store_true",
                         help="show every field a result carries, not just the summary")
    parser.add_argument("--json", action="store_true",
                         help="print the result as a single JSON envelope")
    parser.add_argument("--color", choices=("auto", "always", "never"), default="auto",
                         help="colorize human-readable output (default: auto)")


def _parser():
    """The top-level parser and its subparsers action. Every porcelain
    verb, its folded aliases (if any), and the plumbing (`hook`, `help`,
    `completion`) are registered here -- the one place the grammar is
    assembled, so `verbs()` and `_completion` can read it back rather
    than repeating it."""
    p = argparse.ArgumentParser(
        prog="ret",
        description=_DESC,
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="verb", metavar="<command>")

    for verb in PORCELAIN:
        verb_aliases = sorted(a for a, canon in ALIASES.items() if canon == verb)
        sp = sub.add_parser(verb, aliases=verb_aliases, help=_VERB_HELP[verb])
        _add_verbose_json(sp)

        if verb == "init":
            sp.add_argument("path", nargs="?", default=".")
            sp.add_argument("--no-agent", action="store_true", dest="no_agent")
        elif verb == "run":
            sp.add_argument("cmd")
            sp.add_argument("--workspace", "-C", default=".")
        elif verb == "status":
            sp.add_argument("path", nargs="?", default=".")
            sp.add_argument("--tree", action="store_true")
            sp.add_argument("--claims", action="store_true")
        elif verb == "pack":
            sp.add_argument("path", nargs="?", default=".")
            sp.add_argument("--accept", action="store_true")
            sp.add_argument("--name", default=None)
            sp.add_argument("--inputs-manifest", dest="inputs_manifest", default=None)
        elif verb == "pull":
            sp.add_argument("component")
        elif verb == "export":
            sp.add_argument("path", nargs="?", default=".")
            sp.add_argument("--out", default=None)
        elif verb == "import":
            sp.add_argument("archive")
            sp.add_argument("--into", default=".")
        elif verb in ("verify", "audit", "assess"):
            sp.add_argument("path", nargs="?", default=".")
        elif verb == "rebuild":
            sp.add_argument("path", nargs="?", default=".")
            sp.add_argument("--producer", default=None)
            sp.add_argument("--into", default=None)
            sp.add_argument("--without-guidance", action="store_true", dest="without_guidance")
        elif verb == "crosscheck":
            sp.add_argument("--m1", required=True)
            sp.add_argument("--m2", required=True)
            sp.add_argument("--m3", required=True)
        elif verb == "record":
            sp.add_argument("path", nargs="?", default=".")
            sp.add_argument("--key", default=None)
            sp.add_argument("--as", dest="as_", default=None)
            sp.add_argument("--check", action="store_true")
        elif verb == "sign":
            sp.add_argument("path", nargs="?", default=".")
            sp.add_argument("--key", default=None)

    hook_sp = sub.add_parser("hook", help=_VERB_HELP["hook"])
    hook_sp.add_argument("event")
    _add_verbose_json(hook_sp)

    help_sp = sub.add_parser("help", help=_VERB_HELP["help"])
    help_sp.add_argument("topic", nargs="?", default=None)
    help_sp.add_argument("-a", "--all", action="store_true", dest="all")

    completion_sp = sub.add_parser("completion", help=_VERB_HELP["completion"])
    completion_sp.add_argument("shell", nargs="?", default="bash", choices=("bash", "zsh"))

    return p, sub


def verbs():
    """Every name the parser answers to: the porcelain verbs, their
    folded aliases, and the plumbing -- read off the subparsers actually
    registered by `_parser()`, so this can never drift from the grammar."""
    _, sub = _parser()
    return tuple(sorted(sub.choices.keys()))


# ---- help: the `help` verb's two forms --------------------------------------

def _help_topic(name: str) -> None:
    """`ret help <name>`: the full help text for one command, or -- for
    a retired v1 spelling -- where its behavior went, or a plain refusal
    for a name this parser has never heard of."""
    text = _FULL_HELP.get(name)
    if text is not None:
        print(text)
        return
    retired = _RETIRED_FOLD.get(name)
    if retired is not None:
        print(f"ret: {name}: retired; {retired}")
        return
    print(f"ret: unknown command {name!r}; see 'ret help -a'", file=sys.stderr)


def _help_all() -> None:
    """`ret help -a`: one line per command this parser knows, followed by
    the retired v1 spellings and where each one folded to."""
    for verb in verbs():
        print(f"{verb:<12} {_VERB_HELP.get(verb, '')}")
    print()
    print("retired (no longer accepted):")
    for name in sorted(_RETIRED_FOLD):
        print(f"  {name:<10} {_RETIRED_FOLD[name]}")


# ---- completion --------------------------------------------------------------

def _completion(shell: str = "bash") -> None:
    """A shell completion script covering every verb this parser
    registers -- generated from `verbs()`, so it cannot drift from the
    grammar."""
    names = " ".join(verbs())
    if shell == "zsh":
        print(
            "#compdef ret\n"
            f"_ret() {{ compadd {names}; }}\n"
            "compdef _ret ret\n"
        )
        return
    print(
        "_ret_complete() {\n"
        "    local cur\n"
        '    cur="${COMP_WORDS[COMP_CWORD]}"\n'
        f'    COMPREPLY=( $(compgen -W "{names}" -- "$cur") )\n'
        "}\n"
        "complete -F _ret_complete ret"
    )
