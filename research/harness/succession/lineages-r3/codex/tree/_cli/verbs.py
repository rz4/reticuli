"""Implement the human-facing ``ret`` commands.

The parser owns command syntax; these handlers translate parsed arguments to
the public Reticuli operations and turn their results into exit statuses.
"""

from __future__ import annotations

import json
import os
import sys

from reticuli import assess, attest, hooks, kernel, pack, record, registry, transfer
from . import handlers, parser, statusview, views
from .output import _err, _finish, _line


def _value(args, *names, default=None):
    for name in names:
        value = getattr(args, name, None)
        if value is not None:
            return value
    return default


def _emit(command, data, args, *, ok=None, status=None):
    if ok is None:
        ok = data.get("ok", data.get("satisfied", True)) if isinstance(data, dict) else True
    if status is None:
        status = (data.get("verdict") or data.get("status") or ("ok" if ok else "failed")) if isinstance(data, dict) else ("ok" if ok else "failed")
    _finish(command, data, ok, status, args)
    return 0 if ok else 1


def _handle_help(args):
    if getattr(args, "all", False):
        parser._help_all()
    else:
        parser._help_topic(_value(args, "topic"))
    return 0


def _handle_init(args):
    path = handlers.init(_value(args, "workspace", "path", default="."),
                         no_agent=bool(getattr(args, "no_agent", False)))
    return _emit("init", {"workspace": path}, args)


def _handle_completion(args):
    parser._completion(_value(args, "shell", default="bash"))
    return 0


def _handle_hook(args):
    # Hooks receive their structured event on stdin. An optional event name is
    # accepted by the parser for shells that supply it as a separate token.
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError) as exc:
        _err("hook", str(exc))
        return 2
    if getattr(args, "event", None) and isinstance(payload, dict):
        payload.setdefault("hook_event_name", args.event)
    hooks.event(payload)
    return 0


def _handle_run(args):
    command = _value(args, "script", "command")
    if isinstance(command, (list, tuple)):
        command = " ".join(map(str, command))
    if not command:
        _err("run", "a command is required")
        return 2
    return handlers.run(command, _value(args, "workspace", default="."))


def _handle_verify(args):
    return _emit("verify", kernel.verify(_value(args, "claim", "path", default=".")), args)


def _handle_assess(args):
    result = assess.assess(_value(args, "claim", "path", default="."),
                           mutants=_value(args, "mutants", default=100))
    return _emit("assess", result, args,
                 ok=result["measured"]["audit"].get("ok", False))


def _handle_rebuild(args):
    source = _value(args, "claim", "path")
    target = _value(args, "into")
    producer = _value(args, "producer", default=os.environ.get("RETICULI_PRODUCER"))
    if not source or not target or not producer:
        _err("rebuild", "claim, into, and a producer are required")
        return 2
    if getattr(args, "without_guidance", False):
        # The kernel receives guidance from the source recipe. The public
        # producer command can opt out by clearing the hint in its environment.
        producer = "RETICULI_REQUEST='' " + producer
    result = registry.rebuild_chain(source, producer, target)
    return _emit("rebuild", result, args)


def _handle_pull(args):
    result = registry.pull(_value(args, "claim", "path"),
                           _value(args, "workspace", default="."))
    return _emit("pull", result, args)


def _handle_sign(args):
    directory = _value(args, "claim", "path", default=".")
    if getattr(args, "check", False):
        return _emit("sign check", attest.sign_check(directory), args)
    key = _value(args, "key")
    signer = _value(args, "signer")
    if not key or not signer:
        _err("sign", "--key and --as are required")
        return 2
    return _emit("sign", attest.sign(directory, key, signer), args)


def _handle_export(args):
    source = _value(args, "claim", "path")
    archive = _value(args, "archive", "output")
    if not source or not archive:
        _err("export", "claim and archive are required")
        return 2
    return _emit("export", transfer.export(source, archive,
                                          blind=bool(getattr(args, "blind", False))), args)


