"""Operations behind the ``ret`` command-line verbs."""

from __future__ import annotations

import os
import sys

from reticuli import assess, attest, hooks, kernel, pack, record, registry, transfer
from . import handlers, output, parser, report, statusview


def _value(args, name, default=None):
    return getattr(args, name, default)


def _handle_help(args):
    if _value(args, "all", False):
        parser._help_all()
    elif _value(args, "topic"):
        parser._help_topic(args.topic)
    else:
        parser._parser()[0].print_help()
    return 0


def _handle_completion(args):
    parser._completion(args.shell)
    return 0


def _handle_hook(args):
    return hooks.main()


def _handle_init(args):
    workspace = _value(args, "workspace", ".")
    handlers.init(workspace, no_agent=_value(args, "no_agent", False))
    if not _value(args, "no_agent", False):
        hooks.install(workspace)
    return report._r_init({"ok": True, "path": os.fspath(workspace)}, args)


def _handle_run(args):
    workspace = _value(args, "workspace", ".")
    command = _value(args, "command", [])
    if isinstance(command, (list, tuple)):
        command = " ".join(command)
    if not command:
        output._err("run", "a command is required")
        return 2
    # Running a command is useful even in a plain directory. Initialise the
    # local trace store so the command's exact status can be recorded.
    handlers.init(workspace)
    return handlers.run(command, workspace)


def _handle_verify(args):
    return report._r_verify(kernel.verify(_value(args, "claim", ".")), args)


def _dispatch_audit(args):
    claim = _value(args, "claim", ".")
    if _value(args, "shallow", False):
        result = kernel.audit(claim)
    else:
        result = registry.audit_deep(claim)
    return report._r_audit(result, args)


def _handle_assess(args):
    result = assess.assess(_value(args, "claim", "."), mutants=_value(args, "mutants", 100))
    ok = result["audit"]["ok"]
    return output._finish("assess", result, ok, "ok" if ok else "failed", args)


def _handle_rebuild(args):
    producer = _value(args, "producer") or os.environ.get("RETICULI_PRODUCER")
    if not producer:
        output._err("rebuild", "a producer is required")
        return 2
    producer = handlers._expand_producer(producer)
    claim, into = args.claim, args.into
    if _value(args, "reuse", False):
        result = registry.rebuild_chain(claim, producer, into, reuse=True)
    else:
        result = kernel.rebuild(claim, producer, into,
                                guidance=not _value(args, "without_guidance", False))
    return report._r_rebuild(result, args)


def _handle_pull(args):
    return report._r_pull(registry.pull(args.claim, _value(args, "workspace", ".")), args)


def _handle_sign(args):
    claim = _value(args, "claim", ".")
    if _value(args, "check", False):
        result = attest.sign_check(claim, signers=_value(args, "anchor"))
        return report._r_sign_check(result, args)
    if not _value(args, "key") or not _value(args, "identity"):
        output._err("sign", "--key and --as are required")
        return 2
    return report._r_sign(attest.sign(claim, args.key, args.identity), args)


def _handle_export(args):
    path = transfer.export(args.claim, args.archive, blind=_value(args, "blind", False))
    return report._r_export({"ok": True, "path": path}, args)


def _handle_record(args):
    if _value(args, "check", False):
        anchor = _value(args, "anchor")
        signer = record.signer(args.claim, anchor) if anchor else None
        return report._r_record({"ok": signer is not None, "signer": signer}, args)
    if not _value(args, "into"):
        output._err("record", "--into is required")
        return 2
    doc = record.emit(_value(args, "claim", "."))
    record.write(doc, args.into)
    if _value(args, "key"):
        record.sign(args.into, args.key)
    return report._r_record({"ok": True, "path": args.into, "root": doc["root"]}, args)


def _handle_import(args):
    return report._r_import(transfer.import_(args.archive, args.into), args)


def _dispatch_pack(args):
    # The older pack spelling used ``-o`` for the claim destination. Keep
    # this guard at the dispatch boundary: accepting without a destination
    # must not create or seal a claim accidentally.
    if _value(args, "accept") and not (_value(args, "output") or _value(args, "into") or _value(args, "gate_output")):
        output._err("pack", "--accept requires -o/--output")
        return 2
    project = _value(args, "project", _value(args, "path", "."))
    gate = _value(args, "gate")
    gate_output = _value(args, "gate_output", _value(args, "output"))
    generated = _value(args, "generated") or []
    if isinstance(generated, str):
        generated = [generated]
    inputs = _value(args, "input", []) or []
    if not generated or not gate or not gate_output:
        output._err("pack", "--generated, --gate, and -o/--output are required")
        return 2
    result = pack.pack(project, _value(args, "name") or os.path.basename(os.path.abspath(project)),
                       generated, inputs, gate, gate_output,
                       claim_format=_value(args, "claim_format") or 3,
                       mutation_floor=_value(args, "mutation_floor"),
                       inputs_manifest=_value(args, "inputs_manifest"),
                       environment=_value(args, "environment"), by=_value(args, "by"))
    return report._r_pack(result, args)


def _dispatch_status(args):
    path = _value(args, "path", ".")
    if _value(args, "claims", False):
        return statusview._r_claims(registry.claims(path), args)
    if _value(args, "deps", False):
        return statusview._r_deps(registry.deps(path), args)
    if _value(args, "tree", False):
        return statusview._r_tree(registry.structure(path), args)
    view = statusview._v_status_claim(path)
    if _value(args, "files", False):
        view["files"] = statusview._files_claim(path)
    return output._finish("status", view, True, view["phase"], args)


def _dispatch_crosscheck(args):
    kwargs = {"mutants": _value(args, "mutants")}
    if _value(args, "record_proof", False):
        result = kernel.record_proof(args.m1, args.m2, args.m3, **kwargs)
    else:
        result = kernel.crosscheck(args.m1, args.m2, args.m3, **kwargs)
    ok = result.get("proof_recorded", False) if _value(args, "record_proof", False) else result.get("satisfied", False)
    return output._finish("crosscheck", result, ok, "accept" if ok else "failed", args)


def main(argv=None):
    root, _ = parser._parser()
    args = root.parse_args(argv)
    verb = parser.ALIASES.get(args.verb, args.verb)
    routes = {
        "help": _handle_help, "completion": _handle_completion,
        "hook": _handle_hook, "init": _handle_init, "run": _handle_run,
        "verify": _handle_verify, "audit": _dispatch_audit,
        "assess": _handle_assess, "rebuild": _handle_rebuild,
        "pull": _handle_pull, "sign": _handle_sign,
        "export": _handle_export, "record": _handle_record,
        "import": _handle_import, "pack": _dispatch_pack,
        "status": _dispatch_status, "crosscheck": _dispatch_crosscheck,
    }
    if verb is None:
        root.print_help()
        return 0
    try:
        return routes[verb](args)
    except (kernel.ClaimError, OSError, ValueError) as exc:
        output._err(verb, str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
