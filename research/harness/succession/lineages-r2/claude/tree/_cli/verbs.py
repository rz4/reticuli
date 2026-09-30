"""reticuli._cli.verbs: the porcelain verb handlers (spec/layers.md, surface layer).

Every porcelain verb this CLI understands reduces to one function here: a
`_handle_*` that does the verb's own work and hands back a plain result dict
for `main()` to route through the `--json` envelope, or a `_dispatch_*` for a
verb whose surface covers more than one mode and therefore owns its own exit
code and error report instead of a single uniform result shape. `main()`
parses argv and routes to whichever of the two applies.

Two behaviors are pinned directly here, independent of the assembled CLI's
own end-to-end suite: `_handle_run` returns the child's exit code UNCHANGED
-- the predicate contract, so a session's own driver can use it without
translation -- and `_dispatch_pack` refuses `--accept` without `-o`, in
words, with exit 2, before anything is built: a usage error is not a failed
build and must not touch the filesystem on its way to being reported.

Stdlib only.
"""
import argparse
import json
import os
import sys

from .. import (attest as attest_mod, authoring, hooks, kernel,
                 pack as pack_mod, record as record_mod, registry, transfer)
from ..assess import assess as assess_mod
from . import handlers, output, statusview, views

VERBS = ("init", "run", "status", "pack", "pull", "export", "import",
          "verify", "audit", "assess", "rebuild", "crosscheck", "record", "sign")
PLUMBING = ("hook", "help", "completion")

# handlers whose own contract is an exit code, not a result dict for the
# envelope -- `run` (the predicate contract), and the three plumbing verbs,
# which speak only to a terminal or a hook pipe, never to a script's --json
_INT_HANDLERS = frozenset({"run", "hook", "completion", "help"})


# ---------------------------------------------------------------------------
# handlers: one result dict apiece, the four in `_INT_HANDLERS` excepted
# ---------------------------------------------------------------------------

def _handle_init(args) -> dict:
    return handlers.init(args.workspace, producer=getattr(args, "producer", None),
                          no_agent=getattr(args, "no_agent", False))


def _handle_run(args) -> int:
    """Run `args.command` (argv tokens joined into one shell line) inside
    `args.workspace`; return the child's exit code UNCHANGED -- never
    translated, never swallowed (the predicate contract this verb alone
    carries)."""
    return handlers.run(" ".join(args.command), args.workspace)


def _handle_completion(args) -> int:
    _print_completion(args.shell)
    return 0


def _handle_hook(args) -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        return 0
    try:
        hooks.event(payload)
    except OSError:
        pass
    return 0


def _handle_help(args) -> int:
    if getattr(args, "all", False) or not getattr(args, "topic", None):
        _print_help_all()
    else:
        _print_help_topic(args.topic)
    return 0


def _handle_verify(args) -> dict:
    return kernel.verify(args.claim)


def _handle_assess(args) -> dict:
    return assess_mod(args.claim, mutants=getattr(args, "mutants", 20))


def _handle_rebuild(args) -> dict:
    if getattr(args, "chain", False):
        return registry.rebuild_chain(args.claim, args.producer, args.into,
                                       ws=getattr(args, "ws", None),
                                       reuse=getattr(args, "reuse", False))
    return kernel.rebuild(args.claim, args.producer, args.into)


def _handle_pull(args) -> dict:
    return registry.pull(args.claim, args.into)


def _handle_sign(args) -> dict:
    if getattr(args, "check", False):
        return attest_mod.sign_check(args.claim, ws=getattr(args, "ws", None),
                                      signers=getattr(args, "signers", None))
    return attest_mod.sign(args.claim, args.key, args.identity, ws=getattr(args, "ws", None))


def _handle_export(args) -> dict:
    return transfer.export(args.claim, args.out, blind=getattr(args, "blind", False))


def _handle_record(args) -> dict:
    """Emit a fresh record for `args.claim`, optionally writing (and
    signing) it to `args.out` -- or, with `--check <path>`, read back who
    signed an existing record file instead of emitting a new one."""
    check = getattr(args, "check", None)
    if check:
        signer = record_mod.signer(check, getattr(args, "anchor", None))
        return {"ok": signer is not None, "signer": signer}
    doc = record_mod.emit(args.claim)
    out = getattr(args, "out", None)
    if out:
        record_mod.write(doc, out)
        key = getattr(args, "key", None)
        if key:
            record_mod.sign(out, key)
    return doc


def _handle_import(args) -> dict:
    return transfer.import_(args.archive, args.into)


HANDLERS = {
    "init": _handle_init, "run": _handle_run, "completion": _handle_completion,
    "hook": _handle_hook, "help": _handle_help, "verify": _handle_verify,
    "assess": _handle_assess, "rebuild": _handle_rebuild, "pull": _handle_pull,
    "sign": _handle_sign, "export": _handle_export, "record": _handle_record,
    "import": _handle_import,
}


# ---------------------------------------------------------------------------
# dispatches: multi-mode verbs that own their own exit code and error report
# ---------------------------------------------------------------------------

