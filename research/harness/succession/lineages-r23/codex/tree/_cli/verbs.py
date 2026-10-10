"""Actions and dispatch for the Reticuli command line."""

from __future__ import annotations

import json
import os
import sys

from reticuli import assess, attest, kernel, pack, record, registry, transfer
from reticuli._cli import handlers, parser, statusview
from reticuli._cli.output import _err, _finish


def _arg(args, *names, default=None):
    for name in names:
        value = getattr(args, name, None)
        if value is not None:
            return value
    return default


def _claim(args):
    return _arg(args, "claim", "path", "directory", default=".")


def _result(command, data, args, *, ok=None, status=None):
    if ok is None:
        ok = data.get("ok", data.get("satisfied", True))
    if status is None:
        status = data.get("status") or data.get("verdict") or ("ok" if ok else "failed")
    return _finish(command, data, ok, status, args)


def _handle_help(args):
    try:
        if getattr(args, "all", False):
            parser._help_all()
        else:
            parser._help_topic(getattr(args, "topic", None))
        return 0
    except ValueError as exc:
        _err("help", str(exc))
        return 2


def _handle_completion(args):
    try:
        parser._completion(args.shell)
        return 0
    except ValueError as exc:
        _err("completion", str(exc))
        return 2


def _handle_init(args):
    data = handlers.init(_arg(args, "directory", "path", default="."),
                         no_agent=getattr(args, "no_agent", False))
    return _result("init", data, args)


def _handle_hook(args):
    from reticuli import hooks
    try:
        event = hooks.event(json.load(sys.stdin))
    except (OSError, ValueError) as exc:
        _err("hook", str(exc))
        return 2
    return _result("hook", {"event": event}, args)


def _handle_run(args):
    """Keep the observed shell status, including nonstandard exit codes."""
    command = _arg(args, "shell_command", "command")
    if isinstance(command, (list, tuple)):
        command = " ".join(command)
    if not isinstance(command, str) or not command:
        _err("run", "a command is required")
        return 2
    return handlers.run(command, _arg(args, "workspace", "directory", default="."))


def _handle_verify(args):
    return _result("verify", kernel.verify(_claim(args)), args)


def _handle_assess(args):
    mutants = _arg(args, "mutants", default=100)
    return _result("assess", assess.assess(_claim(args), mutants=mutants), args)


def _handle_rebuild(args):
    source = _claim(args)
    target = _arg(args, "into", "output")
    producer = _arg(args, "producer")
    if not target or not producer:
        _err("rebuild", "a target and producer are required")
        return 2
    if getattr(args, "reuse", False):
        data = registry.rebuild_chain(source, producer, target, reuse=True)
    else:
        data = kernel.rebuild(source, producer, target,
                              guidance=not getattr(args, "without_guidance", False))
    return _result("rebuild", data, args)


def _handle_pull(args):
    return _result("pull", registry.pull(_claim(args),
                                          _arg(args, "workspace", default=".")), args)


def _handle_sign(args):
    source = _claim(args)
    if getattr(args, "check", False):
        return _result("sign", attest.sign_check(source), args)
    key = _arg(args, "key")
    identity = _arg(args, "identity")
    if not key or not identity:
        _err("sign", "--key and --as are required")
        return 2
    return _result("sign", attest.sign(source, key, identity), args)


def _handle_export(args):
    archive = _arg(args, "archive", "output")
    if not archive:
        _err("export", "an archive path is required")
        return 2
    data = transfer.export(_claim(args), archive, blind=getattr(args, "blind", False))
    return _result("export", data, args)


def _handle_record(args):
    source = _claim(args)
    path = _arg(args, "output", "into")
    if getattr(args, "check", False):
        if not path:
            _err("record", "a record path is required")
            return 2
        doc = record.read(path)
        anchor = _arg(args, "signers") or os.environ.get("RETICULI_SIGNERS")
        data = {"ok": True, "root": doc["root"], "digest": record.digest(doc)}
        if anchor:
            data["signer"] = record.signer(path, anchor)
            data["ok"] = bool(data["signer"])
        return _result("record", data, args)
    doc = record.emit(source)
    if path:
        record.write(doc, path)
        key = _arg(args, "key")
        if key:
            record.sign(path, key)
    return _result("record", {"root": doc["root"], "digest": record.digest(doc),
                               "path": path, "record": doc}, args)


def _handle_import(args):
    archive = _arg(args, "archive")
    target = _arg(args, "into")
    if not archive or not target:
        _err("import", "an archive and target are required")
        return 2
    return _result("import", transfer.import_(archive, target), args)


def _dispatch_pack(args):
    """Validate CLI shape before invoking the authoring layer."""
    source = _arg(args, "directory", "path", default=".")
    target = _arg(args, "gate_output", "output")
    accept = getattr(args, "accept", False)
    if accept and not target:
        _err("pack", "--accept requires -o/--output")
        return 2
    generated = _arg(args, "generated", default=[]) or []
    inputs = _arg(args, "input", "inputs", default=[]) or []
    gate = _arg(args, "gate")
    if not generated or not gate or not target:
        _err("pack", "--generated, --gate, and -o/--output are required")
        return 2
    name = _arg(args, "name") or os.path.basename(os.path.abspath(source))
    data = pack.pack(source, name, generated, inputs, gate, target)
    return _result("pack", data, args)


def _dispatch_audit(args):
    source = _claim(args)
    if getattr(args, "shallow", False):
        data = kernel.audit(source)
    else:
        data = registry.audit_deep(source)
    return _result("audit", data, args)


def _dispatch_status(args):
    directory = _arg(args, "directory", "path", default=".")
    if getattr(args, "claims", False):
        return statusview._r_claims(directory, args)
    if getattr(args, "deps", False):
        return statusview._r_deps(directory, args)
    if getattr(args, "tree", False):
        return statusview._r_tree(registry.claims(directory), args)
    if kernel.phase(directory) == "draft":
        return statusview._r_status_draft(directory, args)
    data = statusview._v_status_claim(directory)
    return _result("status", data, args, status=data["phase"])


def _dispatch_crosscheck(args):
    legs = tuple(_arg(args, key) for key in ("m1", "m2", "m3"))
    if any(leg is None for leg in legs):
        _err("crosscheck", "three claim or record legs are required")
        return 2
    if getattr(args, "record_proof", False):
        data = kernel.record_proof(*legs)
    else:
        data = registry.crosscheck_deep(*legs) if getattr(args, "deep", False) else kernel.crosscheck(*legs)
    return _result("crosscheck", data, args)


_ROUTES = {
    "help": _handle_help, "completion": _handle_completion,
    "init": _handle_init, "hook": _handle_hook, "run": _handle_run,
    "status": _dispatch_status, "pack": _dispatch_pack,
    "pull": _handle_pull, "export": _handle_export, "import": _handle_import,
    "verify": _handle_verify, "audit": _dispatch_audit, "assess": _handle_assess,
    "rebuild": _handle_rebuild, "crosscheck": _dispatch_crosscheck,
    "record": _handle_record, "sign": _handle_sign,
}


def main(argv=None):
    top, _ = parser._parser()
    args = top.parse_args(argv)
    verb = getattr(args, "verb", None)
    if verb is None:
        top.print_help()
        return 0
    try:
        return _ROUTES[verb](args)
    except (kernel.ClaimError, OSError, ValueError, RuntimeError) as exc:
        _err(verb, str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
