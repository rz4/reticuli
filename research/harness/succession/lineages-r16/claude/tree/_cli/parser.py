"""The argv grammar: the fourteen porcelain verbs, the folded aliases, and
the plumbing (`hook`, `help`, `completion`).

`_parser()` builds the top-level `argparse.ArgumentParser` once, adding one
subparser per entry in `PORCELAIN`, then one per `ALIASES` key, then the
three plumbing verbs -- and hands back both the parser and the dict of
every subparser it registered. `verbs()` reads that same dict back, so the
grammar and its own listing cannot drift apart; `_completion` builds a
shell completion script from `verbs()` for the same reason. `_help_all`
and `_help_topic` are `ret help`'s two forms: every command at a glance
(aliases and plumbing included), or one command's full usage.

v1 verbs that are gone outright -- never aliased, never reachable -- are
tracked by the caller (`checks/parser_check.py`'s `RETIRED`), not here:
some were folded into a porcelain verb's flag (`seal` into `pack --accept`,
`hooks` into `init`'s agent handshake, `tree`/`claims` into `status
--tree`/`--claims`, `attest` into `record --key --as` / `record --check`),
and some were dropped with the v1 vocabulary itself.
"""
import argparse

PORCELAIN = (
    "init", "run", "status", "pack",
    "pull", "export", "import",
    "verify", "audit", "assess",
    "rebuild", "crosscheck",
    "record", "sign",
)

# No v1 spelling is currently kept alive as a bare-verb alias -- every one
# that survived the 2026-09-22 fold moved onto a flag of a porcelain verb
# instead (see the module docstring); this stays a dict, open for the next
# one that is merely renamed rather than retired.
ALIASES = {}

_PLUMBING = ("hook", "help", "completion")

_DESC = 'Reticuli records and reproduces software claims.\n\nAuthoring\n    init        initialize a workspace\n    run         run and observe a command\n    status      show work, claims, and unresolved inputs\n    pack        create a claim from a project\n\nComposition and transport\n    pull        add another claim as a dependency\n    export      write a portable claim archive\n    import      restore a claim archive\n\nVerification\n    verify      verify claim identity\n    audit       rerun acceptance criteria\n    assess      measure specification strength\n\nReconstruction\n    rebuild     rebuild an implementation from a claim\n    crosscheck  compare independent realizations\n\nEvidence\n    record      write an execution record\n    sign        authorize a claim or proof'

_EPILOG = "See 'ret <command> -h' for command usage.\nSee 'ret help <command>' for detailed help; 'ret help -a' lists everything,\nincluding accepted older spellings."

_FULL_HELP = {
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
    "hook": "classify one coding-agent hook payload (plumbing)",
    "help": "show detailed help for one command, or every command with -a",
    "completion": "print a shell completion script",
}


def _add_verbose_json(sub) -> None:
    """Add the `--json` / `--verbose` / `--color` output flags every verb's
    subparser shares -- `output._finish`'s envelope and the `-v` detail
    view are available uniformly across the grammar."""
    sub.add_argument("--json", action="store_true",
                      help="print the machine-readable envelope instead of a human summary")
    sub.add_argument("--verbose", "-v", action="store_true",
                      help="show extra detail in human-readable mode")
    sub.add_argument("--color", choices=("auto", "always", "never"), default="auto",
                      help="colorize human-mode output (default: auto)")


