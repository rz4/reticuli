"""Implement the command-line verbs over the public Reticuli modules."""

from __future__ import annotations

import os
import sys

from reticuli import assess, attest, authoring, hooks, kernel, pack, record, registry, transfer
from . import handlers, output, parser, report, statusview, views


def _present(name, result, args, *, ok=None, status=None):
    if ok is None:
        ok = bool(result.get("ok", True)) if isinstance(result, dict) else True
    if status is None:
        status = result.get("verdict", "ok" if ok else "failed") if isinstance(result, dict) else "ok"
    output._finish(name, result, ok, status, args)
    return 0 if ok else 1


def _handle_help(args):
    if getattr(args, "all", False):
        parser._help_all()
    else:
        parser._help_topic(getattr(args, "topic", None))
    return 0


def _handle_init(args):
    result = handlers.init(getattr(args, "workspace", "."),
                           no_agent=getattr(args, "no_agent", False))
    return _present("init", result, args)


def _handle_completion(args):
    parser._completion(args.shell)
    return 0


def _handle_hook(args):
    return hooks.main()


def _handle_run(args):
    words = getattr(args, "command_line", None)
    if words is None:
        words = getattr(args, "command", None)
    if isinstance(words, str):
        command = words
    else:
        words = list(words or [])
        if words[:1] == ["--"]:
            words = words[1:]
        command = " ".join(words)
    if not command:
        output._err("run", "a command is required")
        return 2
    return handlers.run(command, getattr(args, "workspace", "."))


def _handle_verify(args):
    return _present("verify", kernel.verify(getattr(args, "claim", ".")), args)


def _handle_assess(args):
    result = assess.assess(getattr(args, "claim", "."),
                           mutants=getattr(args, "mutants", 20))
    return _present("assess", result, args)


def _handle_rebuild(args):
    producer = handlers._expand_producer(args.producer)
    result = kernel.rebuild(args.claim, producer, args.into,
                            guidance=not getattr(args, "without_guidance", False))
    return _present("rebuild", result, args)


def _handle_pull(args):
    result = registry.pull(args.claim, getattr(args, "workspace", "."))
    return _present("pull", result, args)


def _handle_sign(args):
    if getattr(args, "check", False):
        result = attest.sign_check(args.claim, signers=os.environ.get("RETICULI_SIGNERS"))
        return _present("sign check", result, args)
    if not getattr(args, "key", None) or not getattr(args, "identity", None):
        output._err("sign", "--key and --as are required")
        return 2
    return _present("sign", attest.sign(args.claim, args.key, args.identity), args)


def _handle_export(args):
    result = transfer.export(args.claim, args.archive, blind=getattr(args, "blind", False))
    return _present("export", result, args)


def _handle_record(args):
    if getattr(args, "check", False):
        path = getattr(args, "output", None) or args.claim
        anchor = os.environ.get("RETICULI_SIGNERS")
        ok = bool(anchor and record.signer(path, anchor))
        return _present("record", {"ok": ok, "path": path}, args)
    destination = getattr(args, "output", None)
    if not destination:
        output._err("record", "--output is required")
        return 2
    document = record.emit(args.claim)
    record.write(document, destination)
    if getattr(args, "key", None):
        record.sign(destination, args.key)
    return _present("record", {"ok": True, "root": document["root"],
                                "path": destination}, args)


def _handle_import(args):
    return _present("import", transfer.import_(args.archive, args.into), args)


def _dispatch_pack(args):
    # The older authoring form accepts verdict names through --accept. It
    # needs -o so that the destination is known before anything is built.
    accepted = getattr(args, "accept", False)
    destination = getattr(args, "output", None)
    if accepted and not isinstance(accepted, bool) and not destination:
        output._err("pack", "--accept requires -o/--output")
        return 2
    if accepted and not isinstance(accepted, bool):
        return _present("pack", authoring.build_claim(
            args.path, accepted, destination, name=getattr(args, "name", None),
            generated=getattr(args, "generated", None)), args)
    root = getattr(args, "root", None) or getattr(args, "path", ".")
    result = pack.pack(root, args.name, getattr(args, "generated", []),
                       getattr(args, "inputs", []), args.gate, args.gate_output,
                       inputs_manifest=getattr(args, "inputs_manifest", None),
                       environment=getattr(args, "environment", None))
    return _present("pack", result, args)


def _dispatch_audit(args):
    claim = getattr(args, "claim", ".")
    result = (kernel.audit(claim) if getattr(args, "shallow", False)
              else registry.audit_deep(claim))
    return _present("audit", result, args)


def _dispatch_status(args):
    path = getattr(args, "path", ".")
    if getattr(args, "claims", False):
        result = registry.claims(path)
        message = statusview._r_claims(result)
    elif getattr(args, "deps", False):
        result = registry.deps(path)
        message = statusview._r_deps(result)
    elif getattr(args, "tree", False):
        result = handlers._scan_workspace(path)
        message = statusview._r_tree(result)
    else:
        result = views._claim_view(path)
        message = statusview._r_status_draft(result, getattr(args, "verbose", False))
    if getattr(args, "json", False):
        output._finish("status", result, True, "ok", args)
    else:
        output._line(message)
    return 0


def _dispatch_crosscheck(args):
    result = kernel.crosscheck(args.original, args.transfer, args.rebuild,
                               mutants=getattr(args, "mutants", None))
    return _present("crosscheck", result, args, ok=result["satisfied"])


_HANDLERS = {
    "help": _handle_help, "init": _handle_init,
    "completion": _handle_completion, "hook": _handle_hook,
    "run": _handle_run, "verify": _handle_verify,
    "assess": _handle_assess, "rebuild": _handle_rebuild,
    "pull": _handle_pull, "sign": _handle_sign,
    "export": _handle_export, "record": _handle_record,
    "import": _handle_import, "pack": _dispatch_pack,
    "audit": _dispatch_audit, "status": _dispatch_status,
    "crosscheck": _dispatch_crosscheck,
}


def main(argv=None):
    grammar, _ = parser._parser()
    args = grammar.parse_args(argv)
    if args.version:
        output._line(handlers._version_line())
        return 0
    command = parser.ALIASES.get(args.command, args.command)
    if command is None:
        grammar.print_help()
        return 0
    try:
        return _HANDLERS[command](args)
    except (kernel.ClaimError, OSError, ValueError) as exc:
        output._err(command, str(exc))
        return 3


if __name__ == "__main__":
    sys.exit(main())
