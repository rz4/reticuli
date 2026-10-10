"""Actions behind the ``ret`` command line.

The parser owns syntax; this module connects each action to the claim layers
and gives the action an exit status.  Direct callers may also pass a simple
namespace containing the relevant arguments.
"""

from __future__ import annotations

import os
import sys

from .. import assess, attest, hooks, kernel, pack, record, registry, transfer
from . import handlers, output, parser, report, statusview, views


def _arg(args, *names, default=None):
    for name in names:
        value = getattr(args, name, None)
        if value is not None:
            return value
    return default


def _show(command, value, args, *, ok=True, message=None):
    status = value.get("verdict", value.get("status", "ok" if ok else "failed")) if isinstance(value, dict) else ("ok" if ok else "failed")
    output._finish(command, value, ok, status, args, message=message)
    return 0 if ok else 1


def _handle_help(args):
    if _arg(args, "all", default=False):
        parser._help_all()
    else:
        parser._help_topic(_arg(args, "topic"))
    return 0


def _handle_completion(args):
    parser._completion(_arg(args, "shell", default="bash"))
    return 0


def _handle_init(args):
    result = handlers.init(_arg(args, "directory", "workspace", "path", default="."),
                           no_agent=bool(_arg(args, "no_agent", default=False)))
    return _show("init", result, args, message=report._r_init(result))


def _handle_hook(args):
    import json

    payload = _arg(args, "payload")
    if payload is None:
        payload = json.load(sys.stdin)
    result = hooks.event(payload)
    if result is not None and bool(_arg(args, "json", default=False)):
        output._finish("hook", result, True, "ok", args)
    return 0


def _handle_run(args):
    command = _arg(args, "command_line", "command")
    if isinstance(command, (list, tuple)):
        command = " ".join(str(part) for part in command)
    if not command:
        output._err("run", "a command is required")
        return 2
    return handlers.run(command, _arg(args, "workspace", "directory", "path", default="."))


def _handle_verify(args):
    result = kernel.verify(_arg(args, "directory", "claim", "path", default="."))
    return _show("verify", result, args, ok=bool(result["ok"]), message=report._r_verify(result))


def _handle_assess(args):
    result = assess.assess(_arg(args, "directory", "claim", "path", default="."),
                           mutants=_arg(args, "mutants", default=100))
    return _show("assess", result, args, message=report._r_assess(result))


def _handle_rebuild(args):
    source = _arg(args, "directory", "claim", "path")
    into = _arg(args, "into")
    producer = _arg(args, "producer") or os.environ.get("RETICULI_PRODUCER")
    if not source or not into or not producer:
        output._err("rebuild", "claim, destination, and producer are required")
        return 2
    producer = handlers._expand_producer(producer)
    result = kernel.rebuild(source, producer, into,
                            guidance=not bool(_arg(args, "without_guidance", default=False)))
    return _show("rebuild", result, args, message=report._r_rebuild(result))


def _handle_pull(args):
    result = registry.pull(_arg(args, "source", "claim"),
                           _arg(args, "into", "workspace", default="."))
    return _show("pull", result, args, message=report._r_pull(result))


def _handle_sign(args):
    directory = _arg(args, "directory", "claim", "path", default=".")
    if _arg(args, "check", default=False):
        result = attest.sign_check(directory, signers=os.environ.get("RETICULI_SIGNERS"))
        return _show("sign check", result, args, ok=result["ok"], message=report._r_sign_check(result))
    key, principal = _arg(args, "key"), _arg(args, "principal", "as_name")
    if not key or not principal:
        output._err("sign", "--key and --as are required")
        return 2
    result = attest.sign(directory, key, principal)
    return _show("sign", result, args, message=report._r_sign(result))


def _handle_export(args):
    directory = _arg(args, "directory", "claim", "path")
    archive = _arg(args, "archive", "output")
    if not directory or not archive:
        output._err("export", "claim and archive are required")
        return 2
    transfer.export(directory, archive, blind=bool(_arg(args, "blind", default=False)))
    result = {"path": archive, "root": kernel.verify(directory)["root"]}
    return _show("export", result, args, message=report._r_export(result))


