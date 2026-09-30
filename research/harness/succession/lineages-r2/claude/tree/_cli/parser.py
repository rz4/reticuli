"""reticuli._cli.parser: the argv grammar (spec/layers.md, surface layer).

Fourteen porcelain verbs (`PORCELAIN`) cover authoring, composition and
transport, verification, reconstruction, and evidence; a small set of
accepted older spellings (`ALIASES`) fold onto them; three plumbing verbs
(`hook`, `help`, `completion`) round out `verbs()`. Everything else this
module needs -- the subparser for a verb, its one-line help, its detailed
help, and the shell completion word list -- is built from that same small
set of names, so none of them can drift apart from one another.

Stdlib only.
"""
import argparse
import json
import os
import sys

from .. import (attest as attest_mod, authoring, feedback, hooks, kernel,
                 pack as pack_mod, record as record_mod, registry, render, transfer)
from ..assess import assess as assess_mod
from . import handlers, output, report, statusview, views

_DESC = "Reticuli records and reproduces software claims.\n\nAuthoring\n    init        initialize a workspace\n    run         run and observe a command\n    status      show work, claims, and unresolved inputs\n    pack        create a claim from a project\n\nComposition and transport\n    pull        add another claim as a dependency\n    export      write a portable claim archive\n    import      restore a claim archive\n\nVerification\n    verify      verify claim identity\n    audit       rerun acceptance criteria\n    assess      measure specification strength\n\nReconstruction\n    rebuild     rebuild an implementation from a claim\n    crosscheck  compare independent realizations\n\nEvidence\n    record      write an execution record\n    sign        authorize a claim or proof"

_EPILOG = "See 'ret <command> -h' for command usage.\nSee 'ret help <command>' for detailed help; 'ret help -a' lists everything,\nincluding accepted older spellings."

# the fourteen porcelain verbs, grouped in the same order as _DESC
PORCELAIN = (
    "init", "run", "status", "pack",
    "pull", "export", "import",
    "verify", "audit", "assess",
    "rebuild", "crosscheck",
    "record", "sign",
)

# accepted older spellings that fold onto a porcelain verb. Every name in
# checks/parser_check.py's RETIRED tuple is deliberately absent: those verbs
# are gone, not aliased.
ALIASES = {
    "ls": "status",
}

_PLUMBING = ("hook", "help", "completion")

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
    "hook": "internal: translate one coding-agent hook payload",
    "help": "show detailed help for a command",
    "completion": "print a shell completion script",
}

_FULL_HELP = {
    verb: f"{verb}\n    {_VERB_HELP[verb]}\n\nSee 'ret {verb} -h' for the full option list."
    for verb in PORCELAIN + _PLUMBING
}


def verbs() -> set:
    """Every argv token the parser recognizes as a command: the porcelain
    verbs, their accepted older spellings, and the three plumbing verbs."""
    return set(PORCELAIN) | set(ALIASES) | set(_PLUMBING)


def _add_verbose_json(p) -> None:
    """The output-shaping flags every verb accepts: `--json` (the machine
    envelope), `--verbose` (extra detail in the human report), and
    `--color` (`reticuli._cli.output`'s tty-aware default)."""
    p.add_argument("--json", action="store_true", help="emit the machine-readable envelope")
    p.add_argument("--verbose", action="store_true", help="print extra detail in the human report")
    p.add_argument("--color", choices=("auto", "always", "never"), default="auto",
                   help="colorize human-facing output")


# ---------------------------------------------------------------------------
# per-verb arguments
# ---------------------------------------------------------------------------

def _add_init_args(sp):
    sp.add_argument("workspace", nargs="?", default=os.getcwd())
    sp.add_argument("--producer")
    sp.add_argument("--no-agent", action="store_true", dest="no_agent")


def _add_run_args(sp):
    sp.add_argument("cmd")
    sp.add_argument("--ws", default=os.getcwd())


def _add_status_args(sp):
    sp.add_argument("claim", nargs="?", default=os.getcwd())
    sp.add_argument("--tree", action="store_true")
    sp.add_argument("--claims", action="store_true")
    sp.add_argument("--deps", action="store_true")
    sp.add_argument("--draft", action="store_true")


