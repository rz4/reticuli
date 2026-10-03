"""The argv grammar: one `argparse.ArgumentParser` for every porcelain
verb, the plumbing beneath it, and the help/completion surfaces that are
generated from the same grammar so they cannot drift apart from it
(spec/layers.md, "surface").

Fourteen porcelain verbs, grouped exactly as `_DESC` lists them:
Authoring (`init`, `run`, `status`, `pack`), Composition and transport
(`pull`, `export`, `import`), Verification (`verify`, `audit`,
`assess`), Reconstruction (`rebuild`, `crosscheck`), Evidence (`record`,
`sign`). Beneath that: `hook`, the plumbing entry point the coding-agent
hooks installed by `init` call back into, and two meta verbs, `help` and
`completion`, that read the grammar rather than acting on a claim.

A 2026-09-22 retirement folded five v2 verbs into flags on a porcelain
verb rather than keeping them as separate commands: `seal` into `pack
--accept`, `hooks` into `init` (which always wires the agent unless
`--no-agent`), `tree` into `status --tree`, `claims` into `status
--claims`, and `attest` into `record --key --as` / `record --check`.
Those names, plus the v1 names they or their siblings replaced even
earlier (`condense`, `realize`, `prove`, `mint`, `records`, `hydrate`,
`inspect`), stay gone -- `verbs()` never produces them again.

`ALIASES` is the opposite direction: a short list of still-accepted
older spellings, each a plain alternate name for one porcelain verb
(registered as an `argparse` subparser alias, so they show up in
`verbs()` and in `ret help -a`, never in the main `-h` listing).

`_parser()` builds the grammar and returns `(parser, choices)`, where
`choices` is the subparsers action's own `name -> ArgumentParser`
mapping (porcelain names and aliases both as keys) -- the single source
`verbs()`, `_help_topic`, and `_completion` all read, so none of them
can disagree with what `-h` actually accepts.
"""
import argparse
import sys

# ===========================================================================
# The grammar's vocabulary.
# ===========================================================================

PORCELAIN = (
    "init", "run", "status", "pack",
    "pull", "export", "import",
    "verify", "audit", "assess",
    "rebuild", "crosscheck",
    "record", "sign",
)

# Accepted older spellings: a plain alternate name for a current
# porcelain verb, kept out of PORCELAIN and out of the main help
# listing, but still a working subcommand (`ret help -a` lists them).
ALIASES = {
    "build": "pack",
    "check": "verify",
}

_DESC = 'Reticuli records and reproduces software claims.\n\nAuthoring\n    init        initialize a workspace\n    run         run and observe a command\n    status      show work, claims, and unresolved inputs\n    pack        create a claim from a project\n\nComposition and transport\n    pull        add another claim as a dependency\n    export      write a portable claim archive\n    import      restore a claim archive\n\nVerification\n    verify      verify claim identity\n    audit       rerun acceptance criteria\n    assess      measure specification strength\n\nReconstruction\n    rebuild     rebuild an implementation from a claim\n    crosscheck  compare independent realizations\n\nEvidence\n    record      write an execution record\n    sign        authorize a claim or proof'

_EPILOG = "See 'ret <command> -h' for command usage.\nSee 'ret help <command>' for detailed help; 'ret help -a' lists everything,\nincluding accepted older spellings."

