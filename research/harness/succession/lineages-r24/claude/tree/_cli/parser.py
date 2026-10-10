"""reticuli._cli.parser: the argv grammar (spec/layers.md "surface";
checks/parser_check.py is this module's definition).

Fourteen porcelain verbs (`PORCELAIN`), grouped in `_DESC` the same way
`ret -h` prints them, plus the folded spelling aliases (`ALIASES`) and the
plumbing (`hook`, `help`, `completion`). Five v1 verbs retired on
2026-09-22 folded into a porcelain verb's own options instead of staying
separate words: `seal` into `pack --accept`, `hooks` into `init` (which
always wires the agent handshake unless `--no-agent` withholds it), `tree`
and `claims` into `status --tree` / `status --claims`, and `attest` into
`record --key --as` / `record --check`. A retired verb never comes back as
an alias -- it is gone, not renamed.

`_parser()` builds one `argparse.ArgumentParser` with one subparser per
registered verb; `verbs()` reads the grammar back out of it, so the set of
recognized commands can never drift from what `-h` and completion already
describe. `_completion` renders that same grammar as a shell completion
script. `_help_topic`/`_help_all` are `ret help`'s own two forms (one
command, or 'ret help -a' for everything, folded spellings included).
Stdlib only.
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

# Folded spelling aliases: alias -> canonical porcelain verb. A retired
# verb (checks/parser_check.py RETIRED) never appears here -- it has no
# alias, it is gone.
ALIASES = {}

_DESC = ("Reticuli records and reproduces software claims.\n"
         "\n"
         "Authoring\n"
         "    init        initialize a workspace\n"
         "    run         run and observe a command\n"
         "    status      show work, claims, and unresolved inputs\n"
         "    pack        create a claim from a project\n"
         "\n"
         "Composition and transport\n"
         "    pull        add another claim as a dependency\n"
         "    export      write a portable claim archive\n"
         "    import      restore a claim archive\n"
         "\n"
         "Verification\n"
         "    verify      verify claim identity\n"
         "    audit       rerun acceptance criteria\n"
         "    assess      measure specification strength\n"
         "\n"
         "Reconstruction\n"
         "    rebuild     rebuild an implementation from a claim\n"
         "    crosscheck  compare independent realizations\n"
         "\n"
         "Evidence\n"
         "    record      write an execution record\n"
         "    sign        authorize a claim or proof")

_EPILOG = ("See 'ret <command> -h' for command usage.\n"
           "See 'ret help <command>' for detailed help; 'ret help -a' lists everything,\n"
           "including accepted older spellings.")

# One short help line per registered verb -- fed to argparse's own `help=`
# for the one-line form, and reused verbatim by `_help_all`.
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
    "hook": "internal: the agent-hook event handshake",
    "help": "show detailed help for a command",
    "completion": "print a shell completion script",
}


def _add_verbose_json(sp: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """The two output-shaping flags every verb accepts, so they read the
    same after the verb as before it (`ret pack -v` and `ret -v pack`
    alike): `--json` for the machine envelope, `-v/--verbose` for the
    long human form."""
    sp.add_argument("--json", action="store_true", help="emit the machine-readable envelope")
    sp.add_argument("-v", "--verbose", action="store_true", help="show every field")
    return sp


def _parser():
    """Build the whole grammar fresh: the top-level parser and its verb
    subparsers, one per `PORCELAIN` entry (carrying its folded aliases),
    plus the plumbing verbs `hook`, `help`, `completion`. Returns
    `(parser, subparsers_action)` -- the second value is where `verbs()`
    and `_completion` read the registered names back out, so neither can
    name a command the grammar does not actually have."""
    p = argparse.ArgumentParser(
        prog="ret",
        description=_DESC,
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--color", choices=("auto", "always", "never"), default="auto",
                    help="paint terminal output (default: auto)")
    _add_verbose_json(p)

    sub = p.add_subparsers(dest="verb", metavar="<command>")

    def add_verb(name, **kw):
        aliases = sorted(a for a, canon in ALIASES.items() if canon == name)
        sp = sub.add_parser(name, aliases=aliases, help=_FULL_HELP.get(name, ""))
        _add_verbose_json(sp)
        return sp

    # -- authoring --------------------------------------------------------
    sp = add_verb("init")
    sp.add_argument("dir", nargs="?", default=".", help="workspace to initialize")
    sp.add_argument("--name", help="the claim's name (default: the directory's own name)")
    sp.add_argument("--no-agent", action="store_true", help="skip wiring the agent-hook handshake")

    sp = add_verb("run")
    sp.add_argument("cmd", help="the command to run and trace")
    sp.add_argument("--dir", default=".", help="workspace the command runs in")

    sp = add_verb("status")
    sp.add_argument("dir", nargs="?", default=".", help="workspace or claim to report on")
    sp.add_argument("--tree", action="store_true", help="retired `tree`: show the dependency tree")
    sp.add_argument("--claims", action="store_true", help="retired `claims`: list every sealed claim")

    sp = add_verb("pack")
    sp.add_argument("name", help="the claim's name")
    sp.add_argument("generated", nargs="+", help="generated outputs -- the implementation")
    sp.add_argument("--inputs", nargs="*", default=[], help="pinned inputs")
    sp.add_argument("--gate", required=False, help="the gate command")
    sp.add_argument("--gate-output", default="OK", help="the gate's verdict file")
    sp.add_argument("--accept", action="store_true", help="retired `seal`: freeze into a sealed claim")
    sp.add_argument("--format", type=int, help="recipe format version")
    sp.add_argument("--envelope", action="append", default=[], metavar="UNIT=VALUE")
    sp.add_argument("--mutation-floor", type=float)
    sp.add_argument("--requires", nargs="*", default=[])
    sp.add_argument("--inputs-manifest")
    sp.add_argument("--environment")

    # -- composition and transport ---------------------------------------
    sp = add_verb("pull")
    sp.add_argument("dir", help="the dependent claim's directory")
    sp.add_argument("into", help="the dependency claim to pull in")

    sp = add_verb("export")
    sp.add_argument("dir", help="the claim to export")
    sp.add_argument("out", help="the archive path to write")
    sp.add_argument("--blind", action="store_true", help="exclude generated outputs")

    sp = add_verb("import")
    sp.add_argument("tar", help="the archive to restore")
    sp.add_argument("into", help="the directory to restore into")

    # -- verification -------------------------------------------------------
    sp = add_verb("verify")
    sp.add_argument("dir", nargs="?", default=".", help="the claim to verify")

    sp = add_verb("audit")
    sp.add_argument("dir", nargs="?", default=".", help="the claim to audit")

    sp = add_verb("assess")
    sp.add_argument("dir", nargs="?", default=".", help="the claim to measure")
    sp.add_argument("--mutants", type=int, default=20)

    # -- reconstruction -----------------------------------------------------
    sp = add_verb("rebuild")
    sp.add_argument("dir", nargs="?", default=".", help="the claim to rebuild")
    sp.add_argument("--producer", help="a named producer, or a raw shell command")
    sp.add_argument("--into", help="where to write the regrown outputs (default: dir)")
    sp.add_argument("--produce-from", dest="produce_from")
    sp.add_argument("--input-from", dest="input_from")
    sp.add_argument("--without-guidance", dest="guidance", action="store_false",
                     help="withhold every producer hint from the room")

    sp = add_verb("crosscheck")
    sp.add_argument("m1", help="the original: a claim directory or a signed record")
    sp.add_argument("m2", help="the transfer: a claim directory or a signed record")
    sp.add_argument("m3", help="the independent rebuild: a claim directory or a signed record")
    sp.add_argument("--mutants", type=int)

    # -- evidence -------------------------------------------------------
    sp = add_verb("record")
    sp.add_argument("dir", nargs="?", default=".", help="the claim to record")
    sp.add_argument("--out", help="write the record document here")
    sp.add_argument("--key", help="an ssh private key to sign with")
    sp.add_argument("--as", dest="identity", help="retired `attest`: the signing identity")
    sp.add_argument("--check", action="store_true", help="retired `attest`: verify signatures instead of writing")

    sp = add_verb("sign")
    sp.add_argument("dir", nargs="?", default=".", help="the claim or proof to authorize")
    sp.add_argument("--key", help="an ssh private key to sign with")
    sp.add_argument("--identity", help="the signing identity")

    # -- plumbing -------------------------------------------------------------
    sp = add_verb("hook")
    sp.add_argument("event", nargs="?", help="the agent-hook event payload comes on stdin")

    sp = add_verb("help")
    sp.add_argument("topic", nargs="?", help="a command to show detailed help for")
    sp.add_argument("-a", "--all", action="store_true", help="list everything, folded spellings included")

    sp = add_verb("completion")
    sp.add_argument("shell", nargs="?", default="bash", choices=("bash",))

    return p, sub


def verbs():
    """Every command name the grammar actually registers -- porcelain
    verbs, their folded aliases, and the plumbing -- read back out of a
    freshly built parser, so this can never list a name `_parser` does
    not."""
    _, sub = _parser()
    return set(sub.choices.keys())


def _help_topic(name: str) -> int:
    """`ret help <name>`: the named subparser's own `-h` text. An unknown
    name is a refusal that names it, not a crash."""
    _, sub = _parser()
    sp = sub.choices.get(name)
    if sp is None:
        print(f"ret: help: no such command: {name!r}", file=sys.stderr)
        return 1
    sp.print_help()
    return 0


def _help_all() -> int:
    """`ret help -a`: every registered command's help, folded spellings
    included, in one listing."""
    _, sub = _parser()
    for name in sorted(sub.choices):
        print(f"\n== {name} ==")
        sub.choices[name].print_help()
    return 0


def _completion(shell: str = "bash") -> None:
    """Print a shell completion script generated from the grammar
    `verbs()` reads, so the two can never drift apart."""
    names = " ".join(sorted(verbs()))
    if shell != "bash":
        print(f"# completion not available for shell: {shell}", file=sys.stderr)
        return
    print("_ret_complete() {")
    print("    local cur")
    print("    cur=${COMP_WORDS[COMP_CWORD]}")
    print(f"    COMPREPLY=( $(compgen -W \"{names}\" -- \"$cur\") )")
    print("}")
    print("complete -F _ret_complete ret")
