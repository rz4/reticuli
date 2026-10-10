"""Implementation of the command line verbs.

The parser owns the grammar; this module connects parsed arguments to the
claim layers and gives every operation a process exit status.
"""

from __future__ import annotations

import json
import os
import sys

from .. import assess, attest, hooks, kernel, pack, record, registry, transfer
from . import handlers, output, parser, views


def _get(args, *names, default=None):
    for name in names:
        value = getattr(args, name, None)
        if value is not None:
            return value
    return default


def _show(command, data, args, *, ok=None, status=None):
    if ok is None:
        ok = data.get("ok", True) if isinstance(data, dict) else True
    if status is None:
        status = (data.get("verdict") or data.get("status") or
                  ("ok" if ok else "failed")) if isinstance(data, dict) else ("ok" if ok else "failed")
    output._finish(command, data, ok, status, args)
    return 0 if ok else 1


def _handle_help(args):
    if _get(args, "all", default=False):
        parser._help_all()
    elif _get(args, "topic"):
        parser._help_topic(args.topic)
    else:
        parser._parser()[0].print_help()
    return 0


def _handle_completion(args):
    parser._completion(_get(args, "shell", default="bash"))
    return 0


def _handle_init(args):
    data = handlers.init(_get(args, "directory", "workspace", "path", default="."),
                         no_agent=bool(_get(args, "no_agent", default=False)))
    return _show("init", data, args)


def _handle_hook(args):
    payload = _get(args, "payload")
    if payload is None:
        payload = json.load(sys.stdin)
    data = hooks.event(payload)
    return _show("hook", data or {"recorded": False}, args)


def _handle_run(args):
    command = _get(args, "command")
    if isinstance(command, (list, tuple)):
        command = " ".join(command)
    if not command:
        output._err("run", "a command is required")
        return 2
    directory = _get(args, "directory", "workspace", default=".")
    return handlers.run(command, directory)


def _handle_verify(args):
    return _show("verify", kernel.verify(args.claim), args)


def _handle_assess(args):
    data = assess.assess(args.claim, mutants=_get(args, "mutants", default=100))
    return _show("assess", data, args)


def _handle_rebuild(args):
    producer = _get(args, "producer")
    into = _get(args, "into")
    if not producer or not into:
        output._err("rebuild", "--producer and --into are required")
        return 2
    data = kernel.rebuild(args.claim, handlers._expand_producer(producer), into,
                          guidance=not bool(_get(args, "without_guidance", default=False)))
    return _show("rebuild", data, args)


def _handle_pull(args):
    data = registry.pull(args.claim, _get(args, "workspace", default="."))
    return _show("pull", data, args)


def _handle_sign(args):
    if _get(args, "check", default=False):
        return _show("sign", attest.sign_check(args.claim), args)
    key = _get(args, "key")
    if not key:
        output._err("sign", "--key is required")
        return 2
    data = attest.sign(args.claim, key, _get(args, "identity", default="reticuli"))
    return _show("sign", data, args)


def _handle_export(args):
    data = transfer.export(args.claim, args.archive, blind=bool(_get(args, "blind", default=False)))
    return _show("export", data, args)


def _handle_record(args):
    if _get(args, "check", default=False):
        data = record.read(args.claim)
        return _show("record", data, args)
    doc = record.emit(args.claim)
    path = _get(args, "output", default=os.path.abspath(args.claim) + ".record.json")
    record.write(doc, path)
    if _get(args, "key"):
        record.sign(path, args.key)
    return _show("record", {"path": path, "root": doc["root"],
                            "digest": record.digest(doc)}, args)


def _handle_import(args):
    data = transfer.import_(args.archive, args.into)
    return _show("import", data, args)


def _dispatch_pack(args):
    # Both grammars supported by the command layer require an output name for
    # an explicit acceptance verdict. Refuse before touching the project.
    accepted = _get(args, "accept", default=False)
    gate_output = _get(args, "output", "gate_output")
    if accepted and not gate_output:
        output._err("pack", "--accept requires -o/--output")
        return 2
    directory = _get(args, "directory", "path", default=".")
    generated = _get(args, "generated", default=[]) or []
    inputs = _get(args, "input", "inputs", default=[]) or []
    gate = _get(args, "gate")
    if isinstance(gate, list):
        gate = gate[-1] if gate else None
    if not gate or not gate_output:
        output._err("pack", "--gate and -o/--output are required")
        return 2
    name = _get(args, "name", default=os.path.basename(os.path.abspath(directory)))
    data = pack.pack(directory, name, generated, inputs, gate, gate_output,
                     inputs_manifest=_get(args, "inputs_manifest"))
    return _show("pack", data, args)


def _dispatch_audit(args):
    if _get(args, "shallow", default=False):
        data = kernel.audit(args.claim)
    else:
        data = registry.audit_deep(args.claim)
    return _show("audit", data, args)


def _dispatch_status(args):
    directory = _get(args, "directory", "workspace", default=".")
    if _get(args, "claims", default=False):
        data = registry.claims(directory)
    elif _get(args, "deps", default=False):
        data = registry.deps(directory)
    elif _get(args, "structure", default=False):
        data = registry.structure(directory)
    else:
        data = views._claim_view(directory)
    return _show("status", data, args)


def _dispatch_crosscheck(args):
    data = registry.crosscheck_deep(args.m1, args.m2, args.m3,
                                    mutants=_get(args, "mutants"))
    return _show("crosscheck", data, args, ok=data["satisfied"])


_ROUTES = {
    "help": _handle_help, "completion": _handle_completion,
    "init": _handle_init, "hook": _handle_hook, "run": _handle_run,
    "verify": _handle_verify, "assess": _handle_assess,
    "rebuild": _handle_rebuild, "pull": _handle_pull, "sign": _handle_sign,
    "export": _handle_export, "record": _handle_record,
    "import": _handle_import, "pack": _dispatch_pack,
    "audit": _dispatch_audit, "status": _dispatch_status,
    "crosscheck": _dispatch_crosscheck,
}


def main(argv=None):
    args = parser.main(argv)
    verb = _get(args, "verb", "cmd")
    if verb is None:
        parser._parser()[0].print_help()
        return 2
    if verb in ("help", "completion"):
        return 0  # parser.main already printed the requested view.
    try:
        return _ROUTES[verb](args)
    except (kernel.ClaimError, OSError, ValueError, KeyError) as exc:
        output._err(verb, str(exc))
        return 1