# Long-form help for `ret help <command>`, one entry per porcelain verb.
_FULL_HELP = {
    "init": (
        "ret init [workspace] [--no-agent]\n\n"
        "Mark a directory as a reticuli workspace: create its .reticuli\n"
        "store if missing, and -- unless --no-agent -- wire the coding-agent\n"
        "hooks into it. Idempotent: a second call is a no-op on the store."
    ),
    "run": (
        "ret run <cmd> [workspace]\n\n"
        "Run cmd as a shell command with workspace as its working directory\n"
        "and hand back the child's exit code unwrapped, so a session can\n"
        "chain it as a predicate."
    ),
    "status": (
        "ret status [workspace] [--tree] [--claims]\n\n"
        "Show work, claims, and unresolved inputs. --tree shows the retired\n"
        "`tree` verb's layout; --claims shows the retired `claims` verb's\n"
        "listing of sealed claim names."
    ),
    "pack": (
        "ret pack [workspace] [--accept]\n\n"
        "Create a claim from a project. --accept seals it immediately (the\n"
        "retired `seal` verb's behavior)."
    ),
    "pull": (
        "ret pull <source> [workspace]\n\n"
        "Add another claim as a dependency."
    ),
    "export": (
        "ret export [claim] [--out PATH]\n\n"
        "Write a portable claim archive."
    ),
    "import": (
        "ret import <archive> [workspace]\n\n"
        "Restore a claim archive."
    ),
    "verify": (
        "ret verify [claim]\n\n"
        "Verify claim identity."
    ),
    "audit": (
        "ret audit [claim]\n\n"
        "Rerun acceptance criteria."
    ),
    "assess": (
        "ret assess [claim]\n\n"
        "Measure specification strength."
    ),
    "rebuild": (
        "ret rebuild [claim] [--out PATH]\n\n"
        "Rebuild an implementation from a claim."
    ),
    "crosscheck": (
        "ret crosscheck [claim]\n\n"
        "Compare independent realizations."
    ),
    "record": (
        "ret record [claim] [--key KEY] [--as NAME] [--check]\n\n"
        "Write an execution record. --check verifies an existing record\n"
        "instead of writing one (the retired `attest` verb's behavior)."
    ),
    "sign": (
        "ret sign [claim] [--key KEY]\n\n"
        "Authorize a claim or proof."
    ),
}

# Help groups, in the order and wording _DESC already carries -- used
# only to keep the two in one place; the literal text users see is
# still _DESC itself, passed straight through to argparse.
_GROUPS = (
    ("Authoring", ("init", "run", "status", "pack")),
    ("Composition and transport", ("pull", "export", "import")),
    ("Verification", ("verify", "audit", "assess")),
    ("Reconstruction", ("rebuild", "crosscheck")),
    ("Evidence", ("record", "sign")),
)


# ===========================================================================
# The grammar itself.
# ===========================================================================


def _add_verbose_json(p):
    """Add the pair of output-shaping flags every verb's parser carries:
    `-v/--verbose` (extra progress detail on stderr) and `--json` (the
    five-field envelope instead of a colored summary line). Returns `p`.
    """
    p.add_argument("-v", "--verbose", action="store_true", help="show extra detail")
    p.add_argument("--json", action="store_true", help="emit a machine-readable JSON envelope")
    return p


def _aliases_for(name):
    """Alias names in `ALIASES` that point at porcelain verb `name`."""
    return sorted(k for k, v in ALIASES.items() if v == name)


