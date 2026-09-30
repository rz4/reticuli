"""Actions behind the Reticuli command line.

The parser owns syntax; these handlers translate parsed arguments into calls
to the public claim layers and return process exit statuses.
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


def _show(command, data, args, *, ok=True, status=None):
    status = status or ("ok" if ok else "failed")
    if getattr(args, "json", False):
        return output._finish(command, data, ok, status, args)
    renderer = getattr(report, "_r_" + command.replace(" ", "_"), None)
    if renderer is not None:
        print(renderer(data))
    elif isinstance(data, str):
        print(data)
    else:
        print(json.dumps(data, indent=2, sort_keys=True))
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


def _handle_completion(args):
    parser._completion(getattr(args, "shell", "bash"))
    return 0


def _handle_hook(args):
    return hooks.main()


def _handle_init(args):
    workspace = _value(args, "workspace", "path", default=".")
    path = handlers.init(workspace, no_agent=getattr(args, "no_agent", False),
                         producer=getattr(args, "producer", None))
    return _show("init", {"workspace": workspace, "store": path}, args)


def _handle_run(args):
    command = _value(args, "command", "argv", default=[])
    if isinstance(command, (list, tuple)):
        command = list(command)
        if command and command[0] == "--":
            command.pop(0)
        command = " ".join(command)
    if not command:
        return _usage("run", "a command is required")
    return handlers.run(command, _value(args, "workspace", default="."),
                        producer=getattr(args, "producer", None))


def _handle_verify(args):
    data = kernel.verify(_value(args, "claim", "path", default="."))
    return _show("verify", data, args, ok=data["ok"],
                 status="identity verified" if data["ok"] else "mismatch")


def _handle_assess(args):
    data = assess.assess(_value(args, "claim", "path", default="."),
                         mutants=getattr(args, "mutants", 100))
    return _show("assess", data, args)


def _handle_rebuild(args):
    producer = getattr(args, "producer", None) or os.environ.get("RETICULI_PRODUCER")
    if not producer:
        return _usage("rebuild", "a producer is required (--producer or RETICULI_PRODUCER)")
    data = kernel.rebuild(args.claim, producer, args.into,
                          without_guidance=getattr(args, "without_guidance", False))
    return _show("rebuild", data, args)


def _handle_pull(args):
    data = registry.pull(args.claim, getattr(args, "into", "."))
    return _show("pull", data, args)


def _handle_sign(args):
    directory = _value(args, "claim", "path", default=".")
    if getattr(args, "check", False):
        data = attest.sign_check(directory, signers=os.environ.get("RETICULI_SIGNERS"))
        return _show("sign check", data, args, ok=data["ok"])
    if not getattr(args, "key", None) or not getattr(args, "identity", None):
        return _usage("sign", "--key and --as are required")
    return _show("sign", attest.sign(directory, args.key, args.identity), args)


def _handle_export(args):
    data = transfer.export(args.claim, args.archive, blind=getattr(args, "blind", False))
    return _show("export", data, args)


def _handle_record(args):
    directory = _value(args, "claim", "path", default=".")
    if getattr(args, "check", False):
        path = getattr(args, "output", None) or directory
        doc = record.read(path)
        signer = record.signer(path, os.environ["RETICULI_SIGNERS"]) if os.environ.get("RETICULI_SIGNERS") else None
        return _show("record", {"digest": record.digest(doc), "signer": signer}, args)
    destination = getattr(args, "output", None)
    if not destination:
        return _usage("record", "--output is required")
    doc = record.emit(directory)
    record.write(doc, destination)
    data = {"path": destination, "digest": record.digest(doc), "root": doc["root"]}
    if getattr(args, "key", None):
        data["signature"] = record.sign(destination, args.key)
    return _show("record", data, args)


def _handle_import(args):
    data = transfer.import_(args.archive, args.into)
    return _show("import", data, args, ok=data["ok"])


def _dispatch_pack(args):
    accepted = getattr(args, "accept", False)
    gate_output = _value(args, "gate_output", "output")
    if accepted and not gate_output:
        return _usage("pack", "--accept requires -o or --gate-output")
    root = _value(args, "path", "root", default=".")
    generated = getattr(args, "generated", None) or []
    inputs = _value(args, "input", "inputs", default=[])
    gate = getattr(args, "gate", None)
    if not generated or not gate or not gate_output:
        return _usage("pack", "--generated, --gate, and --gate-output are required")
    name = getattr(args, "name", None) or os.path.basename(os.path.abspath(root))
    data = pack.pack(root, name, generated, inputs, gate, gate_output)
    return _show("pack", data, args, ok=data["ok"])


def _dispatch_audit(args):
    directory = _value(args, "claim", "path", default=".")
    data = (kernel.audit(directory) if getattr(args, "shallow", False)
            else registry.audit_deep(directory))
    return _show("audit", data, args, ok=data["ok"],
                 status="earned" if data["ok"] else "carried or broken")


def _dispatch_status(args):
    path = _value(args, "path", "workspace", default=".")
    if getattr(args, "claims", False):
        data = registry.claims(path)
        return _show("status", data, args)
    if getattr(args, "deps", False) or getattr(args, "tree", False):
        data = registry.deps(path)
        return _show("status", data, args)
    if os.path.isfile(os.path.join(path, kernel.RECIPE)) or os.path.isfile(os.path.join(path, "claim.toml")):
        data = views._claim_view(path)
        if not getattr(args, "json", False):
            print(statusview._t_status_claim(data))
            return 0
        return _show("status", data, args, ok=data["verified"])
    data = {"workspace": os.path.abspath(path), "claims": registry.claims(path)}
    return _show("status", data, args)


def _dispatch_crosscheck(args):
    m1, m2, m3 = args.m1, args.m2, args.m3
    if getattr(args, "record_proof", False):
        data = kernel.record_proof(m1, m2, m3)
    elif any(os.path.isfile(path) for path in (m1, m2, m3)):
        data = kernel.crosscheck(m1, m2, m3, mutants=getattr(args, "mutants", None))
    else:
        data = registry.crosscheck_deep(m1, m2, m3)
    return _show("crosscheck", data, args, ok=data["satisfied"], status=data["verdict"])


def main(argv=None):
    grammar, _ = parser._parser()
    args = grammar.parse_args(argv)
    command = getattr(args, "command", None)
    if command is None:
        grammar.print_help()
        return 0
    actions = {
        "help": _handle_help, "completion": _handle_completion, "hook": _handle_hook,
        "init": _handle_init, "run": _handle_run, "verify": _handle_verify,
        "check": _handle_verify, "assess": _handle_assess, "rebuild": _handle_rebuild,
        "pull": _handle_pull, "sign": _handle_sign, "export": _handle_export,
        "record": _handle_record, "import": _handle_import, "pack": _dispatch_pack,
        "audit": _dispatch_audit, "status": _dispatch_status, "ls": _dispatch_status,
        "crosscheck": _dispatch_crosscheck,
    }
    try:
        return actions[command](args)
    except (kernel.ClaimError, OSError, ValueError) as exc:
        output._err(command, str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