def _add_pack_args(sp):
    sp.add_argument("root")
    sp.add_argument("--name")
    sp.add_argument("--generated", nargs="*", default=[])
    sp.add_argument("--inputs", nargs="*", default=[])
    sp.add_argument("--gate")
    sp.add_argument("--gate-output", dest="gate_output")
    sp.add_argument("--envelope", nargs="*", default=[], metavar="KEY=VALUE")
    sp.add_argument("--format", type=int, default=None)
    sp.add_argument("--component-name", dest="component_name")
    sp.add_argument("--component-claim", dest="component_claim")
    sp.add_argument("--component-outputs", dest="component_outputs", nargs="*", default=[])
    sp.add_argument("--accept", action="store_true",
                     help="seal a traced session (the old standalone seal verb)")
    sp.add_argument("--outputs", nargs="*", default=[], help="with --accept: the produced paths")
    sp.add_argument("--claim-paths", dest="claim_paths", nargs="*", default=None,
                     help="with --accept: paths to pin regardless of how they were traced")


def _add_pull_args(sp):
    sp.add_argument("claim")
    sp.add_argument("into")


def _add_export_args(sp):
    sp.add_argument("claim")
    sp.add_argument("out")
    sp.add_argument("--blind", action="store_true")


def _add_import_args(sp):
    sp.add_argument("archive")
    sp.add_argument("into")


def _add_verify_args(sp):
    sp.add_argument("claim", nargs="?", default=os.getcwd())


def _add_audit_args(sp):
    sp.add_argument("claim", nargs="?", default=os.getcwd())


def _add_assess_args(sp):
    sp.add_argument("claim", nargs="?", default=os.getcwd())
    sp.add_argument("--mutants", type=int, default=20)


def _add_rebuild_args(sp):
    sp.add_argument("claim")
    sp.add_argument("into")
    sp.add_argument("--producer", required=True)
    sp.add_argument("--chain", action="store_true", help="DAG-aware rebuild (registry.rebuild_chain)")
    sp.add_argument("--reuse", action="store_true", help="with --chain: reuse sealed components untouched")
    sp.add_argument("--ws")


def _add_crosscheck_args(sp):
    sp.add_argument("m1")
    sp.add_argument("m2")
    sp.add_argument("m3")
    sp.add_argument("--deep", action="store_true", help="re-earn every from-sourced layer's own gate")


def _add_record_args(sp):
    sp.add_argument("claim", nargs="?", default=os.getcwd())
    sp.add_argument("--out", help="write the record's canonical bytes here")
    sp.add_argument("--key", help="sign the written record with this ssh key")
    sp.add_argument("--check", help="read back the signer of a record file instead of emitting one")
    sp.add_argument("--anchor", help="with --check: the allowed-signers file")


def _add_sign_args(sp):
    sp.add_argument("claim", nargs="?", default=os.getcwd())
    sp.add_argument("--key", help="the ssh key authorizing this claim")
    sp.add_argument("--as", dest="identity", help="the signer's identity")
    sp.add_argument("--check", action="store_true", help="read back authorizations instead of signing")
    sp.add_argument("--signers", help="with --check: the allowed-signers file")
    sp.add_argument("--ws", help="the registry workspace, for the component-aware sign root")


_ADDERS = {verb: globals()[f"_add_{verb}_args"] for verb in PORCELAIN}


# ---------------------------------------------------------------------------
# the parser itself
# ---------------------------------------------------------------------------

