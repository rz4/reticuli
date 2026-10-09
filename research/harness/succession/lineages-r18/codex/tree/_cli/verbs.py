"""Actions behind the Reticuli command line.

Keep argument handling here; the underlying modules own claim operations and
the output helpers own the human and JSON presentations.
"""

from __future__ import annotations

import json
import os
import sys

from .. import assess, attest, authoring, feedback, hooks, kernel, pack, record
from .. import registry, transfer
from . import handlers, output, parser, views


def _value(args, name, default=None):
    return getattr(args, name, default)


def _path(args):
    return _value(args, "claim", _value(args, "path", "."))


def _result(command, result, args, *, ok=None, status=None):
    if ok is None:
        ok = bool(result.get("ok", True)) if isinstance(result, dict) else True
    return output._finish(command, result, ok, status or ("ok" if ok else "refused"), args)


def _usage(command, message):
    output._err(command, message)
    return 2


def _handle_help(args):
    if _value(args, "all", False):
        parser._help_all()
    elif _value(args, "topic"):
        parser._help_topic(args.topic)
    else:
        print(parser._parser()[0].format_help(), end="")
    return 0


def _handle_init(args):
    result = handlers.init(_value(args, "workspace", "."), no_agent=_value(args, "no_agent", False))
    return _result("init", result, args)


def _handle_completion(args):
    parser._completion(args.shell)
    return 0


def _handle_hook(args):
    # Agent hooks pass their event as JSON on stdin.
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError) as exc:
        return _usage("hook", str(exc))
    result = hooks.event(payload)
    if result is not None:
        print(json.dumps(result, sort_keys=True))
    return 0


def _handle_run(args):
    words = _value(args, "command_text", _value(args, "command", []))
    if isinstance(words, str):
        command = words
    else:
        command = " ".join(words)
    if not command:
        return _usage("run", "a command is required")
    return handlers.run(command, _value(args, "workspace", "."))


def _handle_verify(args):
    result = kernel.verify(_path(args))
    return _result("verify", result, args)


def _handle_assess(args):
    result = assess.assess(_path(args), mutants=_value(args, "mutants", 20))
    return _result("assess", result, args)


def _handle_rebuild(args):
    producer = _value(args, "producer")
    if not producer:
        return _usage("rebuild", "--producer is required")
    producer = handlers._expand_producer(producer)
    source = _path(args)
    into = _value(args, "into")
    if not into:
        return _usage("rebuild", "destination is required")
    if _value(args, "reuse", False):
        result = registry.rebuild_chain(source, producer, into, reuse=True)
    else:
        result = kernel.rebuild(source, producer, into,
                                guidance=not _value(args, "without_guidance", False))
    return _result("rebuild", result, args)


def _handle_pull(args):
    result = registry.pull(_path(args), _value(args, "workspace", "."))
    return _result("pull", result, args)


def _handle_sign(args):
    path = _path(args)
    if _value(args, "check", False):
        result = attest.sign_check(path)
    else:
        if not _value(args, "key") or not _value(args, "identity"):
            return _usage("sign", "--key and --as are required")
        result = attest.sign(path, args.key, args.identity)
    return _result("sign", result, args)


def _handle_export(args):
    result = transfer.export(_path(args), args.archive, blind=_value(args, "blind", False))
    return _result("export", {"archive": result}, args)


def _handle_record(args):
    path = _path(args)
    destination = _value(args, "output") or os.path.join(path, kernel.STORE, "record.json")
    if _value(args, "check", False):
        result = kernel.record_read(destination)
        return _result("record", result, args)
    document = record.emit(path)
    os.makedirs(os.path.dirname(os.path.abspath(destination)), exist_ok=True)
    record.write(document, destination)
    if _value(args, "key"):
        record.sign(destination, args.key)
    return _result("record", {"path": destination, "root": document["root"]}, args)


def _handle_import(args):
    result = transfer.import_(args.archive, args.into)
    return _result("import", result, args)


def _dispatch_pack(args):
    path = _value(args, "path", ".")
    accept = _value(args, "accept", False)
    # The authoring form uses -o for a new claim directory. Validate before
    # reading a trace, writing a recipe, or invoking a gate.
    if _value(args, "cmd") == "pack":
        if accept and not _value(args, "output"):
            return _usage("pack", "--accept requires -o/--output")
        if not accept:
            proposal = authoring.propose(path, _value(args, "gate") or [],
                                         _value(args, "name") or os.path.basename(os.path.abspath(path)),
                                         generated=_value(args, "generated"))
            return _result("pack", proposal, args)
        result = authoring.build_claim(path, _value(args, "gate") or [], args.output,
                                       name=_value(args, "name"),
                                       generated=_value(args, "generated"))
        return _result("pack", result, args)
    if not accept:
        return _result("pack", {"path": path, "status": "draft"}, args)
    if not _value(args, "gate") or not _value(args, "gate_output"):
        return _usage("pack", "--accept requires --gate and --gate-output")
    result = pack.pack(path, _value(args, "name") or os.path.basename(os.path.abspath(path)),
                       _value(args, "generated", []), _value(args, "inputs", []),
                       args.gate, args.gate_output,
                       inputs_manifest=_value(args, "inputs_manifest"),
                       environment=_value(args, "environment"))
    return _result("pack", result, args)


def _dispatch_audit(args):
    result = (kernel.audit(_path(args), shallow=True) if _value(args, "shallow", False)
              else registry.audit_deep(_path(args)))
    return _result("audit", result, args)


def _dispatch_status(args):
    path = _value(args, "path", ".")
    if _value(args, "claims", False):
        result = {"claims": registry.claims(path)}
    elif _value(args, "tree", False):
        result = registry.deps(path)
    elif os.path.isfile(os.path.join(path, "reticuli.toml")) or os.path.isfile(os.path.join(path, "claim.toml")):
        result = views._claim_view(path)
        if _value(args, "files", False):
            doc = kernel.load_recipe(path)
            result["files"] = {step["output"]: step.get("class") for step in doc.get("step", [])}
    else:
        result = handlers._scan_workspace(path)
        result.update(feedback.advise(path))
    return _result("status", result, args)


def _dispatch_crosscheck(args):
    paths = (args.m1, args.m2, args.m3)
    if _value(args, "record_proof", False):
        result = registry.record_proof_deep(*paths, mutants=_value(args, "mutants"))
    else:
        result = registry.crosscheck_deep(*paths, mutants=_value(args, "mutants"))
    return _result("crosscheck", result, args, ok=result.get("satisfied", False),
                   status=result.get("verdict", "refused"))
