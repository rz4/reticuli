"""The `ret` argv grammar -- see `checks/parser_check.py`.

`_parser()` builds the one `argparse.ArgumentParser` the CLI entry point
uses; `verbs()` reads the registered subcommand names back off of it, so
the two can never drift apart -- there is exactly one place a verb gets
registered. `PORCELAIN` names the fourteen verbs a user is meant to
reach for (`spec/layers.md`'s CLI table, as folded on 2026-09-22);
`ALIASES` is where an accepted older spelling of a current verb would be
registered, empty today because every surviving v1 name was folded into
a porcelain verb's own flag rather than kept as a second name (`seal` ->
`pack --accept`, `hooks` -> `init`, `tree`/`claims` -> `status --tree`/
`--claims`, `attest` -> `record --key --as`/`--check`) -- those five, and
every other retired spelling, must never again be a registered
subcommand name. `hook`, `help`, and `completion` are plumbing: they
answer the agent handshake, print help, and emit a shell completion
script, but none of them is something a claim's story is told in terms
of.

Only `reticuli._cli.output` reads `--json`/`--verbose`/`--color` off the
parsed namespace; this module never executes a verb, so it needs nothing
beyond the standard library.
"""
import argparse
import sys

_DESC = 'Reticuli records and reproduces software claims.\n\nAuthoring\n    init        initialize a workspace\n    run         run and observe a command\n    status      show work, claims, and unresolved inputs\n    pack        create a claim from a project\n\nComposition and transport\n    pull        add another claim as a dependency\n    export      write a portable claim archive\n    import      restore a claim archive\n\nVerification\n    verify      verify claim identity\n    audit       rerun acceptance criteria\n    assess      measure specification strength\n\nReconstruction\n    rebuild     rebuild an implementation from a claim\n    crosscheck  compare independent realizations\n\nEvidence\n    record      write an execution record\n    sign        authorize a claim or proof'

_EPILOG = "See 'ret <command> -h' for command usage.\nSee 'ret help <command>' for detailed help; 'ret help -a' lists everything,\nincluding accepted older spellings."

# The fourteen porcelain verbs, grouped exactly as `_DESC` lists them.
PORCELAIN = (
    "init", "run", "status", "pack",
    "pull", "export", "import",
    "verify", "audit", "assess",
    "rebuild", "crosscheck",
    "record", "sign",
)

# Accepted older spellings of a current verb, `old -> current`. Every
# v1 name that once lived here was retired outright on 2026-09-22 rather
# than kept as an alias (see the module docstring); nothing has taken
# this slot since, so it stays empty until one does.
ALIASES = {}

# Plumbing: registered subcommands that are not part of the porcelain.
_PLUMBING = ("hook", "help", "completion")

