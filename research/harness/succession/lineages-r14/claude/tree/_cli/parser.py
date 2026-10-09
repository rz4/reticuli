"""reticuli._cli.parser -- the argv grammar (spec/layers.md: surface).

Registers exactly the fourteen porcelain verbs (`PORCELAIN`), whatever
older spellings are still accepted for them (`ALIASES`), and the plumbing
(`hook`, `help`, `completion`) -- argparse subparsers built once in
`_parser()`, so `verbs()` reads the grammar back off the parser itself
rather than keeping a second list that could drift from it.

A handful of v1/v2 verbs that used to be separate commands are gone for
good, folded into flags on the porcelain verb that absorbed them: `seal`
into `pack --accept`, `hooks` into `init` (wired by default, `--no-agent`
opts out), `tree`/`claims` into `status --tree`/`status --claims`, and
`attest` into `record --key --as` / `record --check`. Nothing here
dispatches a verb to its implementation -- this module is the grammar
only; what each verb does lives in `_cli.report` and `_cli.statusview`.
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

# Older spellings still accepted for a porcelain verb above, folded into
# argparse's own `aliases=` on that verb's subparser -- `alias -> verb`.
# Empty for now: every v1 name this CLI once carried (`condense`, `realize`,
# `prove`, `mint`, `records`, `hydrate`, `inspect`) and every intermediate
# v2 verb later folded into a flag (`seal`, `hooks`, `tree`, `claims`,
# `attest`) is retired outright, not an accepted spelling of anything.
ALIASES = {}

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

_EPILOG = ("See 'ret <command> -h' for command usage.\n"
           "See 'ret help <command>' for detailed help; 'ret help -a' lists everything,\n"
           "including accepted older spellings.")

_FULL_HELP = {
    "init": "init [workspace]\n\n"
            "Mark a workspace as a session: create its .reticuli/ store and, unless\n"
            "--no-agent is given, wire the coding-agent handshake into it so a trace\n"
            "starts filling without a separate step.",
    "run": "run <command> [--workspace DIR]\n\n"
           "Run a shell command inside a workspace, trace it into the session's\n"
           "draft trace, and return the child's exit code unchanged.",
    "status": "status [target] [--tree] [--claims] [--ledger] [--structure]\n\n"
               "Show a sealed claim's state, or a not-yet-sealed session's draft\n"
               "state. --tree shows the registry's dependency DAG (retired `tree`);\n"
               "--claims lists every claim sealed into the store (retired `claims`);\n"
               "--ledger shows cost residue; --structure shows one claim's anatomy.",
    "pack": "pack <workspace> --name NAME --gate CMD [--generated PAT...] [--inputs PAT...]\n"
            "     [--accept]\n\n"
            "Seal a project as a self-claim from declared glob patterns. --accept\n"
            "(retired `seal`) instead certifies the workspace's own session trace\n"
            "cold and seals the result, rather than packing from glob patterns.",
    "pull": "pull <claim> <dest>\n\nMaterialize a claim as a dependency of a fresh workspace.",
    "export": "export <claim> <out> [--blind]\n\n"
               "Write a deterministic tar of a claim's declared content. --blind\n"
               "omits generated outputs even when present on disk.",
    "import": "import <tar> <dest>\n\n"
               "Extract a tar's declared content and verify the claim's identity\n"
               "holds from the received bytes alone.",
    "verify": "verify <claim>\n\nIdentity and gates, re-run on present bytes.",
    "audit": "audit <claim>\n\nDeep re-earning of every gate: earned vs. carried.",
    "assess": "assess <claim> [--mutants N]\n\n"
              "Measure how much the gates would have caught, by mutation testing.",
    "rebuild": "rebuild <claim> <producer> <into> [--workspace DIR] [--reuse]\n\n"
               "Regrow a claim's generated outputs with a producer; declared\n"
               "components are rebuilt first unless --reuse.",
    "crosscheck": "crosscheck <m1> <m2> <m3>\n\n"
                  "The three-machine test, deep over every ancestor: a leg is a\n"
                  "claim directory or a record file.",
    "record": "record <claim> [--out PATH] [--key KEY --as IDENTITY] [--check]\n\n"
              "Write this machine's signed statement of a claim's current results.\n"
              "--check (retired `attest`) instead checks existing attestations for\n"
              "intactness, drift, and -- given --signers -- signed authenticity.",
    "sign": "sign <claim> --key KEY --as IDENTITY [--workspace DIR] [--check]\n\n"
            "The accountable authorization ceremony over a reviewed claim. --check\n"
            "instead checks each authorization's own integrity.",
}


# -- flags every verb (and the top level) shares ----------------------------

def _add_verbose_json(p) -> None:
    """Wire `--json`, `--verbose`, and `--color` onto `p` -- the one place
    these three flags are spelled, so every subparser that calls this
    agrees on their names and defaults."""
    p.add_argument("--json", action="store_true",
                    help="print the result envelope as one line of JSON")
    p.add_argument("--verbose", action="store_true",
                    help="include the full result data under the human line")
    p.add_argument("--color", choices=("auto", "always", "never"), default="auto",
                    help="colorize human-readable output (default: auto)")


# -- building the grammar -----------------------------------------------

def _aliases_for(verb: str) -> list:
    return sorted(a for a, target in ALIASES.items() if target == verb)


def _parser():
    """The argv grammar: `(parser, subparsers)` -- `subparsers` is the
    `{name: ArgumentParser}` map argparse itself resolved a verb name to,
    aliases included, so `verbs()` reads the grammar back rather than
    keeping a second list that could drift from it."""
    p = argparse.ArgumentParser(
        prog="ret",
        description=_DESC,
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--version", action="store_true", help="print the version and exit")

    sub = p.add_subparsers(dest="verb", metavar="command")

    def add(verb: str, help_text: str):
        sp = sub.add_parser(verb, aliases=_aliases_for(verb), help=help_text)
        _add_verbose_json(sp)
        return sp

    s_init = add("init", "initialize a workspace")
    s_init.add_argument("workspace", nargs="?", default=".")
    s_init.add_argument("--no-agent", dest="no_agent", action="store_true",
                         help="skip wiring the coding-agent handshake")

    s_run = add("run", "run and observe a command")
    s_run.add_argument("command")
    s_run.add_argument("--workspace", default=".")

    s_status = add("status", "show work, claims, and unresolved inputs")
    s_status.add_argument("target", nargs="?", default=".")
    s_status.add_argument("--tree", action="store_true", help="the registry's dependency DAG")
    s_status.add_argument("--claims", action="store_true", help="every claim sealed into the store")
    s_status.add_argument("--ledger", action="store_true", help="cost residue for one claim")
    s_status.add_argument("--structure", action="store_true", help="one claim's own file anatomy")

    s_pack = add("pack", "create a claim from a project")
    s_pack.add_argument("workspace", nargs="?", default=".")
    s_pack.add_argument("--name")
    s_pack.add_argument("--generated", nargs="*", default=())
    s_pack.add_argument("--inputs", nargs="*", default=())
    s_pack.add_argument("--gate")
    s_pack.add_argument("--gate-output", dest="gate_output")
    s_pack.add_argument("--mutation-floor", dest="mutation_floor", type=float)
    s_pack.add_argument("--requires", nargs="*")
    s_pack.add_argument("--by")
    s_pack.add_argument("--accept", action="store_true",
                         help="certify the workspace's own session trace cold, instead of globs")
    s_pack.add_argument("--into")
    s_pack.add_argument("--outputs", nargs="*", default=())

    s_pull = add("pull", "add another claim as a dependency")
    s_pull.add_argument("claim")
    s_pull.add_argument("dest")

    s_export = add("export", "write a portable claim archive")
    s_export.add_argument("claim")
    s_export.add_argument("out")
    s_export.add_argument("--blind", action="store_true")

    s_import = add("import", "restore a claim archive")
    s_import.add_argument("tar")
    s_import.add_argument("dest")

    s_verify = add("verify", "verify claim identity")
    s_verify.add_argument("claim", nargs="?", default=".")

    s_audit = add("audit", "rerun acceptance criteria")
    s_audit.add_argument("claim", nargs="?", default=".")

    s_assess = add("assess", "measure specification strength")
    s_assess.add_argument("claim", nargs="?", default=".")
    s_assess.add_argument("--mutants", type=int, default=50)

    s_rebuild = add("rebuild", "rebuild an implementation from a claim")
    s_rebuild.add_argument("claim")
    s_rebuild.add_argument("producer")
    s_rebuild.add_argument("into")
    s_rebuild.add_argument("--workspace")
    s_rebuild.add_argument("--reuse", action="store_true")

    s_crosscheck = add("crosscheck", "compare independent realizations")
    s_crosscheck.add_argument("m1")
    s_crosscheck.add_argument("m2")
    s_crosscheck.add_argument("m3")

    s_record = add("record", "write an execution record")
    s_record.add_argument("claim", nargs="?", default=".")
    s_record.add_argument("--out")
    s_record.add_argument("--key")
    s_record.add_argument("--as", dest="identity")
    s_record.add_argument("--check", action="store_true",
                           help="check attestations instead of emitting one")
    s_record.add_argument("--signers")

    s_sign = add("sign", "authorize a claim or proof")
    s_sign.add_argument("claim")
    s_sign.add_argument("--key")
    s_sign.add_argument("--as", dest="identity")
    s_sign.add_argument("--workspace", default=".")
    s_sign.add_argument("--check", action="store_true",
                         help="check the ceremony's own integrity instead of signing")
    s_sign.add_argument("--signers")

    # -- plumbing: not porcelain, not an alias of anything -----------------

    sub.add_parser("hook", help="internal: the coding-agent event receiver (reads stdin)")

    s_help = sub.add_parser("help", help="detailed help for one command, or everything with -a")
    s_help.add_argument("topic", nargs="?")
    s_help.add_argument("-a", "--all", action="store_true")

    s_completion = sub.add_parser("completion", help="print a shell completion script")
    s_completion.add_argument("shell", nargs="?", default="bash", choices=("bash", "zsh"))

    return p, sub.choices


# -- verbs(): read the grammar back, so it cannot drift from the parser ----

def verbs() -> list:
    """Every subcommand name `_parser()` actually registers -- the
    fourteen porcelain verbs, every accepted alias, and the plumbing --
    read straight off the built parser rather than a second, driftable
    list."""
    _, subparsers = _parser()
    return sorted(subparsers.keys())


# -- help: `ret help [-a] [topic]` ------------------------------------------

def _help_all() -> None:
    """Everything: the grouped overview (`_DESC`), then every accepted
    alias and its target, then the plumbing -- 'ret help -a' lists
    everything, including accepted older spellings."""
    print(_DESC)
    print()
    if ALIASES:
        print("Accepted older spellings")
        for alias in sorted(ALIASES):
            print(f"    {alias:<12}-> {ALIASES[alias]}")
        print()
    print("Plumbing")
    print("    hook        internal: the coding-agent event receiver")
    print("    help        detailed help for one command, or everything with -a")
    print("    completion  print a shell completion script")


def _help_topic(name: str) -> int:
    """Detailed help for one command. Returns 0 if `name` is known, 1
    otherwise (so `ret help <typo>` is a refusal, not a silent no-op)."""
    _, subparsers = _parser()
    if name in _FULL_HELP:
        print(_FULL_HELP[name])
        return 0
    if name in subparsers:
        subparsers[name].print_help()
        return 0
    print(f"ret: help: no such command: {name!r}", file=sys.stderr)
    return 1


# -- shell completion, generated from the grammar so it cannot drift -------

def _completion(shell: str) -> None:
    """Print a completion script for `shell` naming every verb `verbs()`
    returns -- generated from the grammar, not hand-maintained, so it
    cannot drift from what the parser actually accepts."""
    names = " ".join(verbs())
    if shell == "zsh":
        print(f"#compdef ret\n_ret() {{ reply=({names}) }}\ncompctl -K _ret ret")
        return
    print(
        "_ret_complete() {\n"
        '    local cur="${COMP_WORDS[COMP_CWORD]}"\n'
        f'    COMPREPLY=($(compgen -W "{names}" -- "$cur"))\n'
        "}\n"
        "complete -F _ret_complete ret"
    )