def _parser():
    """The top-level `ret` parser, and a `{verb: subparser}` map -- the one
    grammar every other function here (`verbs`, `_help_topic`, `_completion`)
    is read from, so none of them can drift out of step with it."""
    p = argparse.ArgumentParser(
        prog="ret", description=_DESC, epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="verb", metavar="command")
    subparsers = {}

    for verb in PORCELAIN:
        aliases = sorted(a for a, canonical in ALIASES.items() if canonical == verb)
        sp = sub.add_parser(verb, aliases=aliases, help=_VERB_HELP[verb])
        _add_verbose_json(sp)
        _ADDERS[verb](sp)
        subparsers[verb] = sp

    hook_sp = sub.add_parser("hook", help=_VERB_HELP["hook"])
    subparsers["hook"] = hook_sp

    help_sp = sub.add_parser("help", help=_VERB_HELP["help"])
    help_sp.add_argument("topic", nargs="?")
    help_sp.add_argument("-a", "--all", action="store_true")
    subparsers["help"] = help_sp

    completion_sp = sub.add_parser("completion", help=_VERB_HELP["completion"])
    completion_sp.add_argument("shell", choices=("bash",))
    subparsers["completion"] = completion_sp

    return p, subparsers


# ---------------------------------------------------------------------------
# help: 'ret help <command>' and 'ret help -a'
# ---------------------------------------------------------------------------

def _help_topic(topic: str) -> None:
    """The detailed help for one command, or its accepted older spelling."""
    canonical = ALIASES.get(topic, topic)
    text = _FULL_HELP.get(canonical)
    if text is None:
        print(f"no help for {topic!r}", file=sys.stderr)
        return
    print(text)


def _help_all() -> None:
    """Every command this parser recognizes: the porcelain groups (`_DESC`),
    the plumbing, and every accepted older spelling."""
    print(_DESC)
    print()
    print("Plumbing")
    for verb in _PLUMBING:
        print(f"    {verb:<11} {_VERB_HELP[verb]}")
    if ALIASES:
        print()
        print("Accepted older spellings")
        for alias in sorted(ALIASES):
            print(f"    {alias:<11} -> {ALIASES[alias]}")


# ---------------------------------------------------------------------------
# completion: generated from the grammar, so it cannot drift
# ---------------------------------------------------------------------------

def _completion(shell: str) -> None:
    """Print a shell completion script whose word list is `verbs()` itself."""
    if shell != "bash":
        raise ValueError(f"unsupported shell: {shell!r}")
    words = " ".join(sorted(verbs()))
    print(
        "_ret_complete() {\n"
        "    local cur\n"
        '    cur="${COMP_WORDS[COMP_CWORD]}"\n'
        '    if [ "$COMP_CWORD" -eq 1 ]; then\n'
        f'        COMPREPLY=( $(compgen -W "{words}" -- "$cur") )\n'
        "    fi\n"
        "}\n"
        "complete -F _ret_complete ret"
    )


# ---------------------------------------------------------------------------
# dispatch: one _cmd_<verb> per porcelain verb, plus the plumbing
# ---------------------------------------------------------------------------

def _run_verb(cmd: str, fn, args, *, root=None) -> int:
    """Call `fn`, then hand its result to `output._finish` -- the one path
    every porcelain verb's result reaches the envelope or the console
    through. A `kernel.ClaimError` becomes the one-voice error line, never a
    raw traceback."""
    try:
        data = fn()
    except kernel.ClaimError as e:
        output._err(cmd, str(e))
        return 1
    ok = bool(data.get("ok", True)) if isinstance(data, dict) else True
    output._finish(cmd, data, ok, "ok" if ok else "failed", args, root=root)
    return 0 if ok else 1


def _cmd_init(args):
    return _run_verb("init", lambda: handlers.init(
        args.workspace, producer=args.producer, no_agent=args.no_agent), args)


def _cmd_run(args):
    rc = handlers.run(args.cmd, args.ws)
    if getattr(args, "json", False):
        output._finish("run", {"returncode": rc}, rc == 0, "ok" if rc == 0 else "failed", args)
    return rc


def _cmd_status(args):
    d = args.claim
    try:
        if args.tree:
            payload = {"lines": statusview._r_tree(d).split("\n")}
        elif args.claims:
            payload = {"lines": statusview._r_claims(d)}
        elif args.deps:
            payload = {"lines": statusview._r_deps(d)}
        elif args.draft:
            payload = {"lines": statusview._r_status_draft(d)}
        else:
            payload = {"lines": statusview._v_status_claim(d), **views._claim_view(d)}
    except kernel.ClaimError as e:
        output._err("status", str(e))
        return 1
    if getattr(args, "json", False):
        output._finish("status", payload, True, "ok", args, root=payload.get("root"))
    else:
        for line in payload["lines"]:
            print(line)
    return 0