_FULL_HELP = {
    "init": "init [ws] [--name NAME] [--no-agent]\n\n"
            "Mark a workspace as a session: create its store directory and,\n"
            "unless --no-agent withholds it, wire the agent handshake that\n"
            "feeds the session's trace.",
    "run": "run CMD [--ws WS]\n\n"
           "Run CMD inside the session at WS (default: the current\n"
           "directory), tracing it as a bash event -- the same event\n"
           "`pack` later reads to find a project's gate command.",
    "status": "status [d] [--workspace] [--tree] [--claims] [-v]\n\n"
               "Show one claim's state, or -- with --workspace -- every\n"
               "claim a workspace's store holds. --tree lists a claim's\n"
               "declared files; --claims lists a workspace's sealed claims.\n"
               "-v walks every gate, signature, and ledger entry.",
    "pack": "pack [root] --name NAME [--generated PATTERN ...]\n"
            "     [--inputs PATTERN ...] --gate CMD --gate-output OUTPUT\n"
            "     [--accept] [...]\n\n"
            "Turn a project directory into a sealed claim in place.\n"
            "--accept seals an already-authored recipe without expanding\n"
            "any new generated/input patterns -- the old `seal` verb's job.",
    "pull": "pull SRC DEST [--ws WS]\n\n"
            "Add claim SRC as a dependency of DEST, with its whole closure\n"
            "copied into DEST's store.",
    "export": "export d TAR_PATH [--blind]\n\n"
              "Write claim D's declared content as a portable, "
              "byte-deterministic tar archive.",
    "import": "import TAR_PATH DEST\n\n"
               "Extract TAR_PATH into DEST, and reverify its identity.",
    "verify": "verify [d]\n\n"
              "Recompute D's root from the bytes present and compare it\n"
              "with the sealed manifest. Identity only -- no gate runs.",
    "audit": "audit [d] [--shallow]\n\n"
             "Re-execute every gate, cold and sandboxed, earning each\n"
             "verdict fresh. Composed claims audit recursively unless\n"
             "--shallow opts out.",
    "assess": "assess [d] [--mutants N]\n\n"
              "Measure how much of D's declared output the gates actually\n"
              "interrogate, by mutation testing.",
    "rebuild": "rebuild d PRODUCER INTO [--produce-from OUTPUT=PATH ...]\n"
               "        [--input-from NAME=PATH ...] [--without-guidance]\n\n"
               "Regrow D's generated outputs with PRODUCER into INTO,\n"
               "until the gates pass. --without-guidance withholds every\n"
               "producer hint, so a pass measures what the criteria alone carry.",
    "crosscheck": "crosscheck M1 M2 M3 [--shallow] [--mutants N]\n\n"
                  "The three-machine test: original, transfer, and an\n"
                  "independent rebuild must land one root, every verdict\n"
                  "re-earned, and the cost envelope held.",
    "record": "record [d] [--out PATH] [--key KEY --as PRINCIPAL] [--check]\n\n"
               "Write a signed statement of this machine's results. --key\n"
               "and --as sign it as PRINCIPAL -- the old `attest` verb's\n"
               "job; --check verifies an existing record's signatures\n"
               "instead of writing a new one.",
    "sign": "sign d --key KEY --principal PRINCIPAL [--ws WS]\n\n"
            "The signing ceremony: a human's accountable authorization\n"
            "over a claim's whole chain. Never an agent's act.",
}


def _add_verbose_json(sp: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Add the three flags every verb's report shares: `--json` (the
    five-key envelope), `-v`/`--verbose` (progress on stderr), and
    `--color` (paint the human line; `auto` follows the tty)."""
    sp.add_argument("--json", action="store_true",
                     help="emit the five-key JSON envelope instead of a human line")
    sp.add_argument("-v", "--verbose", action="store_true",
                     help="show progress on stderr")
    sp.add_argument("--color", choices=("auto", "always", "never"), default="auto",
                     help="colorize the human-readable line (default: auto)")
    return sp


def _kv_append(sp: argparse.ArgumentParser, flag: str, metavar: str, help: str) -> None:
    """A repeatable `--flag KEY=VALUE` option, collected as a list of
    raw `KEY=VALUE` strings -- parsing them into a dict is the caller's
    job, not the grammar's."""
    sp.add_argument(flag, action="append", default=[], metavar=metavar, help=help)