def _dispatch_pack(args) -> int:
    """`pack` covers two modes. `--accept <output...>` certifies a TRACED
    session (`authoring.build_claim`) and needs `-o`/`--output` to say
    where the resulting claim is written -- refused, in words, with exit 2,
    BEFORE anything is built, when it is missing: a usage error, not a
    failed build. Without `--accept`, `pack` builds a fresh self-claim from
    glob patterns (`pack.pack`)."""
    accept = getattr(args, "accept", None)
    if accept:
        output_dir = getattr(args, "output", None)
        if not output_dir:
            output._err("pack", "--accept needs -o/--output naming the claim to write")
            return 2
        try:
            result = authoring.build_claim(
                args.path, list(accept), output_dir,
                name=getattr(args, "name", None), generated=getattr(args, "generated", None))
        except kernel.ClaimError as e:
            output._err("pack", str(e))
            return 1
    else:
        name = getattr(args, "name", None)
        gate = getattr(args, "gate", None) or (
            "python3 -m pytest -q" if getattr(args, "pytest", False) else None)
        if not name or not gate:
            output._err("pack", "pack needs --name and --gate, or --accept with -o")
            return 2
        gate_output = getattr(args, "output", None) or "OK"
        recipe_path = os.path.join(args.path, kernel.RECIPE)
        if os.path.isfile(recipe_path) and not getattr(args, "force", False):
            output._err("pack", f"{recipe_path!r} already exists; pass --force to overwrite")
            return 1
        try:
            result = pack_mod.pack(args.path, name, getattr(args, "generated", None) or [],
                                    [], gate, gate_output)
        except kernel.ClaimError as e:
            output._err("pack", str(e))
            return 1
        into = getattr(args, "into", None)
        if into:
            try:
                registry.pull(args.path, into)
            except kernel.ClaimError as e:
                output._err("pack", str(e))
                return 1

    expected_root = getattr(args, "root", None)
    if expected_root and result.get("root") != expected_root:
        output._err("pack", f"sealed root {result.get('root')} != expected {expected_root}")
        return 1
    output._finish("pack", result, True, "ok", args, root=result.get("root"))
    return 0


def _dispatch_audit(args) -> int:
    """`audit` recurses into composed claims by default -- a `from`-sourced
    layer must re-earn its own gate on the dependent's shipped bytes
    (`registry.audit_deep`), not merely pass along a carried verdict;
    `--shallow` opts out to the kernel's own, non-recursive audit."""
    d = args.claim
    try:
        base = kernel.audit(d)
        if getattr(args, "shallow", False):
            result = base
        else:
            deep = registry.audit_deep(d)
            result = {**base, "ok": base["ok"] and deep["ok"], "deep": deep}
    except kernel.ClaimError as e:
        output._err("audit", str(e))
        return 1
    ok = bool(result.get("ok", True))
    output._finish("audit", result, ok, "ok" if ok else "failed", args, root=result.get("root"))
    return 0 if ok else 1


def _dispatch_status(args) -> int:
    """`status` reads one of several views of a claim, chosen by which flag
    is set -- the claim's own state by default (`views._claim_view`)."""
    d = args.claim
    try:
        if getattr(args, "tree", False):
            payload = {"lines": statusview._r_tree(d).split("\n")}
        elif getattr(args, "claims", False):
            payload = {"lines": statusview._r_claims(d)}
        elif getattr(args, "deps", False):
            payload = {"lines": statusview._r_deps(d)}
        elif getattr(args, "draft", False):
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


def _dispatch_crosscheck(args) -> int:
    """`crosscheck` is the three-machine test; `--deep` additionally
    re-earns every `from`-sourced layer's own gate on each leg's shipped
    bytes (`registry.crosscheck_deep`)."""
    try:
        if getattr(args, "deep", False):
            result = registry.crosscheck_deep(args.m1, args.m2, args.m3)
        else:
            result = kernel.crosscheck(args.m1, args.m2, args.m3)
    except kernel.ClaimError as e:
        output._err("crosscheck", str(e))
        return 1
    ok = bool(result.get("satisfied", False))
    output._finish("crosscheck", result, ok, result.get("verdict", "incomplete"), args)
    return 0 if ok else 1


DISPATCHES = {
    "pack": _dispatch_pack, "audit": _dispatch_audit,
    "status": _dispatch_status, "crosscheck": _dispatch_crosscheck,
}


# ---------------------------------------------------------------------------
# help / completion text -- built from `VERBS`/`PLUMBING` alone, so neither
# can drift out of step with the parser below
# ---------------------------------------------------------------------------

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


def _print_help_all() -> None:
    print("Reticuli records and reproduces software claims.\n")
    for verb in VERBS:
        print(f"    {verb:<11} {_VERB_HELP[verb]}")
    print("\nPlumbing")
    for verb in PLUMBING:
        print(f"    {verb:<11} {_VERB_HELP[verb]}")


def _print_help_topic(topic: str) -> None:
    text = _VERB_HELP.get(topic)
    if text is None:
        print(f"no help for {topic!r}", file=sys.stderr)
        return
    print(f"{topic}\n    {text}\n\nSee 'ret {topic} -h' for the full option list.")