def _cmd_pack(args):
    def go():
        if args.accept:
            return authoring.build_claim(
                args.root, args.outputs, args.root, name=args.name,
                claim=args.claim_paths, generated=None)
        component = None
        if args.component_name:
            component = {"name": args.component_name, "claim": args.component_claim,
                         "outputs": args.component_outputs}
        envelope = dict(kv.split("=", 1) for kv in args.envelope) if args.envelope else None
        return pack_mod.pack(
            args.root, args.name, args.generated, args.inputs, args.gate, args.gate_output,
            envelope=envelope, claim_format=args.format, component=component)
    return _run_verb("pack", go, args)


def _cmd_pull(args):
    return _run_verb("pull", lambda: registry.pull(args.claim, args.into), args)


def _cmd_export(args):
    return _run_verb("export", lambda: transfer.export(args.claim, args.out, blind=args.blind), args)


def _cmd_import(args):
    return _run_verb("import", lambda: transfer.import_(args.archive, args.into), args)


def _cmd_verify(args):
    return _run_verb("verify", lambda: kernel.verify(args.claim), args)


def _cmd_audit(args):
    return _run_verb("audit", lambda: kernel.audit(args.claim), args)


def _cmd_assess(args):
    return _run_verb("assess", lambda: assess_mod(args.claim, mutants=args.mutants), args)


def _cmd_rebuild(args):
    def go():
        if args.chain:
            return registry.rebuild_chain(args.claim, args.producer, args.into,
                                          ws=args.ws, reuse=args.reuse)
        return kernel.rebuild(args.claim, args.producer, args.into)
    return _run_verb("rebuild", go, args)


def _cmd_crosscheck(args):
    def go():
        if args.deep:
            return registry.crosscheck_deep(args.m1, args.m2, args.m3)
        return kernel.crosscheck(args.m1, args.m2, args.m3)
    return _run_verb("crosscheck", go, args)


def _cmd_record(args):
    def go():
        if args.check:
            signer = record_mod.signer(args.check, args.anchor)
            return {"ok": signer is not None, "signer": signer}
        doc = record_mod.emit(args.claim)
        if args.out:
            record_mod.write(doc, args.out)
            if args.key:
                record_mod.sign(args.out, args.key)
        return doc
    return _run_verb("record", go, args)


def _cmd_sign(args):
    def go():
        if args.check:
            return attest_mod.sign_check(args.claim, ws=args.ws, signers=args.signers)
        return attest_mod.sign(args.claim, args.key, args.identity, ws=args.ws)
    return _run_verb("sign", go, args)


def _cmd_hook(args):
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        return 0
    try:
        hooks.event(payload)
    except OSError:
        pass
    return 0


def _cmd_completion(args):
    _completion(args.shell)
    return 0


_DISPATCH = {
    "init": _cmd_init, "run": _cmd_run, "status": _cmd_status, "pack": _cmd_pack,
    "pull": _cmd_pull, "export": _cmd_export, "import": _cmd_import,
    "verify": _cmd_verify, "audit": _cmd_audit, "assess": _cmd_assess,
    "rebuild": _cmd_rebuild, "crosscheck": _cmd_crosscheck,
    "record": _cmd_record, "sign": _cmd_sign,
    "hook": _cmd_hook, "completion": _cmd_completion,
}


def main(argv=None) -> int:
    p, _subparsers = _parser()
    args = p.parse_args(argv)
    verb = getattr(args, "verb", None)
    if verb is None:
        p.print_help()
        return 0
    canonical = ALIASES.get(verb, verb)
    if canonical == "help":
        if args.all:
            _help_all()
        elif args.topic:
            _help_topic(args.topic)
        else:
            p.print_help()
        return 0
    return _DISPATCH[canonical](args)


if __name__ == "__main__":
    sys.exit(main())
