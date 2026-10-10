"""reticuli.cli: the human/machine command grammar (spec/layers.md "surface";
checks/surface_check.py is this module's acceptance check).

Fourteen porcelain verbs, one concept each, grouped by workflow in the top
help (`-h`/no args): Authoring, Composition and transport, Verification,
Reconstruction, Evidence. `hook`/`help`/`completion` are plumbing: present in
the grammar (`verbs()`), never listed among the fourteen. Older (v1)
spellings are retired outright -- not aliased -- and an unrecognized verb
gets the git answer: name the mistake, suggest the near miss, exit 2.

Two-level help: `<verb> -h` is argparse's own concise usage; `<verb> --help`
(and `help <verb>`) is the fuller SYNOPSIS account. Because both `-h` and
`--help` would otherwise collapse onto the same argparse action, every verb
parser disables the built-in help (`add_help=False`) and this module
intercepts the two spellings itself, before argparse ever sees them.

Every verb also accepts `--json` (the stable five-field envelope) and
`-v`/`--verbose` (the long human account); a verb's own business logic
lives in `dispatch.py`, which this module only parses argv for and routes
to.
"""
import argparse
import difflib
import sys

from reticuli._cli import dispatch

_VERSION = "2.2"

PORCELAIN = (
    "init", "run", "status", "pack",
    "pull", "export", "import",
    "verify", "audit", "assess",
    "rebuild", "crosscheck",
    "record", "sign",
)
PLUMBING = ("hook", "help", "completion")
ALIASES = {}
RETIRED = ("condense", "realize", "prove", "mint", "records", "hydrate",
           "inspect", "seal", "hooks", "tree", "claims", "attest")

_GROUPS = (
    ("Authoring", (
        ("init", "initialize a workspace"),
        ("run", "run and observe a command"),
        ("status", "show work, claims, and unresolved inputs"),
        ("pack", "create a claim from a project"),
    )),
    ("Composition and transport", (
        ("pull", "add another claim as a dependency"),
        ("export", "write a portable claim archive"),
        ("import", "restore a claim archive"),
    )),
    ("Verification", (
        ("verify", "verify claim identity"),
        ("audit", "rerun acceptance criteria"),
        ("assess", "measure specification strength"),
    )),
    ("Reconstruction", (
        ("rebuild", "rebuild an implementation from a claim"),
        ("crosscheck", "compare independent realizations"),
    )),
    ("Evidence", (
        ("record", "write an execution record"),
        ("sign", "authorize a claim or proof"),
    )),
)


def _top_help() -> str:
    lines = ["usage: ret <command> [options]", "",
             "Reticuli records and reproduces software claims.", ""]
    for group, verbs in _GROUPS:
        lines.append(group)
        for name, desc in verbs:
            lines.append(f"    {name:<12}{desc}")
        lines.append("")
    lines.append("See 'ret <command> -h' for usage; 'ret help <command>' for details;")
    lines.append("'ret help -a' lists everything, including accepted older spellings.")
    return "\n".join(lines)


_ENV_DOC = """environment variables

RETICULI_KEY       an ssh private key path used by 'record --sign'
RETICULI_SIGNERS   an ssh allowed_signers file: the trust anchor records
                   and signatures are checked against
RETICULI_COLOR     auto (default) / always / never -- paints terminal output
RETICULI_JAILED    internal: set when already inside an applied sandbox
RETICULI_GATE_TIMEOUT   a host ceiling on every gate's wall-clock bound
RETICULI_TOLERANCE      override the crosscheck cost-band tolerance
RETICULI_ENV_CACHE      where furnished venvs are cached
OPENAI_API_KEY     credential the 'codex'/'openai' producers need
ANTHROPIC_API_KEY  credential the 'claude' producer needs
"""

_CONCISE = {
    "init": "ret init [dir] [--agent NAME] [--no-agent]",
    "run": "ret run <cmd> [-C dir]",
    "status": "ret status [dir] [--all] [--files] [--tree] [--claims]",
    "pack": "ret pack [dir] [--accept OUTPUT -o DEST] [--name NAME]",
    "pull": "ret pull <dir> <into>",
    "export": "ret export <dir> [out] [--blind]",
    "import": "ret import <tar> <into>",
    "verify": "ret verify [dir]",
    "audit": "ret audit [dir] [--shallow] [--no-strict] [--mutants N]",
    "assess": "ret assess [dir] [--mutants N]",
    "rebuild": "ret rebuild [dir] --producer NAME-OR-CMD [-o into]",
    "crosscheck": "ret crosscheck <m1> <m2> [m3] [--mutants N]",
    "record": "ret record [dir] [-o out] [--key K --as ID] [--check] [--sign]",
    "sign": "ret sign [dir] [--key K --as ID] [--check]",
    "hook": "ret hook [-C dir]",
    "help": "ret help [command] [-a]",
    "completion": "ret completion [bash]",
}