def _handle_record(args):
    directory = _value(args, "claim", "path", default=".")
    if getattr(args, "check", False):
        return _emit("record", {"record": record.emit(directory)}, args)
    document = record.emit(directory)
    output = _value(args, "output", default=os.path.join(directory, "record.json"))
    record.write(document, output)
    key = _value(args, "key")
    if key:
        record.sign(output, key)
    return _emit("record", {"path": output, "root": document["root"]}, args)


def _handle_import(args):
    source = _value(args, "archive", "path")
    target = _value(args, "into")
    if not source or not target:
        _err("import", "archive and into are required")
        return 2
    return _emit("import", transfer.import_(source, target), args)


def _dispatch_pack(args):
    project = _value(args, "project", "path", default=".")
    generated = _value(args, "generated", default=[])
    inputs = _value(args, "input", "inputs", default=[])
    gate = _value(args, "gate")
    output = _value(args, "gate_output", "output")
    accept = getattr(args, "accept", False)
    if accept and not output:
        _err("pack", "--accept requires -o/--output (a gate verdict file)")
        return 2
    if not generated or not gate or not output:
        _err("pack", "--generated, --gate, and -o/--output are required")
        return 2
    name = _value(args, "name", default=os.path.basename(os.path.abspath(project)))
    result = pack.pack(project, name, generated, inputs, gate, output,
                       claim_format=_value(args, "claim_format"),
                       inputs_manifest=_value(args, "inputs_manifest"),
                       environment=_value(args, "environment"))
    return _emit("pack", result, args)


def _dispatch_audit(args):
    directory = _value(args, "claim", "path", default=".")
    result = (kernel.audit(directory) if getattr(args, "shallow", False)
              else registry.audit_deep(directory))
    return _emit("audit", result, args)


def _dispatch_status(args):
    workspace = _value(args, "workspace", "path", default=".")
    if getattr(args, "claims", False):
        rows = registry.claims(workspace)
        result = {"claims": rows}
        rendered = statusview._r_claims(rows)
    elif getattr(args, "deps", False) or getattr(args, "tree", False):
        result = registry.deps(workspace)
        rendered = statusview._r_tree(result) if getattr(args, "tree", False) else statusview._r_deps(result)
    else:
        result = views._claim_view(workspace)
        rendered = (statusview._v_status_claim(result) if getattr(args, "verbose", False)
                    else statusview._t_status_claim(result))
    if getattr(args, "json", False):
        _finish("status", result, True, "ok", args)
    else:
        _line(rendered)
    return 0


def _dispatch_crosscheck(args):
    legs = [_value(args, name) for name in ("m1", "m2", "m3")]
    if any(leg is None for leg in legs):
        _err("crosscheck", "m1, m2, and m3 are required")
        return 2
    if getattr(args, "record_proof", False):
        result = kernel.record_proof(*legs)
    elif all(os.path.isdir(leg) for leg in legs):
        result = registry.crosscheck_deep(*legs)
    else:
        result = kernel.crosscheck(*legs)
    return _emit("crosscheck", result, args)


_ROUTES = {
    "help": _handle_help, "init": _handle_init, "completion": _handle_completion,
    "hook": _handle_hook, "run": _handle_run, "verify": _handle_verify,
    "assess": _handle_assess, "rebuild": _handle_rebuild, "pull": _handle_pull,
    "sign": _handle_sign, "export": _handle_export, "record": _handle_record,
    "import": _handle_import, "pack": _dispatch_pack, "audit": _dispatch_audit,
    "status": _dispatch_status, "crosscheck": _dispatch_crosscheck,
}


def main(argv=None):
    top, _ = parser._parser()
    args = top.parse_args(argv)
    if args.version:
        _line(handlers._version_line())
        return 0
    command = args.command
    if not command:
        top.print_help()
        return 0
    command = parser.ALIASES.get(command, command)
    try:
        return _ROUTES[command](args)
    except (kernel.ClaimError, OSError, ValueError, KeyError, TypeError) as exc:
        _err(command, str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
