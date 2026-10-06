"""Command handlers for the ``ret`` command.

The parser owns spelling and argument types; this module turns parsed commands
into calls to the claim layers and gives each result a CLI exit status.
"""

from __future__ import annotations

import json
import os
import sys

from .. import assess, attest, hooks, kernel, pack, record, registry, transfer
from . import handlers, output, parser, report, statusview, views


def _value(args, *names, default=None):
    for name in names:
        value = getattr(args, name, None)
        if value is not None:
            return value
    return default


def _show(command, result, args=None, *, ok=None):
    if ok is None:
        ok = result.get("ok", result.get("satisfied", True)) if isinstance(result, dict) else True
    status = (result.get("status", result.get("verdict", "ok" if ok else "failed"))
              if isinstance(result, dict) else "ok" if ok else "failed")
    output._finish(command, result if isinstance(result, dict) else {"result": result},
                   ok, status, args)
    return 0 if ok else 1


def _usage(command, message):
    output._err(command, message)
    return 2


def _handle_help(args):
    if getattr(args, "all", False):
        parser._help_all()
    elif getattr(args, "topic", None):
        parser._help_topic(args.topic)
    else:
        parser._parser()[0].print_help()
    return 0


def _handle_init(args):
    root = handlers.init(_value(args, "workspace", "path", default="."),
                         no_agent=getattr(args, "no_agent", False))
    return _show("init", {"ok": True, "workspace": root}, args)


def _handle_completion(args):
    parser._completion(getattr(args, "shell", "bash"))
    return 0


def _handle_hook(args):
    payload = json.load(sys.stdin)
    if getattr(args, "event", None):
        payload.setdefault("hook_event_name", args.event)
    hooks.event(payload)
    return 0


def _handle_run(args):
    command = _value(args, "shell_command", "command", default=[])
    if isinstance(command, (list, tuple)):
        command = " ".join(command)
    if not command:
        return _usage("run", "a shell command is required")
    return handlers.run(command, _value(args, "workspace", "path", default="."))


def _handle_verify(args):
    return _show("verify", kernel.verify(_value(args, "claim", "path", default=".")), args)


def _handle_assess(args):
    result = assess.assess(_value(args, "claim", "path", default="."),
                           mutants=getattr(args, "mutants", 100))
    return _show("assess", result, args)


def _handle_rebuild(args):
    producer = handlers._expand_producer(getattr(args, "producer"))
    source = _value(args, "claim", "path")
    target = getattr(args, "into")
    result = registry.rebuild_chain(source, producer, target, reuse=True) if getattr(args, "reuse", False) else kernel.rebuild(
        source, producer, target, guidance=not getattr(args, "without_guidance", False))
    return _show("rebuild", result, args)


def _handle_pull(args):
    return _show("pull", registry.pull(args.claim, getattr(args, "workspace", ".")), args)


def _handle_sign(args):
    claim = _value(args, "claim", "path", default=".")
    if getattr(args, "check", False):
        result = attest.sign_check(claim, signers=getattr(args, "signers", None))
    else:
        if not getattr(args, "key", None) or not getattr(args, "identity", None):
            return _usage("sign", "--key and --as are required")
        result = attest.sign(claim, args.key, args.identity)
    return _show("sign", result, args)


def _handle_export(args):
    archive = transfer.export(args.claim, args.archive, blind=getattr(args, "blind", False))
    return _show("export", {"ok": True, "archive": archive}, args)


def _handle_record(args):
    claim = _value(args, "claim", "path", default=".")
    if getattr(args, "check", False):
        destination = getattr(args, "output", None)
        if not destination:
            return _usage("record", "--output is required with --check")
        document = record.read(destination)
        signer = record.signer(destination, args.signers) if getattr(args, "signers", None) else None
        return _show("record", {"ok": signer is not None, "digest": record.digest(document),
                                "signer": signer}, args)
    destination = getattr(args, "output", None)
    if not destination:
        return _usage("record", "--output is required")
    document = record.emit(claim)
    record.write(document, destination)
    if getattr(args, "key", None):
        record.sign(destination, args.key)
    return _show("record", {"ok": True, "output": destination,
                            "digest": record.digest(document)}, args)


def _handle_import(args):
    return _show("import", transfer.import_(args.archive, args.into), args)


def _dispatch_pack(args):
    # The older pack form accepts expected output words only when it has a
    # destination for the verdict. Check this before touching the project.
    if getattr(args, "accept", None) and not _value(args, "output", "gate_output"):
        return _usage("pack", "--accept requires -o/--output")
    name = getattr(args, "name", None)
    gate = getattr(args, "gate", None)
    gate_output = _value(args, "gate_output", "output")
    if not name or not gate or not gate_output:
        return _usage("pack", "--name, --gate and --gate-output are required")
    result = pack.pack(_value(args, "path", "root", default="."), name,
                       getattr(args, "generated", []) or [],
                       getattr(args, "input", []) or [], gate, gate_output,
                       claim_format=getattr(args, "claim_format", 3),
                       mutation_floor=getattr(args, "mutation_floor", None),
                       requires=getattr(args, "requires", None),
                       by=getattr(args, "by", None),
                       inputs_manifest=getattr(args, "inputs_manifest", None),
                       environment=getattr(args, "environment", None))
    return _show("pack", result, args)


def _dispatch_audit(args):
    claim = _value(args, "claim", "path", default=".")
    result = kernel.audit(claim, shallow=True) if getattr(args, "shallow", False) else registry.audit_deep(claim)
    return _show("audit", result, args)


def _dispatch_status(args):
    path = getattr(args, "path", ".")
    if getattr(args, "claims", False):
        result = registry.claims(path)
        text = statusview._r_claims(result)
    elif getattr(args, "deps", False):
        result = registry.deps(path)
        text = statusview._r_deps(result)
    elif getattr(args, "tree", False):
        result = registry.structure(path)
        text = statusview._r_structure(result)
    else:
        result = views._claim_view(path)
        text = (statusview._files_claim(path) if getattr(args, "files", False)
                else statusview._v_status_claim(result) if getattr(args, "verbose", False)
                else statusview._t_status_claim(result))
    if getattr(args, "json", False):
        output._finish("status", result if isinstance(result, dict) else {"claims": result},
                       True, "ok", args)
    else:
        output._line(text)
    return 0


def _dispatch_crosscheck(args):
    if getattr(args, "record", False):
        result = kernel.record_proof(args.m1, args.m2, args.m3,
                                     mutants=getattr(args, "mutants", None))
    else:
        result = kernel.crosscheck(args.m1, args.m2, args.m3,
                                   mutants=getattr(args, "mutants", None))
    return _show("crosscheck", result, args)