_DETAIL = {
    "verify": """SYNOPSIS
    ret verify [dir]

Recompute the claim's identity from the bytes present and compare it with
the sealed manifest. Does not execute acceptance criteria -- no gate is
run; identity is a hash comparison, answered in milliseconds. See 'audit'
for a verdict earned by actually running the gates.
""",
    "audit": """SYNOPSIS
    ret audit [dir] [--shallow] [--no-strict] [--mutants N] [--record PATH]

Re-execute every gate, cold and sandboxed, composed claims included. The
only verb that re-earns a verdict: it does not execute acceptance criteria
by reading a carried verdict, it runs them now. Strict by default: a
claim's gates never read your files -- judging happens over an isolated
copy -- and --no-strict opts down to judging in place. --shallow audits
only the claim's own gates, not its composed ancestry.
""",
    "rebuild": """SYNOPSIS
    ret rebuild [dir] --producer NAME-OR-CMD [-o into]

Regrow a claim's generated outputs until its gates pass. Generated sources
are withheld from the room a producer sees -- only the pinned inputs,
fixtures, and recipe travel in. Producer guidance is a hint for a
rebuilder, never a condition on acceptance, and --without-guidance
withholds it entirely too, so a pass measures what the criteria alone
carry. A shipped producer answers to its own name
(--producer codex, --producer claude, --producer openai); a producer stays
any program -- a raw shell command works exactly the same way.
""",
    "help": """SYNOPSIS
    ret help [command] [-a]

Show detailed help for one command, or everything (including accepted
older spellings) under -a.
""",
}


def _detail_help(verb: str) -> str:
    text = _DETAIL.get(verb)
    if text:
        return text
    desc = dict(x for _g, items in _GROUPS for x in items).get(verb, "")
    return f"SYNOPSIS\n    {_CONCISE.get(verb, 'ret ' + verb)}\n\n{desc}\n"


def _concise_help(verb: str) -> str:
    sp = _build_parser(verb)
    sp.usage = _CONCISE.get(verb)
    return sp.format_help()


def _help_all() -> str:
    chunks = []
    for name in sorted(set(PORCELAIN) | set(ALIASES) | set(PLUMBING)):
        chunks.append(f"== {name} ==\n{_detail_help(name)}")
    return "\n".join(chunks)


def verbs():
    """Every command name the grammar recognizes: the fourteen porcelain
    verbs, their folded aliases (none, currently), and the plumbing."""
    return set(PORCELAIN) | set(ALIASES) | set(PLUMBING)


# ---------------------------------------------------------------------------
# per-verb argparse grammar (add_help=False: -h/--help are handled above argparse)
# ---------------------------------------------------------------------------

def _add_common(sp):
    sp.add_argument("--json", action="store_true")
    sp.add_argument("-v", "--verbose", action="store_true")
    return sp


def _build_parser(verb: str) -> argparse.ArgumentParser:
    sp = argparse.ArgumentParser(prog=f"ret {verb}", add_help=False)
    _add_common(sp)

    if verb == "init":
        sp.add_argument("dir", nargs="?", default=".")
        sp.add_argument("--name")
        sp.add_argument("--agent")
        sp.add_argument("--no-agent", action="store_true")
    elif verb == "run":
        sp.add_argument("cmd")
        sp.add_argument("-C", "--dir", dest="C")
    elif verb == "status":
        sp.add_argument("dir", nargs="?", default=".")
        sp.add_argument("--all", action="store_true")
        sp.add_argument("--files", action="store_true")
        sp.add_argument("--tree", action="store_true")
        sp.add_argument("--claims", action="store_true")
    elif verb == "pack":
        sp.add_argument("dir", nargs="?", default=".")
        sp.add_argument("--accept", metavar="OUTPUT")
        sp.add_argument("-o", "--out")
        sp.add_argument("--name")
        sp.add_argument("--format", type=int)
        sp.add_argument("--envelope", action="append", default=[])
        sp.add_argument("--mutation-floor", type=float)
        sp.add_argument("--requires", nargs="*", default=[])
        sp.add_argument("--inputs-manifest")
        sp.add_argument("--environment")
        sp.add_argument("--pytest", action="store_true")
        sp.add_argument("--gate")
        sp.add_argument("--gate-output", default="OK")
        sp.add_argument("--generated", nargs="*", default=[])
        sp.add_argument("--inputs", nargs="*", default=[])
    elif verb == "pull":
        sp.add_argument("dir")
        sp.add_argument("into")
    elif verb == "export":
        sp.add_argument("dir")
        sp.add_argument("out", nargs="?", default=None)
        sp.add_argument("-o", "--out-flag", dest="out_flag", default=None)
        sp.add_argument("--blind", action="store_true")
    elif verb == "import":
        sp.add_argument("tar")
        sp.add_argument("into")
    elif verb == "verify":
        sp.add_argument("dir", nargs="?", default=".")
    elif verb == "audit":
        sp.add_argument("dir", nargs="?", default=".")
        sp.add_argument("--shallow", action="store_true")
        sp.add_argument("--no-strict", dest="no_strict", action="store_true")
        sp.add_argument("--mutants", type=int)
        sp.add_argument("--record")
    elif verb == "assess":
        sp.add_argument("dir", nargs="?", default=".")
        sp.add_argument("--mutants", type=int, default=20)
    elif verb == "rebuild":
        sp.add_argument("dir", nargs="?", default=".")
        sp.add_argument("--producer")
        sp.add_argument("-o", "--into", dest="into")
        sp.add_argument("--produce-from")
        sp.add_argument("--input-from")
        sp.add_argument("--without-guidance", dest="guidance", action="store_false")
        sp.set_defaults(guidance=True)
    elif verb == "crosscheck":
        sp.add_argument("m1")
        sp.add_argument("m2")
        sp.add_argument("m3", nargs="?", default=None)
        sp.add_argument("--mutants", type=int)
    elif verb == "record":
        sp.add_argument("dir", nargs="?", default=".")
        sp.add_argument("-o", "--out")
        sp.add_argument("--key")
        sp.add_argument("--as", dest="identity")
        sp.add_argument("--check", action="store_true")
        sp.add_argument("--sign", dest="sign_flag", action="store_true")
    elif verb == "sign":
        sp.add_argument("dir", nargs="?", default=".")
        sp.add_argument("--key")
        sp.add_argument("--as", "--identity", dest="identity")
        sp.add_argument("--check", action="store_true")
    elif verb == "hook":
        sp.add_argument("event", nargs="?")
        sp.add_argument("-C", "--dir", dest="C")
    elif verb == "help":
        sp.add_argument("topic", nargs="?")
        sp.add_argument("-a", "--all", action="store_true")
    elif verb == "completion":
        sp.add_argument("shell", nargs="?", default="bash")
    return sp


