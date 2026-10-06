"""Command handlers for the ``ret`` surface.

Each handler accepts the parsed argument namespace and returns an exit status.
The package modules do the claim work; this module translates their results
into command line output and usage errors.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys

from reticuli import assess, attest, kernel, pack, record, registry, transfer

from . import handlers, parser, report, statusview, views
from .output import _err, _finish, _line


def _value(args, *names, default=None):
    for name in names:
        value = getattr(args, name, None)
        if value is not None:
            return value
    return default


def _directory(args):
    return os.fspath(_value(args, "directory", "path", default="."))


def _show(command, data, args, *, ok=None):
    if ok is None:
        ok = data.get("ok", True) if isinstance(data, dict) else True
    renderer = getattr(report, "_r_" + command.replace("-", "_"), None)
    message = renderer(data) if renderer else None
    _finish(command, data, ok, "ok" if ok else "failed", args, message)
    return 0 if ok else 1


def _usage(command, message):
    _err(command, message)
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
    data = handlers.init(_directory(args), getattr(args, "no_agent", False))
    return _show("init", data, args)


def _handle_completion(args):
    parser._completion(_value(args, "shell", default="bash"))
    return 0


def _handle_hook(args):
    from reticuli import hooks
    hooks.main()
    return 0


def _handle_run(args):
    """Run the user's command and preserve the child's exact exit status."""
    words = _value(args, "command", default=[])
    if not words:
        return _usage("run", "a command is required")
    if isinstance(words, str):
        command = words
    else:
        words = list(words)
        if words[:1] == ["--"]:
            words = words[1:]
        if not words:
            return _usage("run", "a command is required")
        command = words[0] if len(words) == 1 else shlex.join(words)
    workspace = os.fspath(_value(args, "workspace", "directory", default="."))
    result = subprocess.run(command, shell=True, cwd=workspace, check=False)
    return result.returncode


def _handle_verify(args):
    data = kernel.verify(_directory(args))
    return _show("verify", data, args)


def _handle_assess(args):
    data = assess.assess(_directory(args), mutants=_value(args, "mutants", default=100))
    return _show("assess", data, args)


def _handle_rebuild(args):
    producer = _value(args, "producer")
    into = _value(args, "into", "output")
    if not producer or not into:
        return _usage("rebuild", "producer and output directory are required")
    data = kernel.rebuild(_directory(args), handlers._expand_producer(producer), into,
                          guidance=not getattr(args, "without_guidance", False))
    return _show("rebuild", data, args)


def _handle_pull(args):
    claim = _value(args, "claim", "path")
    if not claim:
        return _usage("pull", "a claim is required")
    data = registry.pull(claim, _value(args, "into", default="."))
    return _show("pull", data, args)


def _handle_sign(args):
    key = _value(args, "key")
    identity = _value(args, "identity")
    if not key or not identity:
        return _usage("sign", "--key and --as are required")
    data = attest.sign(_directory(args), key, identity)
    return _show("sign", data, args)


def _handle_export(args):
    archive = _value(args, "archive", "output")
    if not archive:
        return _usage("export", "an archive path is required")
    data = transfer.export(_directory(args), archive, blind=getattr(args, "blind", False))
    return _show("export", data, args)


def _handle_record(args):
    path = _value(args, "output", "archive")
    if getattr(args, "check", False):
        if not path:
            return _usage("record", "a record path is required with --check")
        data = record.read(path)
        return _show("record", data, args)
    if not path:
        return _usage("record", "an output path is required")
    data = record.emit(_directory(args))
    record.write(data, path)
    if getattr(args, "key", None):
        record.sign(path, args.key)
    return _show("record", data, args)


def _handle_import(args):
    archive = _value(args, "archive")
    if not archive:
        return _usage("import", "an archive path is required")
    data = transfer.import_(archive, _directory(args))
    return _show("import", data, args)


def _dispatch_pack(args):
    """Check pack's argument dependencies before creating claim files."""
    output = _value(args, "output", "into")
    if getattr(args, "accept", False) and not output:
        return _usage("pack", "--accept requires -o/--output")
    if not output:
        return _usage("pack", "-o/--output is required")
    source = _directory(args)
    name = _value(args, "name", default=os.path.basename(os.path.abspath(source)))
    generated = _value(args, "generated", default=[])
    inputs = _value(args, "inputs", default=[])
    gate = _value(args, "gate")
    verdict = _value(args, "gate_output", default="OK")
    if not gate:
        return _usage("pack", "--gate is required")
    data = pack.pack(source, name, generated, inputs, gate, verdict,
                     inputs_manifest=getattr(args, "inputs_manifest", None))
    return _show("pack", data, args)


def _dispatch_audit(args):
    directory = _directory(args)
    data = (registry.audit_deep(directory) if getattr(args, "deep", False)
            else kernel.audit(directory))
    return _show("audit", data, args)


def _dispatch_status(args):
    directory = _directory(args)
    if getattr(args, "claims", False):
        data = {"claims": registry.claims(directory)}
        message = statusview._r_claims(data)
    elif getattr(args, "tree", False):
        data = registry.structure(directory)
        message = statusview._r_tree(data)
    else:
        data = views._claim_view(directory)
        message = statusview._v_status_claim(data)
    _finish("status", data, True, "ok", args, message)
    return 0


def _dispatch_crosscheck(args):
    legs = [_value(args, "m1"), _value(args, "m2"), _value(args, "m3")]
    if any(leg is None for leg in legs):
        return _usage("crosscheck", "three claim legs are required")
    data = kernel.crosscheck(*legs)
    return _show("crosscheck", data, args, ok=data.get("satisfied", False))


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
    top, _ = parser._parser()
    args = top.parse_args(argv)
    name = parser.ALIASES.get(args.verb, args.verb)
    if name is None:
        top.print_help()
        return 0
    try:
        return _HANDLERS[name](args)
    except (kernel.ClaimError, OSError, ValueError) as exc:
        _err(name, exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
