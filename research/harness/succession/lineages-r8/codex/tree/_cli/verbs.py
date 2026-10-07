"""Implement the human-facing CLI verbs.

Handlers return process exit codes.  The command grammar lives in ``parser``;
this module translates its arguments into calls to the claim layers.
"""

from __future__ import annotations

import os
import sys

from reticuli import assess, attest, hooks, kernel, pack, record, registry, transfer

from . import handlers, parser, views
from .output import _err, _finish


def _get(args, name, default=None):
    return getattr(args, name, default)


def _path(args, *names, default="."):
    for name in names:
        value = _get(args, name)
        if value is not None:
            return value
    return default


def _report(command, result, args, *, ok=None):
    if ok is None:
        ok = result.get("ok", result.get("satisfied", True)) if isinstance(result, dict) else True
    status = (result.get("status") or result.get("verdict") or
              ("ok" if ok else "failed")) if isinstance(result, dict) else ("ok" if ok else "failed")
    _finish(command, result, bool(ok), str(status), args)
    return 0 if ok else 1


def _handle_help(args):
    if _get(args, "all", False):
        parser._help_all()
    elif _get(args, "topic"):
        parser._help_topic(args.topic)
    else:
        parser._parser()[0].print_help()
    return 0


def _handle_completion(args):
    parser._completion(_get(args, "shell", "bash"))
    return 0


def _handle_init(args):
    return _report("init", handlers.init(_path(args, "directory", "path"),
                                         no_agent=_get(args, "no_agent", False)), args)


def _handle_hook(args):
    return hooks.main()


def _handle_run(args):
    command = _get(args, "command")
    if isinstance(command, (list, tuple)):
        command = " ".join(command)
    if not isinstance(command, str) or not command:
        _err("run", "a command is required")
        return 2
    return handlers.run(command, _path(args, "workspace", "directory"))


def _handle_verify(args):
    return _report("verify", kernel.verify(_path(args, "claim", "path")), args)


def _handle_assess(args):
    result = assess.assess(_path(args, "claim", "path"),
                           mutants=_get(args, "mutants", 100))
    return _report("assess", result, args)


def _handle_rebuild(args):
    source = _path(args, "claim", "path")
    producer = handlers._expand_producer(_get(args, "producer"))
    into = _get(args, "into")
    if not into:
        _err("rebuild", "destination is required")
        return 2
    if _get(args, "reuse", False):
        result = registry.rebuild_chain(source, producer, into, reuse=True)
    else:
        result = kernel.rebuild(source, producer, into,
                                guidance=not _get(args, "without_guidance", False))
    return _report("rebuild", result, args)


def _handle_pull(args):
    result = registry.pull(_path(args, "claim", "path"),
                           _path(args, "workspace", "directory"))
    return _report("pull", result, args)


def _handle_sign(args):
    claim = _path(args, "claim", "path")
    if _get(args, "check", False):
        return _report("sign check", attest.sign_check(claim), args)
    key = _get(args, "key")
    identity = _get(args, "identity")
    if not key or not identity:
        _err("sign", "--key and --as are required")
        return 2
    return _report("sign", attest.sign(claim, key, identity), args)


def _handle_export(args):
    archive = _get(args, "archive", _get(args, "output"))
    if not archive:
        _err("export", "archive destination is required")
        return 2
    return _report("export", transfer.export(_path(args, "claim", "path"), archive,
                                               blind=_get(args, "blind", False)), args)


def _handle_record(args):
    claim = _path(args, "claim", "path")
    output = _get(args, "output")
    if _get(args, "check", False):
        if not output:
            _err("record", "--output is required with --check")
            return 2
        document = record.read(output)
        return _report("record", {"ok": True, "root": document["root"],
                                  "build_digest": document["build_digest"]}, args)
    if not output:
        _err("record", "--output is required")
        return 2
    document = record.emit(claim)
    record.write(document, output)
    if _get(args, "key"):
        record.sign(output, args.key)
    return _report("record", {"ok": True, "path": output,
                              "root": document["root"]}, args)


def _handle_import(args):
    into = _get(args, "into")
    if not into:
        _err("import", "destination is required")
        return 2
    return _report("import", transfer.import_(_get(args, "archive"), into), args)


def _dispatch_pack(args):
    # The older ``pack --accept VERDICT`` form requires ``-o``.  Check this
    # before calling the packer, so an invalid invocation cannot write files.
    accept = _get(args, "accept", False)
    if isinstance(accept, (list, tuple)) and accept and not _get(args, "output"):
        _err("pack", "--accept requires -o OUTPUT")
        return 2
    root = _path(args, "root", "path")
    name = _get(args, "name") or os.path.basename(os.path.abspath(root))
    generated = _get(args, "generated") or []
    inputs = _get(args, "inputs") or []
    gate = _get(args, "gate") or _get(args, "pytest")
    gate_output = _get(args, "gate_output") or _get(args, "output")
    if isinstance(accept, (list, tuple)) and accept:
        gate_output = gate_output or accept[0]
    if not gate or not gate_output:
        _err("pack", "--gate and --gate-output are required")
        return 2
    result = pack.pack(root, name, generated, inputs, gate, gate_output,
                       inputs_manifest=_get(args, "inputs_manifest"),
                       environment=_get(args, "environment"))
    return _report("pack", result, args)


def _dispatch_audit(args):
    claim = _path(args, "claim", "path")
    result = (kernel.audit(claim, deep=False) if _get(args, "shallow", False)
              else registry.audit_deep(claim))
    return _report("audit", result, args)


def _dispatch_status(args):
    directory = _path(args, "directory", "path")
    if _get(args, "claims", False):
        result = registry.claims(directory)
    elif _get(args, "tree", False):
        result = registry.deps(directory)
    else:
        result = views._claim_view(directory)
    return _report("status", result, args)


def _dispatch_crosscheck(args):
    kwargs = {}
    for key in ("mutants", "tolerance"):
        value = _get(args, key)
        if value is not None:
            kwargs[key] = value
    operation = kernel.record_proof if _get(args, "record_proof", False) else kernel.crosscheck
    result = operation(args.m1, args.m2, args.m3, **kwargs)
    return _report("crosscheck", result, args)
