"""Command handlers for the ``ret`` interface.

Handlers return process exit codes.  Presentation is kept at this boundary;
the kernel and the layers below it return ordinary result dictionaries.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys

from .. import assess, attest, hooks, kernel, pack, record, registry, transfer
from . import handlers, output, parser, report, statusview, views


def _arg(args, *names, default=None):
    for name in names:
        value = getattr(args, name, None)
        if value is not None:
            return value
    return default


def _show(command, data, args, *, ok=True, status=None):
    if getattr(args, "json", False):
        output._finish(command, data, ok, status or ("ok" if ok else "failed"), args)
    else:
        print(report._render(command, data))
    return 0 if ok else 1


def _usage(command, message):
    output._err(command, message)
    return 2


def _handle_help(args):
    if _arg(args, "all", default=False):
        parser._help_all()
    else:
        parser._help_topic(_arg(args, "topic"))
    return 0


def _handle_completion(args):
    parser._completion(_arg(args, "shell", default="bash"))
    return 0


def _handle_hook(args):
    # Hook payloads are delivered on stdin by the coding agent.
    hooks.main()
    return 0


def _handle_init(args):
    directory = _arg(args, "directory", "workspace", "path", default=".")
    result = handlers.init(directory, no_agent=bool(_arg(args, "no_agent", default=False)))
    return _show("init", result, args)


def _handle_run(args):
    words = _arg(args, "command", default=[])
    if not words:
        return _usage("run", "a command is required")
    if words[0] == "--":
        words = words[1:]
    if not words:
        return _usage("run", "a command is required")
    command = " ".join(words)
    directory = os.path.abspath(_arg(args, "workspace", "directory", default="."))
    if os.path.isdir(os.path.join(directory, ".reticuli")):
        return handlers.run(command, directory)
    return subprocess.run(command, shell=True, cwd=directory, check=False).returncode


def _handle_verify(args):
    result = kernel.verify(_arg(args, "claim", "path", default="."))
    return _show("verify", result, args, ok=bool(result["ok"]),
                 status="verified" if result["ok"] else "mismatch")


def _handle_assess(args):
    result = assess.assess(_arg(args, "claim", "path", default="."),
                           mutants=_arg(args, "mutants", default=10))
    return _show("assess", result, args)


def _handle_rebuild(args):
    source = _arg(args, "claim", "path")
    target = _arg(args, "into")
    producer = _arg(args, "producer") or os.environ.get("RETICULI_PRODUCER")
    if not source or not target or not producer:
        return _usage("rebuild", "claim, --into, and --producer are required")
    producer = handlers._expand_producer(producer)
    if _arg(args, "reuse", default=False):
        result = registry.rebuild_chain(source, producer, target, reuse=True)
    else:
        result = kernel.rebuild(source, producer, target,
                                guidance=not bool(_arg(args, "without_guidance", default=False)))
    return _show("rebuild", result, args)


def _handle_pull(args):
    source = _arg(args, "claim", "path")
    if not source:
        return _usage("pull", "claim is required")
    result = registry.pull(source, _arg(args, "into", default="."))
    return _show("pull", result, args)


def _handle_sign(args):
    source = _arg(args, "claim", "path", default=".")
    if _arg(args, "check", default=False):
        result = attest.sign_check(source, signers=os.environ.get("RETICULI_SIGNERS"))
        return _show("sign check", result, args, ok=bool(result["ok"]))
    key, principal = _arg(args, "key"), _arg(args, "principal")
    if not key or not principal:
        return _usage("sign", "--key and --as are required")
    return _show("sign", attest.sign(source, key, principal), args)


def _handle_export(args):
    source, archive = _arg(args, "claim", "path"), _arg(args, "archive", "into")
    if not source or not archive:
        return _usage("export", "claim and archive are required")
    return _show("export", transfer.export(source, archive), args)


def _handle_record(args):
    source = _arg(args, "claim", "path", default=".")
    destination = _arg(args, "into")
    if _arg(args, "check", default=False):
        if not destination:
            return _usage("record", "--check requires --into")
        doc = record.read(destination)
        anchor = os.environ.get("RETICULI_SIGNERS")
        signer = record.signer(destination, anchor) if anchor else None
        return _show("record check", {"digest": record.digest(doc), "signer": signer},
                     args, ok=bool(signer))
    doc = record.emit(source)
    if destination:
        record.write(doc, destination)
        if _arg(args, "key"):
            record.sign(destination, args.key)
    return _show("record", {"digest": record.digest(doc), "path": destination,
                            "root": doc["root"]}, args)


def _handle_import(args):
    archive, target = _arg(args, "archive"), _arg(args, "into")
    if not archive or not target:
        return _usage("import", "archive and destination are required")
    return _show("import", transfer.import_(archive, target), args)


def _dispatch_pack(args):
    source = _arg(args, "directory", "path", "root", default=".")
    generated = _arg(args, "output", "generated")
    gate = _arg(args, "gate")
    verdict = _arg(args, "verdict")
    accepted = _arg(args, "accept", default=False)
    if accepted and not generated:
        return _usage("pack", "--accept requires -o/--output")
    if not generated:
        return _usage("pack", "-o/--output is required")
    if isinstance(generated, str):
        generated = [generated]
    if not gate or not verdict:
        return _usage("pack", "--gate and --verdict are required")
    name = _arg(args, "name") or os.path.basename(os.path.abspath(source))
    inputs = _arg(args, "inputs", "pytest", default=[]) or []
    result = pack.pack(source, name, generated, inputs, gate, verdict,
                       inputs_manifest=_arg(args, "inputs_manifest"))
    return _show("pack", result, args)


def _dispatch_audit(args):
    source = _arg(args, "claim", "path", default=".")
    shallow = bool(_arg(args, "shallow", default=False))
    result = kernel.audit(source, shallow=True) if shallow else registry.audit_deep(source)
    return _show("audit", result, args, ok=bool(result.get("ok")))


def _dispatch_status(args):
    directory = _arg(args, "directory", "workspace", "path", default=".")
    if _arg(args, "deps", default=False):
        data = registry.deps(directory)
        rendered = statusview._r_deps(data)
    elif _arg(args, "claims", default=False):
        data = registry.claims(directory)
        rendered = statusview._r_claims(data)
    else:
        data = views._claim_view(directory)
        rendered = statusview._r_tree(data) if _arg(args, "tree", default=False) else statusview._v_status_claim(data)
    if _arg(args, "json", default=False):
        output._finish("status", data, True, "ok", args)
    else:
        print(rendered)
    return 0


def _dispatch_crosscheck(args):
    legs = [_arg(args, name) for name in ("m1", "m2", "m3")]
    if not all(legs):
        return _usage("crosscheck", "three claim legs are required")
    kwargs = {"mutants": _arg(args, "mutants")}
    if _arg(args, "record", default=False):
        result = kernel.record_proof(*legs, **kwargs)
    else:
        result = kernel.crosscheck(*legs, **kwargs)
    return _show("crosscheck", result, args, ok=bool(result.get("satisfied")))


_ROUTES = {
    "help": _handle_help, "completion": _handle_completion,
    "hook": _handle_hook, "init": _handle_init, "run": _handle_run,
    "verify": _handle_verify, "assess": _handle_assess,
    "rebuild": _handle_rebuild, "pull": _handle_pull,
    "sign": _handle_sign, "export": _handle_export,
    "record": _handle_record, "import": _handle_import,
    "pack": _dispatch_pack, "audit": _dispatch_audit,
    "status": _dispatch_status, "crosscheck": _dispatch_crosscheck,
}


def main(argv=None):
    command_parser, _ = parser._parser()
    args = command_parser.parse_args(argv)
    verb = parser.ALIASES.get(args.verb, args.verb)
    if verb is None:
        command_parser.print_help()
        return 0
    try:
        return _ROUTES[verb](args)
    except (kernel.ClaimError, ValueError, OSError) as exc:
        output._err(verb, str(exc))
        return 1
