"""Execution of the ``ret`` command line's verbs."""

from __future__ import annotations

import os
import shlex
import sys

from reticuli import assess, attest, kernel, pack, record, registry, transfer
from . import handlers, output, parser, statusview, views


def _get(args, *names, default=None):
    for name in names:
        value = getattr(args, name, None)
        if value is not None:
            return value
    return default


def _directory(args):
    return _get(args, "directory", "path", "project", default=".")


def _result(command, data, args, *, ok=None, status=None):
    if ok is None:
        ok = data.get("ok", data.get("satisfied", True)) if isinstance(data, dict) else True
    if status is None:
        status = (data.get("status") or data.get("verdict") or
                  ("ok" if ok else "failed")) if isinstance(data, dict) else "ok"
    output._finish(command, data, ok, status, args)
    return 0 if ok else 1


def _usage(command, message):
    output._err(command, message)
    return 2


def _handle_help(args):
    if _get(args, "all", default=False):
        parser._help_all()
    else:
        parser._help_topic(_get(args, "topic"))
    return 0


def _handle_init(args):
    result = handlers.init(_get(args, "workspace", default="."),
                           no_agent=bool(_get(args, "no_agent", default=False)))
    return _result("init", result, args)


def _handle_completion(args):
    parser._completion(_get(args, "shell", default="bash"))
    return 0


def _handle_hook(args):
    from reticuli import hooks

    event = _get(args, "event")
    if event in (None, "event"):
        return hooks.main()
    if event == "install":
        result = hooks.install((_get(args, "args", default=[]) or ["."])[0])
        return _result("hook", result, args)
    return _usage("hook", f"unknown event: {event}")


def _handle_run(args):
    command = _get(args, "cmd", "command")
    if isinstance(command, (list, tuple)):
        command = " ".join(command)
    if not command:
        return _usage("run", "a command is required")
    return handlers.run(command, _get(args, "workspace", default="."))


def _handle_verify(args):
    result = kernel.verify(_directory(args))
    return _result("verify", result, args)


def _handle_assess(args):
    result = assess.assess(_directory(args))
    return _result("assess", result, args)


def _handle_rebuild(args):
    directory = _directory(args)
    producer = handlers._expand_producer(_get(args, "producer"))
    into = _get(args, "into", default=os.path.abspath(directory) + "-rebuild")
    result = registry.rebuild_chain(directory, producer, into)
    return _result("rebuild", result, args)


def _handle_pull(args):
    result = registry.pull(_get(args, "claim", "source"),
                           _get(args, "into", default="."))
    return _result("pull", result, args)


def _handle_sign(args):
    directory = _directory(args)
    if _get(args, "check", default=False):
        result = attest.sign_check(directory,
                                   signers=os.environ.get("RETICULI_SIGNERS"))
    else:
        key = _get(args, "key")
        if not key:
            return _usage("sign", "--key is required")
        identity = _get(args, "as_name", "identity", default=os.environ.get("USER", "reticuli"))
        result = attest.sign(directory, key, identity)
    return _result("sign", result, args)


def _handle_export(args):
    result = transfer.export(_directory(args), _get(args, "archive", "output"))
    return _result("export", result, args)


def _handle_record(args):
    directory = _directory(args)
    if _get(args, "check", default=False):
        path = _get(args, "output", default=os.path.join(directory, "record.json"))
        result = {"ok": record.signer(path, os.environ.get("RETICULI_SIGNERS", "")) is not None,
                  "record": path}
    else:
        doc = record.emit(directory)
        path = _get(args, "output", default=os.path.join(directory, "record.json"))
        record.write(doc, path)
        key = _get(args, "key")
        if key:
            record.sign(path, key)
        result = {"ok": True, "record": path, "root": doc["root"],
                  "digest": record.digest(doc)}
    return _result("record", result, args)


def _handle_import(args):
    result = transfer.import_(_get(args, "archive"), _get(args, "into", default="."))
    return _result("import", result, args)


def _dispatch_pack(args):
    accept = _get(args, "accept", default=False)
    destination = _get(args, "output", "into")
    if accept and not destination and not isinstance(accept, bool):
        return _usage("pack", "--accept requires -o/--output")
    project = _get(args, "project", "path", default=".")
    name = _get(args, "name", default=os.path.basename(os.path.abspath(project)))
    generated = _get(args, "generated", default=[]) or []
    inputs = _get(args, "inputs", default=[]) or []
    gate = _get(args, "gate")
    gate_output = _get(args, "gate_output", "verdict", default="PACK_OK")
    if not gate and isinstance(accept, (list, tuple)):
        gate = " && ".join(accept)
    if not gate:
        return _usage("pack", "a gate command is required")
    result = pack.pack(project, name, generated, inputs, gate, gate_output,
                       inputs_manifest=_get(args, "inputs_manifest"))
    return _result("pack", result, args)


def _dispatch_audit(args):
    directory = _directory(args)
    result = (kernel.audit(directory) if _get(args, "shallow", default=False)
              else registry.audit_deep(directory))
    return _result("audit", result, args)


def _dispatch_status(args):
    directory = _directory(args)
    if _get(args, "claims", default=False):
        result = {"claims": registry.claims(directory)}
    elif _get(args, "deps", default=False):
        result = registry.deps(directory)
    elif _get(args, "tree", default=False):
        result = registry.structure(directory)
    elif _get(args, "files", default=False):
        result = {"files": statusview._files_claim(kernel.load_recipe(directory), directory)}
    else:
        result = views._claim_view(directory)
    return _result("status", result, args)


def _dispatch_crosscheck(args):
    result = kernel.crosscheck(_get(args, "origin"), _get(args, "transfer"),
                               _get(args, "rebuild"))
    return _result("crosscheck", result, args)


_ROUTES = {
    "help": _handle_help, "init": _handle_init, "completion": _handle_completion,
    "hook": _handle_hook, "run": _handle_run, "verify": _handle_verify,
    "assess": _handle_assess, "rebuild": _handle_rebuild, "pull": _handle_pull,
    "sign": _handle_sign, "export": _handle_export, "record": _handle_record,
    "import": _handle_import, "pack": _dispatch_pack, "audit": _dispatch_audit,
    "status": _dispatch_status, "crosscheck": _dispatch_crosscheck,
}


def main(argv=None):
    cli, _ = parser._parser()
    args = cli.parse_args(argv)
    if args.command is None:
        cli.print_help()
        return 0
    command = parser.ALIASES.get(args.command, args.command)
    try:
        return _ROUTES[command](args)
    except (kernel.ClaimError, OSError, ValueError) as exc:
        output._err(command, str(exc))
        return 1

