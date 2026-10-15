"""Command handlers for the Reticuli command line."""

from __future__ import annotations

import os
import sys

from .. import assess, attest, kernel, pack, record, registry, transfer
from . import handlers, output, parser, views


def _get(args, *names, default=None):
    for name in names:
        value = getattr(args, name, None)
        if value is not None:
            return value
    return default


def _directory(args):
    return _get(args, "directory", "claim", "path", "workspace", default=".")


def _present(command, result, args, ok=None):
    if ok is None:
        ok = result.get("ok", result.get("satisfied", True)) if isinstance(result, dict) else True
    status = result.get("verdict", result.get("status", "ok" if ok else "failed")) if isinstance(result, dict) else ("ok" if ok else "failed")
    output._finish(command, result, ok, status, args)
    return 0 if ok else 1


def _handle_help(args):
    topic = _get(args, "topic")
    if topic:
        print(parser._help_topic(topic), end="")
    elif _get(args, "all", default=False):
        print(parser._help_all(), end="")
    else:
        print(parser._parser()[0].format_help(), end="")
    return 0


def _handle_init(args):
    return _present("init", handlers.init(_directory(args), no_agent=_get(args, "no_agent", default=False)), args)


def _handle_completion(args):
    parser._completion(_get(args, "shell", default="bash"))
    return 0


def _handle_hook(args):
    from .. import hooks
    return hooks.main()


def _handle_run(args):
    command = _get(args, "shell_command", "command")
    if isinstance(command, (list, tuple)):
        command = " ".join(command)
    if not isinstance(command, str) or not command:
        output._err("run", "a command is required")
        return 2
    return handlers.run(command, _get(args, "workspace", "directory", default="."))


def _handle_verify(args):
    return _present("verify", kernel.verify(_directory(args)), args)


def _handle_assess(args):
    result = assess.assess(_directory(args), mutants=_get(args, "mutants", default=32))
    return _present("assess", result, args)


def _handle_rebuild(args):
    producer = handlers._expand_producer(_get(args, "producer"))
    result = registry.rebuild_chain(_directory(args), producer, _get(args, "into"),
                                    reuse=_get(args, "reuse", default=False))
    return _present("rebuild", result, args)


def _handle_pull(args):
    return _present("pull", registry.pull(_get(args, "source"), _get(args, "into", default=".")), args)


def _handle_sign(args):
    directory = _directory(args)
    if _get(args, "check", default=False):
        result = attest.sign_check(directory, signers=os.environ.get("RETICULI_SIGNERS"))
    else:
        result = attest.sign(directory, _get(args, "key"), _get(args, "identity"))
    return _present("sign", result, args)


def _handle_export(args):
    result = transfer.export(_directory(args), _get(args, "archive"),
                             blind=_get(args, "blind", default=False))
    return _present("export", result, args)


def _handle_record(args):
    directory = _directory(args)
    if _get(args, "check", default=False):
        path = _get(args, "into", default=directory)
        result = record.read(path)
    else:
        path = _get(args, "into")
        if not path:
            output._err("record", "--into is required")
            return 2
        result = record.emit(directory)
        record.write(result, path)
        key = _get(args, "key")
        if key:
            record.sign(path, key)
    return _present("record", result, args)


def _handle_import(args):
    return _present("import", transfer.import_(_get(args, "archive"), _get(args, "into")), args)


def _dispatch_pack(args):
    directory = _directory(args)
    accepting = bool(_get(args, "accept", default=False))
    gate_output = _get(args, "output", "gate_output")
    if accepting and not gate_output:
        output._err("pack", "--accept requires -o/--output for the gate verdict")
        return 2
    gate = _get(args, "gate")
    if not gate:
        output._err("pack", "--gate is required")
        return 2
    name = _get(args, "name", default=os.path.basename(os.path.abspath(directory)))
    result = pack.pack(directory, name, _get(args, "generated", default=[]) or [],
                       _get(args, "input", "inputs", default=[]) or [], gate,
                       gate_output, inputs_manifest=_get(args, "inputs_manifest"),
                       environment=_get(args, "environment"))
    return _present("pack", result, args)


def _dispatch_audit(args):
    directory = _directory(args)
    if _get(args, "shallow", default=False):
        result = kernel.audit(directory)
    else:
        result = registry.audit_deep(directory)
    return _present("audit", result, args)


def _dispatch_status(args):
    directory = _directory(args)
    if _get(args, "deps", "tree", default=False):
        result = registry.deps(directory)
    elif _get(args, "claims", default=False):
        result = {"claims": registry.claims(directory)}
    elif os.path.isfile(os.path.join(directory, kernel.RECIPE)) or os.path.isfile(os.path.join(directory, "claim.toml")):
        result = views._claim_view(directory)
    else:
        result = {"claims": registry.claims(directory), "path": os.path.abspath(directory)}
    return _present("status", result, args)


def _dispatch_crosscheck(args):
    m1, m2, m3 = (_get(args, name) for name in ("m1", "m2", "m3"))
    result = kernel.crosscheck(m1, m2, m3, mutants=_get(args, "mutants", default=0))
    return _present("crosscheck", result, args, ok=result["satisfied"])


_COMMANDS = {
    "help": _handle_help, "init": _handle_init, "completion": _handle_completion,
    "hook": _handle_hook, "run": _handle_run, "verify": _handle_verify,
    "assess": _handle_assess, "rebuild": _handle_rebuild, "pull": _handle_pull,
    "sign": _handle_sign, "export": _handle_export, "record": _handle_record,
    "import": _handle_import, "pack": _dispatch_pack, "audit": _dispatch_audit,
    "status": _dispatch_status, "ls": _dispatch_status,
    "crosscheck": _dispatch_crosscheck,
}


def main(argv=None):
    argument_parser, _ = parser._parser()
    args = argument_parser.parse_args(argv)
    command = args.command
    if command is None:
        argument_parser.print_help()
        return 0
    try:
        return _COMMANDS[command](args)
    except (kernel.ClaimError, OSError, ValueError, TypeError) as exc:
        output._err(command, str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