_ROUTES = {
    "init": dispatch.do_init,
    "run": dispatch.do_run,
    "status": dispatch.do_status,
    "pack": dispatch.do_pack,
    "pull": dispatch.do_pull,
    "export": dispatch.do_export,
    "import": dispatch.do_import,
    "verify": dispatch.do_verify,
    "audit": dispatch.do_audit,
    "assess": dispatch.do_assess,
    "rebuild": dispatch.do_rebuild,
    "crosscheck": dispatch.do_crosscheck,
    "record": dispatch.do_record,
    "sign": dispatch.do_sign,
}


def _completion(shell: str) -> str:
    if shell != "bash":
        return f"# completion not available for shell: {shell}"
    names = " ".join(sorted(verbs()))
    return ("_ret_complete() {\n"
            "    local cur\n"
            "    cur=${COMP_WORDS[COMP_CWORD]}\n"
            f"    COMPREPLY=( $(compgen -W \"{names}\" -- \"$cur\") )\n"
            "}\n"
            "complete -F _ret_complete ret")


def _version_line() -> str:
    import platform
    return f"ret {_VERSION} (CPython {platform.python_version()}, {sys.platform})"


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if not argv:
        print(_top_help())
        return 0

    first = argv[0]

    if first in ("-h", "--help"):
        print(_top_help())
        return 0
    if first == "--version":
        print(_version_line())
        return 0

    known = verbs()
    if first not in known:
        match = difflib.get_close_matches(first, PORCELAIN, n=1)
        hint = f" Did you mean {match[0]!r}?" if match else ""
        print(f"ret: {first}: {first!r} is not a ret command.{hint}", file=sys.stderr)
        return 2

    verb = first
    rest = argv[1:]

    if verb == "help":
        topic = None
        show_all = False
        for tok in rest:
            if tok in ("-a", "--all"):
                show_all = True
            elif not tok.startswith("-"):
                topic = tok
        if show_all:
            print(_help_all())
            return 0
        if topic == "environment":
            print(_ENV_DOC)
            return 0
        if topic:
            print(_detail_help(topic))
            return 0
        print(_top_help())
        return 0

    if verb == "completion":
        shell = rest[0] if rest else "bash"
        print(_completion(shell))
        return 0

    if verb == "hook":
        c_dir = "."
        it = iter(rest)
        for tok in it:
            if tok in ("-C", "--dir"):
                c_dir = next(it, ".")
        return dispatch.do_hook(argparse.Namespace(C=c_dir))

    if "-h" in rest:
        print(_concise_help(verb))
        return 0
    if "--help" in rest:
        print(_detail_help(verb))
        return 0

    parser = _build_parser(verb)
    try:
        args = parser.parse_args(rest)
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 2
        return code if code else 0

    handler = _ROUTES.get(verb)
    if handler is None:
        print(f"ret: {verb}: no such command", file=sys.stderr)
        return 2

    try:
        return handler(args)
    except Exception as e:  # noqa: BLE001 -- a refusal, never a raw traceback
        print(f"ret: {verb}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