def _handle_record(args):
    directory = _arg(args, "directory", "claim", "path", default=".")
    if _arg(args, "check", default=False):
        path = _arg(args, "output", "record", default=directory)
        doc = record.read(path)
        result = {"ok": True, "root": doc["root"], "build_digest": doc["build_digest"]}
        return _show("record check", result, args)
    path = _arg(args, "output") or os.path.join(directory, ".reticuli", "record.json")
    doc = record.emit(directory)
    record.write(doc, path)
    if _arg(args, "key"):
        record.sign(path, args.key)
    return _show("record", {**doc, "path": path}, args, message=report._r_record(doc))


def _handle_import(args):
    archive = _arg(args, "archive", "source")
    into = _arg(args, "into", "directory")
    if not archive or not into:
        output._err("import", "archive and destination are required")
        return 2
    result = transfer.import_(archive, into)
    return _show("import", result, args, ok=result["ok"], message=report._r_import(result))


def _dispatch_pack(args):
    # The acceptance form writes to a separate destination.  Refuse an
    # incomplete invocation before pack() can write a recipe or run a gate.
    if _arg(args, "accept") and not _arg(args, "output"):
        output._err("pack", "--accept requires -o/--output")
        return 2
    directory = _arg(args, "directory", "path", default=".")
    name = _arg(args, "name") or os.path.basename(os.path.abspath(directory))
    generated = _arg(args, "generated", default=[]) or []
    inputs = _arg(args, "input", "inputs", default=[]) or []
    gate = _arg(args, "gate")
    gate_output = _arg(args, "gate_output", "output")
    if not gate or not gate_output:
        output._err("pack", "--gate and --gate-output are required")
        return 2
    result = pack.pack(directory, name, generated, inputs, gate, gate_output,
                       inputs_manifest=_arg(args, "inputs_manifest"),
                       environment=_arg(args, "environment"))
    return _show("pack", result, args, message=report._r_pack(result))


def _dispatch_audit(args):
    directory = _arg(args, "directory", "claim", "path", default=".")
    if _arg(args, "shallow", default=False):
        result = kernel.audit(directory)
    else:
        result = registry.audit_deep(directory)
    return _show("audit", result, args, ok=bool(result["ok"]), message=report._r_audit(result))


def _dispatch_status(args):
    directory = _arg(args, "directory", "workspace", "path", default=".")
    if _arg(args, "tree", default=False):
        result = registry.structure(directory)
        message = statusview._r_tree(result)
    elif _arg(args, "claims", default=False):
        result = registry.claims(directory)
        message = statusview._r_claims(result)
    elif _arg(args, "deps", default=False):
        result = registry.deps(directory)
        message = statusview._r_deps(result)
    elif _arg(args, "files", default=False):
        result = statusview._files_claim(directory)
        message = result
    else:
        result = views._claim_view(directory)
        message = (statusview._v_status_claim(result) if _arg(args, "verbose", default=False)
                   else statusview._t_status_claim(result))
    return _show("status", result, args, message=message)


def _dispatch_crosscheck(args):
    legs = [_arg(args, key) for key in ("m1", "m2", "m3")]
    if any(leg is None for leg in legs):
        output._err("crosscheck", "three claim or record paths are required")
        return 2
    result = kernel.crosscheck(*legs, mutants=_arg(args, "mutants"))
    return _show("crosscheck", result, args, ok=result["satisfied"],
                 message=report._r_crosscheck(result))


_VERBS = {
    "init": _handle_init, "run": _handle_run, "status": _dispatch_status,
    "pack": _dispatch_pack, "pull": _handle_pull, "export": _handle_export,
    "import": _handle_import, "verify": _handle_verify,
    "audit": _dispatch_audit, "assess": _handle_assess,
    "rebuild": _handle_rebuild, "crosscheck": _dispatch_crosscheck,
    "record": _handle_record, "sign": _handle_sign,
    "hook": _handle_hook, "help": _handle_help,
    "completion": _handle_completion,
}


def main(argv=None):
    command_parser, _ = parser._parser()
    args = command_parser.parse_args(argv)
    if args.version:
        print(handlers._version_line())
        return 0
    command = parser.ALIASES.get(args.command, args.command)
    if command is None:
        command_parser.print_help()
        return 0
    try:
        return _VERBS[command](args)
    except (kernel.ClaimError, OSError, ValueError) as exc:
        output._err(command, str(exc))
        return 1