def _print_completion(shell: str) -> None:
    if shell != "bash":
        raise ValueError(f"unsupported shell: {shell!r}")
    words = " ".join(sorted(set(VERBS) | set(PLUMBING)))
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
# the parser, and main(): route argv to a handler or a dispatch
# ---------------------------------------------------------------------------

def _add_common(sp) -> None:
    sp.add_argument("--json", action="store_true")
    sp.add_argument("--verbose", action="store_true")
    sp.add_argument("--color", choices=("auto", "always", "never"), default="auto")


def _build_parser():
    p = argparse.ArgumentParser(prog="ret")
    sub = p.add_subparsers(dest="verb", metavar="command")

    sp = sub.add_parser("init"); _add_common(sp)
    sp.add_argument("workspace", nargs="?", default=os.getcwd())
    sp.add_argument("--producer")
    sp.add_argument("--no-agent", action="store_true", dest="no_agent")

    sp = sub.add_parser("run"); _add_common(sp)
    sp.add_argument("workspace", nargs="?", default=os.getcwd())
    sp.add_argument("command", nargs=argparse.REMAINDER)

    sp = sub.add_parser("status"); _add_common(sp)
    sp.add_argument("claim", nargs="?", default=os.getcwd())
    sp.add_argument("--tree", action="store_true")
    sp.add_argument("--claims", action="store_true")
    sp.add_argument("--deps", action="store_true")
    sp.add_argument("--draft", action="store_true")

    sp = sub.add_parser("pack"); _add_common(sp)
    sp.add_argument("path")
    sp.add_argument("--name")
    sp.add_argument("--root")
    sp.add_argument("--generated", nargs="*", default=[])
    sp.add_argument("--gate")
    sp.add_argument("-o", "--output")
    sp.add_argument("--pytest", action="store_true")
    sp.add_argument("--accept", nargs="*", default=None)
    sp.add_argument("--into")
    sp.add_argument("--force", action="store_true")

    sp = sub.add_parser("pull"); _add_common(sp)
    sp.add_argument("claim")
    sp.add_argument("into")

    sp = sub.add_parser("export"); _add_common(sp)
    sp.add_argument("claim")
    sp.add_argument("out")
    sp.add_argument("--blind", action="store_true")

    sp = sub.add_parser("import"); _add_common(sp)
    sp.add_argument("archive")
    sp.add_argument("into")

    sp = sub.add_parser("verify"); _add_common(sp)
    sp.add_argument("claim", nargs="?", default=os.getcwd())

    sp = sub.add_parser("audit"); _add_common(sp)
    sp.add_argument("claim", nargs="?", default=os.getcwd())
    sp.add_argument("--shallow", action="store_true")

    sp = sub.add_parser("assess"); _add_common(sp)
    sp.add_argument("claim", nargs="?", default=os.getcwd())
    sp.add_argument("--mutants", type=int, default=20)

    sp = sub.add_parser("rebuild"); _add_common(sp)
    sp.add_argument("claim")
    sp.add_argument("into")
    sp.add_argument("--producer", required=True)
    sp.add_argument("--chain", action="store_true")
    sp.add_argument("--reuse", action="store_true")
    sp.add_argument("--ws")

    sp = sub.add_parser("crosscheck"); _add_common(sp)
    sp.add_argument("m1")
    sp.add_argument("m2")
    sp.add_argument("m3")
    sp.add_argument("--deep", action="store_true")

    sp = sub.add_parser("record"); _add_common(sp)
    sp.add_argument("claim", nargs="?", default=os.getcwd())
    sp.add_argument("--out")
    sp.add_argument("--key")
    sp.add_argument("--check")
    sp.add_argument("--anchor")

    sp = sub.add_parser("sign"); _add_common(sp)
    sp.add_argument("claim", nargs="?", default=os.getcwd())
    sp.add_argument("--key")
    sp.add_argument("--as", dest="identity")
    sp.add_argument("--check", action="store_true")
    sp.add_argument("--signers")
    sp.add_argument("--ws")

    sub.add_parser("hook")

    help_sp = sub.add_parser("help")
    help_sp.add_argument("topic", nargs="?")
    help_sp.add_argument("-a", "--all", action="store_true")

    completion_sp = sub.add_parser("completion")
    completion_sp.add_argument("shell", choices=("bash",))

    return p


def main(argv=None) -> int:
    p = _build_parser()
    args = p.parse_args(argv)
    verb = getattr(args, "verb", None)
    if verb is None:
        p.print_help()
        return 0

    if verb in DISPATCHES:
        return DISPATCHES[verb](args)

    fn = HANDLERS.get(verb)
    if fn is None:
        p.print_help()
        return 1
    if verb in _INT_HANDLERS:
        return fn(args)

    try:
        data = fn(args)
    except kernel.ClaimError as e:
        output._err(verb, str(e))
        return 1
    ok = bool(data.get("ok", True)) if isinstance(data, dict) else True
    root = data.get("root") if isinstance(data, dict) else None
    output._finish(verb, data, ok, "ok" if ok else "failed", args, root=root)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