def _parser():
    """Build the full argv grammar. Returns `(parser, choices)`:
    `parser` is the top-level `argparse.ArgumentParser`; `choices` is the
    subparsers action's own `name -> ArgumentParser` map, carrying both
    porcelain names and their aliases -- the one place `verbs()`,
    `_help_topic`, and `_completion` all read from.
    """
    p = argparse.ArgumentParser(
        prog="ret",
        description=_DESC,
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--version", action="store_true", help="show the version and exit")
    p.add_argument(
        "--color", choices=("auto", "always", "never"), default="auto",
        help="colorize terminal output",
    )
    _add_verbose_json(p)

    sub = p.add_subparsers(dest="verb", metavar="<command>")

    def porcelain(name, help_text):
        sp = sub.add_parser(name, help=help_text, aliases=_aliases_for(name))
        _add_verbose_json(sp)
        return sp

    sp = porcelain("init", "initialize a workspace")
    sp.add_argument("workspace", nargs="?", default=".")
    sp.add_argument("--no-agent", action="store_true", help="do not wire the coding-agent hooks")

    sp = porcelain("run", "run and observe a command")
    sp.add_argument("cmd", help="the shell command to run")
    sp.add_argument("workspace", nargs="?", default=".")

    sp = porcelain("status", "show work, claims, and unresolved inputs")
    sp.add_argument("workspace", nargs="?", default=".")
    sp.add_argument("--tree", action="store_true", help="show the claim's layout as a tree")
    sp.add_argument("--claims", action="store_true", help="list sealed claim names")

    sp = porcelain("pack", "create a claim from a project")
    sp.add_argument("workspace", nargs="?", default=".")
    sp.add_argument("--accept", action="store_true", help="seal the claim immediately")

    sp = porcelain("pull", "add another claim as a dependency")
    sp.add_argument("source", help="the claim to add as a dependency")
    sp.add_argument("workspace", nargs="?", default=".")

    sp = porcelain("export", "write a portable claim archive")
    sp.add_argument("claim", nargs="?", default=".")
    sp.add_argument("--out", metavar="PATH", help="archive path (default: alongside the claim)")

    sp = porcelain("import", "restore a claim archive")
    sp.add_argument("archive", help="the archive to restore")
    sp.add_argument("workspace", nargs="?", default=".")

    sp = porcelain("verify", "verify claim identity")
    sp.add_argument("claim", nargs="?", default=".")

    sp = porcelain("audit", "rerun acceptance criteria")
    sp.add_argument("claim", nargs="?", default=".")

    sp = porcelain("assess", "measure specification strength")
    sp.add_argument("claim", nargs="?", default=".")

    sp = porcelain("rebuild", "rebuild an implementation from a claim")
    sp.add_argument("claim", nargs="?", default=".")
    sp.add_argument("--out", metavar="PATH", help="where to materialize the rebuild")

    sp = porcelain("crosscheck", "compare independent realizations")
    sp.add_argument("claim", nargs="?", default=".")

    sp = porcelain("record", "write an execution record")
    sp.add_argument("claim", nargs="?", default=".")
    sp.add_argument("--key", metavar="KEY", help="credential or signing key reference")
    sp.add_argument("--as", dest="as_", metavar="NAME", help="write the record under this name")
    sp.add_argument("--check", action="store_true", help="verify an existing record instead of writing one")

    sp = porcelain("sign", "authorize a claim or proof")
    sp.add_argument("claim", nargs="?", default=".")
    sp.add_argument("--key", metavar="KEY", help="credential or signing key reference")

    # Plumbing: the entry point the coding-agent hooks installed by
    # `init` call back into. Suppressed from the main listing -- it is
    # never typed by a human at a prompt.
    sp = sub.add_parser("hook", help=argparse.SUPPRESS)
    sp.add_argument("name", help="the hook event name")
    sp.add_argument("workspace", nargs="?", default=".")
    _add_verbose_json(sp)

    # Meta: read the grammar rather than acting on a claim.
    sp = sub.add_parser("help", help=argparse.SUPPRESS)
    sp.add_argument("topic", nargs="?", default=None)
    sp.add_argument("-a", "--all", action="store_true", help="list everything, including older spellings")

    sp = sub.add_parser("completion", help=argparse.SUPPRESS)
    sp.add_argument("shell", nargs="?", default="bash", choices=("bash",))

    return p, sub.choices


def verbs():
    """Every name the parser accepts as a `<command>`: the fourteen
    porcelain verbs, their folded aliases, and the plumbing (`hook`,
    `help`, `completion`) -- read straight off `_parser()`'s own
    subparsers map, so this can never drift from what `-h` accepts.
    """
    _, choices = _parser()
    return sorted(choices)


# ===========================================================================
# Help and completion: generated from the grammar, not hand-maintained.
# ===========================================================================


def _help_topic(name):
    """Print `ret help <name>`'s detailed help: `_FULL_HELP`'s entry for
    `name`'s canonical verb (an alias resolves through `ALIASES` first),
    falling back to that verb's own `-h` text when there is no entry.
    Prints a one-line refusal for a name the parser does not accept.
    """
    canonical = ALIASES.get(name, name)
    text = _FULL_HELP.get(canonical)
    if text is not None:
        print(text)
        return
    _, choices = _parser()
    sp = choices.get(canonical)
    if sp is None:
        print(f"ret: help: no such command: {name}", file=sys.stderr)
        return
    print(sp.format_help())


def _help_all():
    """Print `ret help -a`: the main listing (`_DESC`), the plumbing,
    and every accepted older spelling mapped to the verb it now means.
    """
    print(_DESC)
    print()
    print("Plumbing")
    print("    hook        the coding-agent hook entry point")
    print()
    print("Accepted older spellings")
    for alias in sorted(ALIASES):
        print(f"    {alias:<11} -> {ALIASES[alias]}")


def _completion(shell):
    """Print a shell completion script for `shell`, built from `verbs()`
    so the completion list cannot drift from the grammar it completes.
    Only `"bash"` is supported.
    """
    names = " ".join(verbs())
    if shell != "bash":
        print(f"# completion for {shell!r} is not supported", file=sys.stderr)
        return
    print(
        "_ret_complete() {\n"
        '    local cur="${COMP_WORDS[COMP_CWORD]}"\n'
        f'    COMPREPLY=( $(compgen -W "{names}" -- "$cur") )\n'
        "}\n"
        "complete -F _ret_complete ret"
    )