def _parser():
    """Build the top-level parser and every subparser it owns. Returns
    `(parser, registered)`, where `registered` maps every verb name --
    porcelain, alias, and plumbing alike -- to its own subparser; `verbs()`
    is exactly `registered`'s keys, so the two cannot disagree."""
    p = argparse.ArgumentParser(
        prog="ret",
        description=_DESC,
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--version", action="store_true", help="print the version and exit")
    sub = p.add_subparsers(dest="verb", metavar="<command>")

    registered = {}

    def add(name):
        s = sub.add_parser(name, help=_FULL_HELP.get(name, ""))
        registered[name] = s
        return s

    s = add("init")
    s.add_argument("dir", nargs="?", default=".", help="the workspace directory (default: .)")
    s.add_argument("--no-agent", action="store_true",
                    help="withhold the coding-agent handshake (the folded `hooks` behavior)")
    _add_verbose_json(s)

    s = add("run")
    s.add_argument("cmd", help="the shell command to run and observe")
    s.add_argument("--dir", help="the workspace to run inside (default: cwd)")
    _add_verbose_json(s)

    s = add("status")
    s.add_argument("dir", nargs="?", default=".", help="the claim/workspace directory (default: .)")
    s.add_argument("--tree", action="store_true", help="show the dependency DAG (the folded `tree` verb)")
    s.add_argument("--claims", action="store_true", help="list every sealed claim (the folded `claims` verb)")
    s.add_argument("--deps", action="store_true", help="show the flat dependency report")
    _add_verbose_json(s)

    s = add("pack")
    s.add_argument("dir", nargs="?", default=".", help="the project directory (default: .)")
    s.add_argument("--name", help="the claim's name")
    s.add_argument("--gate", help="the gate command")
    s.add_argument("--gate-output", default="gate", help="the gate's verdict file (default: gate)")
    s.add_argument("--generated", action="append", default=[], help="a generated (regrowable) output; repeatable")
    s.add_argument("--inputs", action="append", default=[], help="a pinned input; repeatable")
    s.add_argument("--component", help="a layered sub-claim to depend on")
    s.add_argument("--format", type=int, help="the claim format to write")
    s.add_argument("--envelope", action="append", default=[], help="unit=ceiling cost commitment; repeatable")
    s.add_argument("--mutation-floor", type=float, help="minimum mutation-kill rate the crosscheck must re-earn")
    s.add_argument("--requires", action="append", default=[], help="a host environment requirement; repeatable")
    s.add_argument("--by", help="the producer credited with the generated bytes")
    s.add_argument("--inputs-manifest", help="write a large corpus as a manifest file instead of inline inputs")
    s.add_argument("--environment", help="a hash-pinned requirements file")
    s.add_argument("--accept", action="store_true",
                    help="seal immediately after packing (the folded `seal` verb)")
    _add_verbose_json(s)

    s = add("pull")
    s.add_argument("src", help="the claim to add as a dependency")
    s.add_argument("dest", help="the workspace to add it into")
    _add_verbose_json(s)

    s = add("export")
    s.add_argument("dir", nargs="?", default=".", help="the claim directory (default: .)")
    s.add_argument("--out", help="the archive path to write")
    s.add_argument("--blind", action="store_true", help="exclude generated bytes from the archive")
    _add_verbose_json(s)

    s = add("import")
    s.add_argument("tar", help="the archive to restore")
    s.add_argument("dest", nargs="?", help="where to restore it (default: cwd)")
    _add_verbose_json(s)

    s = add("verify")
    s.add_argument("dir", nargs="?", default=".", help="the claim directory (default: .)")
    _add_verbose_json(s)

    s = add("audit")
    s.add_argument("dir", nargs="?", default=".", help="the claim directory (default: .)")
    s.add_argument("--deep", action="store_true", help="re-earn composed claims recursively (the default)")
    s.add_argument("--shallow", action="store_true", help="opt out of the recursive deep audit")
    _add_verbose_json(s)

    s = add("assess")
    s.add_argument("dir", nargs="?", default=".", help="the claim directory (default: .)")
    s.add_argument("--mutants", type=int, help="how many deterministic mutants to draw")
    _add_verbose_json(s)

    s = add("rebuild")
    s.add_argument("dir", nargs="?", default=".", help="the claim directory (default: .)")
    s.add_argument("--into", help="the room to regrow into (default: a fresh scratch directory)")
    s.add_argument("--producer", help="the producer to regrow with (default: $RETICULI_PRODUCER)")
    s.add_argument("--ws", help="a session workspace whose trace guides the producer")
    s.add_argument("--reuse", action="store_true", help="resume into a non-empty target")
    s.add_argument("--without-guidance", action="store_true",
                    help="withhold every producer hint, to measure what the criteria alone carry")
    _add_verbose_json(s)

    s = add("crosscheck")
    s.add_argument("dir", nargs="?", default=".", help="M1, the original claim directory (default: .)")
    s.add_argument("--m2", help="M2: a transfer leg (a claim directory or a record)")
    s.add_argument("--m3", help="M3: an independent-rebuild leg (a claim directory or a record)")
    s.add_argument("--mutants", type=int, help="how many deterministic mutants M3 must re-earn")
    _add_verbose_json(s)

    s = add("record")
    s.add_argument("dir", nargs="?", default=".", help="the claim directory (default: .)")
    s.add_argument("--out", help="the record path to write (default: <dir>/record.json)")
    s.add_argument("--key", help="an ssh private key to sign the record with")
    s.add_argument("--as", dest="identity", help="the identity to sign as (the folded `attest` verb)")
    s.add_argument("--check", action="store_true",
                    help="verify a record's signature against $RETICULI_SIGNERS (the folded `attest` check)")
    s.add_argument("--signers", help="an allowed-signers file (default: $RETICULI_SIGNERS)")
    _add_verbose_json(s)

    s = add("sign")
    s.add_argument("dir", nargs="?", default=".", help="the claim directory (default: .)")
    s.add_argument("--key", help="an ssh private key to sign the root with")
    s.add_argument("--identity", help="the identity to sign as")
    s.add_argument("--ws", help="a session workspace to record the signature under")
    _add_verbose_json(s)

    for alias, target in ALIASES.items():
        s = add(alias)
        s.set_defaults(_alias_for=target)
        _add_verbose_json(s)

    s = add("hook")
    s.add_argument("--project-dir", help="the project to wire the handshake into (default: cwd)")

    s = add("help")
    s.add_argument("topic", nargs="?", help="a command to show detailed help for")
    s.add_argument("-a", "--all", action="store_true", help="list everything, including accepted older spellings")

    s = add("completion")
    s.add_argument("shell", nargs="?", default="bash", choices=("bash", "zsh"), help="the shell to emit for")

    return p, registered


def verbs():
    """Every verb this grammar accepts: the fourteen porcelain verbs, every
    `ALIASES` key, and the three plumbing verbs -- read back from `_parser`'s
    own registration, so this can never list something the grammar does not
    actually accept, or omit something it does."""
    _, registered = _parser()
    return tuple(registered)


def _completion(shell: str = "bash") -> None:
    """Print a shell completion script for `shell`, built from `verbs()` --
    the completions are generated from the grammar, so they cannot drift
    from it the way a hand-maintained word list could."""
    names = " ".join(sorted(verbs()))
    if shell == "zsh":
        print(
            "#compdef ret\n"
            f"_ret() {{ compadd {names}; }}\n"
            "compdef _ret ret"
        )
        return
    print(
        "_ret_completion() {\n"
        '    local cur="${COMP_WORDS[COMP_CWORD]}"\n'
        f'    COMPREPLY=( $(compgen -W "{names}" -- "$cur") )\n'
        "}\n"
        "complete -F _ret_completion ret"
    )


def _help_all() -> None:
    """`ret help -a`: every command at a glance, aliases and plumbing
    included, with the one-line help `_FULL_HELP` carries for it."""
    names = verbs()
    width = max(len(name) for name in names)
    for name in sorted(names):
        if name in _FULL_HELP:
            text = _FULL_HELP[name]
        elif name in ALIASES:
            text = f"accepted older spelling of {ALIASES[name]!r}"
        else:
            text = ""
        print(f"{name:<{width}}  {text}")


def _help_topic(topic: str) -> None:
    """`ret help <command>`: one command's full usage, or a refusal naming
    the unknown command rather than a traceback."""
    _, registered = _parser()
    s = registered.get(topic)
    if s is None:
        print(f"ret: help: no such command: {topic!r}")
        return
    print(s.format_help())