def _parser():
    """Build the `ret` parser. Returns `(parser, subparsers)`, where
    `subparsers` maps every registered verb name (porcelain, alias, and
    plumbing alike) to its own `ArgumentParser` -- the one place
    `verbs()`, `_help_topic`, and `_completion` all read the grammar
    from, so none of them can disagree with what was actually
    registered."""
    p = argparse.ArgumentParser(
        prog="ret",
        description=_DESC,
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    action = p.add_subparsers(dest="verb", metavar="<command>")
    subparsers = {}

    def add(name: str, help_text: str = None, aliases=()) -> argparse.ArgumentParser:
        sp = action.add_parser(name, help=help_text, aliases=list(aliases))
        subparsers[name] = sp
        for alias in aliases:
            subparsers[alias] = sp
        return sp

    # -- Authoring -------------------------------------------------------
    sp = add("init", "initialize a workspace")
    sp.add_argument("ws", nargs="?", default=".")
    sp.add_argument("--name")
    sp.add_argument("--no-agent", action="store_true")
    _add_verbose_json(sp)

    sp = add("run", "run and observe a command")
    sp.add_argument("cmd")
    sp.add_argument("--ws", default=".")
    _add_verbose_json(sp)

    sp = add("status", "show work, claims, and unresolved inputs")
    sp.add_argument("d", nargs="?", default=".")
    sp.add_argument("--workspace", action="store_true",
                     help="show every claim the workspace's store holds")
    sp.add_argument("--tree", action="store_true",
                     help="list the claim's declared files (folds the old `tree` verb)")
    sp.add_argument("--claims", action="store_true",
                     help="list the workspace's sealed claims (folds the old `claims` verb)")
    _add_verbose_json(sp)

    sp = add("pack", "create a claim from a project")
    sp.add_argument("root", nargs="?", default=".")
    sp.add_argument("--name", required=True)
    sp.add_argument("--generated", nargs="*", default=[], metavar="PATTERN")
    sp.add_argument("--inputs", nargs="*", default=[], metavar="PATTERN")
    sp.add_argument("--gate")
    sp.add_argument("--gate-output")
    sp.add_argument("--accept", action="store_true",
                     help="seal an already-authored recipe (folds the old `seal` verb)")
    sp.add_argument("--component-name", metavar="NAME")
    sp.add_argument("--component-claim", metavar="DIR")
    sp.add_argument("--claim-format", type=int, metavar="N")
    _kv_append(sp, "--envelope", "UNIT=CEILING", "a cost ceiling, e.g. usd=25.0")
    sp.add_argument("--mutation-floor", type=float, metavar="RATE")
    sp.add_argument("--requires", nargs="*", default=[], metavar="NAME")
    sp.add_argument("--by")
    sp.add_argument("--inputs-manifest", metavar="PATH")
    sp.add_argument("--environment", metavar="PATH")
    _add_verbose_json(sp)

    # -- Composition and transport ---------------------------------------
    sp = add("pull", "add another claim as a dependency")
    sp.add_argument("src")
    sp.add_argument("dest")
    sp.add_argument("--ws")
    _add_verbose_json(sp)

    sp = add("export", "write a portable claim archive")
    sp.add_argument("d")
    sp.add_argument("tar_path", metavar="path")
    sp.add_argument("--blind", action="store_true")
    _add_verbose_json(sp)

    sp = add("import", "restore a claim archive")
    sp.add_argument("tar_path", metavar="path")
    sp.add_argument("dest")
    _add_verbose_json(sp)

    # -- Verification ------------------------------------------------------
    sp = add("verify", "verify claim identity")
    sp.add_argument("d", nargs="?", default=".")
    _add_verbose_json(sp)

    sp = add("audit", "rerun acceptance criteria")
    sp.add_argument("d", nargs="?", default=".")
    sp.add_argument("--shallow", action="store_true",
                     help="skip composed claims' recursive audit")
    _add_verbose_json(sp)

    sp = add("assess", "measure specification strength")
    sp.add_argument("d", nargs="?", default=".")
    sp.add_argument("--mutants", type=int, default=50, metavar="N")
    _add_verbose_json(sp)

    # -- Reconstruction ------------------------------------------------------
    sp = add("rebuild", "rebuild an implementation from a claim")
    sp.add_argument("d")
    sp.add_argument("producer")
    sp.add_argument("into")
    _kv_append(sp, "--produce-from", "OUTPUT=PATH", "reuse PATH's bytes for OUTPUT")
    _kv_append(sp, "--input-from", "NAME=PATH", "materialize pinned input NAME from PATH")
    sp.add_argument("--without-guidance", action="store_true",
                     help="withhold every producer hint from the room's environment")
    _add_verbose_json(sp)

    sp = add("crosscheck", "compare independent realizations")
    sp.add_argument("m1")
    sp.add_argument("m2")
    sp.add_argument("m3")
    sp.add_argument("--shallow", action="store_true",
                     help="skip each leg's recursive deep audit")
    sp.add_argument("--mutants", type=int, metavar="N")
    _add_verbose_json(sp)

    # -- Evidence ------------------------------------------------------
    sp = add("record", "write an execution record")
    sp.add_argument("d", nargs="?", default=".")
    sp.add_argument("--out", metavar="PATH")
    sp.add_argument("--key", metavar="PATH",
                     help="sign the record with this ssh key")
    sp.add_argument("--as", dest="as_", metavar="PRINCIPAL",
                     help="the principal to sign as (folds the old `attest` verb)")
    sp.add_argument("--check", action="store_true",
                     help="verify an existing record's signatures instead of writing one")
    sp.add_argument("--signers", metavar="PATH",
                     help="an allowed_signers file, for --check")
    _add_verbose_json(sp)

    sp = add("sign", "authorize a claim or proof")
    sp.add_argument("d")
    sp.add_argument("--key", required=True)
    sp.add_argument("--principal", required=True)
    sp.add_argument("--ws")
    _add_verbose_json(sp)

    # -- Plumbing ------------------------------------------------------
    sp = add("hook", "the agent handshake's own verb")
    sp.add_argument("payload", nargs="?", help="a JSON payload; defaults to reading stdin")

    sp = add("help", "show detailed help for one command, or everything")
    sp.add_argument("topic", nargs="?")
    sp.add_argument("-a", "--all", action="store_true",
                     help="list everything, including accepted older spellings")

    sp = add("completion", "print a shell completion script")
    sp.add_argument("shell", nargs="?", default="bash", choices=("bash", "zsh"))

    return p, subparsers


def verbs():
    """Every registered subcommand name -- porcelain, alias, and
    plumbing alike -- read back off the parser actually built by
    `_parser()`, so this can never list a name that was not registered
    or omit one that was."""
    _, subparsers = _parser()
    return tuple(subparsers.keys())


def _help_topic(name: str) -> None:
    """Print detailed help for one command: `_FULL_HELP`'s hand-written
    text if this command has one, otherwise its subparser's own usage."""
    text = _FULL_HELP.get(name)
    if text is not None:
        print(text)
        return
    _, subparsers = _parser()
    sp = subparsers.get(name)
    if sp is None:
        print(f"ret: help: no such command: {name!r}", file=sys.stderr)
        return
    print(sp.format_help())


def _help_all() -> None:
    """`ret help -a`: the grouped overview, the plumbing, every accepted
    older spelling, and the epilog -- everything in one place."""
    print(_DESC)
    print()
    print("Plumbing")
    for name in _PLUMBING:
        print(f"    {name}")
    if ALIASES:
        print()
        print("Accepted older spellings")
        for old in sorted(ALIASES):
            print(f"    {old:<12}-> {ALIASES[old]}")
    print()
    print(_EPILOG)


def _completion(shell: str = "bash") -> None:
    """Print a completion script for `shell`, generated from the live
    grammar (`verbs()`) so the two can never drift apart."""
    names = sorted(verbs())
    if shell == "bash":
        word_list = " ".join(names)
        print(f'_ret_complete() {{\n'
              f'    local cur\n'
              f'    cur="${{COMP_WORDS[COMP_CWORD]}}"\n'
              f'    COMPREPLY=( $(compgen -W "{word_list}" -- "$cur") )\n'
              f'}}\n'
              f'complete -F _ret_complete ret')
    elif shell == "zsh":
        word_list = " ".join(names)
        print(f'#compdef ret\n'
              f'_ret() {{\n'
              f'    local -a cmds\n'
              f'    cmds=({word_list})\n'
              f'    _describe "command" cmds\n'
              f'}}\n'
              f'compdef _ret ret')
    else:
        raise ValueError(f"completion: unsupported shell {shell!r}")
