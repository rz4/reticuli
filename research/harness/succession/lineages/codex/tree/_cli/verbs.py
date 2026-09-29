"""Implement the command line verbs using the public Reticuli layers."""

from __future__ import annotations

import os
import shlex
import subprocess

from reticuli import assess, attest, hooks, kernel, pack, record, registry, transfer
from . import handlers, output, parser, views


def _get(args, name, default=None):
    return getattr(args, name, default)


def _path(args):
    return _get(args, "path") or _get(args, "workspace") or "."


def _show(command, result, args, *, ok=None, status=None):
    if ok is None:
        ok = result.get("ok", result.get("satisfied", True)) if isinstance(result, dict) else True
    if status is None:
        status = result.get("verdict", "ok" if ok else "failed") if isinstance(result, dict) else "ok"
    output._finish(command, result, ok, status, args)
    return 0 if ok else 1


def _usage(command, message):
    output._err(command, message)
    return 2


def _handle_help(args):
    if _get(args, "all", False):
        parser._help_all()
    elif _get(args, "topic"):
        parser._help_topic(args.topic)
    else:
        parser._parser()[0].print_help()
    return 0


def _handle_completion(args):
    parser._completion(args.shell)
    return 0


def _handle_hook(args):
    # The hook protocol is a JSON document on standard input.
    return hooks.main()


def _handle_init(args):
    return _show("init", handlers.init(_path(args), no_agent=_get(args, "no_agent", False)), args)


def _handle_run(args):
    command = _get(args, "command")
    if isinstance(command, (list, tuple)):
        command = " ".join(command)
    if not isinstance(command, str) or not command:
        return _usage("run", "a command is required")
    workspace = _get(args, "workspace") or _get(args, "path") or "."
    # An initialized session records the command; a bare workspace can still
    # run a command and must preserve the child's exact exit status.
    if os.path.isdir(os.path.join(workspace, ".reticuli")):
        return handlers.run(command, workspace)
    return subprocess.call(command, cwd=workspace, shell=True)


def _handle_verify(args):
    return _show("verify", kernel.verify(_path(args)), args)


def _handle_assess(args):
    result = assess.assess(_path(args), mutants=_get(args, "mutants", 12))
    audit = result["measured"].get("gates", {})
    return _show("assess", result, args, ok=bool(audit.get("ok")))


def _handle_rebuild(args):
    producer = _get(args, "producer")
    into = _get(args, "into")
    if not producer or not into:
        return _usage("rebuild", "a producer and --into are required")
    result = registry.rebuild_chain(_path(args), producer, into,
                                    ws=_get(args, "workspace"), reuse=_get(args, "reuse", False))
    return _show("rebuild", result, args)


def _handle_pull(args):
    into = _get(args, "into")
    if not into:
        return _usage("pull", "--into is required")
    return _show("pull", registry.pull(_path(args), into), args)


def _handle_sign(args):
    key, identity = _get(args, "key"), _get(args, "identity")
    if not key or not identity:
        return _usage("sign", "--key and --identity are required")
    return _show("sign", attest.sign(_path(args), key, identity,
                                      ws=_get(args, "workspace")), args)


def _handle_export(args):
    destination = _get(args, "output")
    if not destination:
        return _usage("export", "-o/--output is required")
    return _show("export", transfer.export(_path(args), destination,
                                            blind=_get(args, "blind", False)), args)


def _handle_record(args):
    destination = _get(args, "output")
    if not destination:
        return _usage("record", "-o/--output is required")
    document = record.emit(_path(args))
    record.write(document, destination)
    if _get(args, "key"):
        record.sign(destination, args.key)
    return _show("record", {"path": destination, "root": document["root"]}, args)


def _handle_import(args):
    source = _get(args, "path")
    into = _get(args, "into")
    if not source or not into:
        return _usage("import", "an archive and --into are required")
    return _show("import", transfer.import_(source, into), args)


def _dispatch_pack(args):
    action = _get(args, "cmd") or "pack"
    destination = _get(args, "output")
    if _get(args, "accept") and not destination:
        return _usage("pack", "--accept requires -o/--output")
    if action == "seal":
        return _show("seal", kernel.seal(_path(args)), args)
    if action != "pack":
        return _usage("pack", f"unknown action: {action}")
    root = _get(args, "root") or _path(args)
    name = _get(args, "name") or os.path.basename(os.path.abspath(root))
    generated = _get(args, "generated") or []
    pins = _get(args, "inputs") or _get(args, "claim") or []
    gate = _get(args, "gate")
    if not gate or not destination:
        return _usage("pack", "--gate and -o/--output are required")
    result = pack.pack(root, name, generated, pins, gate, destination)
    return _show("pack", result, args)


def _dispatch_audit(args):
    path = _path(args)
    result = kernel.audit(path) if _get(args, "shallow", False) else registry.audit_deep(path)
    return _show("audit", result, args)


def _dispatch_status(args):
    path = _path(args)
    result = views._claim_view(path)
    return _show("status", result, args, ok=result["verified"], status=result["phase"])


def _dispatch_crosscheck(args):
    legs = (_get(args, "m1"), _get(args, "m2"), _get(args, "m3"))
    if any(not leg for leg in legs):
        return _usage("crosscheck", "three claim or record paths are required")
    if _get(args, "record", False):
        result = kernel.record_proof(*legs)
    elif _get(args, "shallow", False):
        result = kernel.crosscheck(*legs)
    else:
        result = registry.crosscheck_deep(*legs)
    return _show("crosscheck", result, args)
