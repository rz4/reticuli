"""Actions and dispatch for the Reticuli command line."""

from __future__ import annotations

import json
import os
import shlex
import sys

from .. import assess, attest, kernel, pack, record, registry, transfer
from . import handlers, parser, views
from .output import _err, _finish


def _value(args, name, default=None):
    return getattr(args, name, default)


def _show(command, result, args, *, ok=None, status=None):
    if ok is None:
        ok = result.get("ok", result.get("satisfied", True)) if isinstance(result, dict) else True
    if status is None:
        status = result.get("verdict", result.get("status")) if isinstance(result, dict) else None
    _finish(command, result, ok, status or ("ok" if ok else "failed"), args)
    return 0 if ok else 1


def _handle_help(args):
    if _value(args, "all", False):
        parser._help_all()
    elif _value(args, "topic"):
        parser._help_topic(args.topic)
    else:
        parser._parser()[0].print_help()
    return 0


def _handle_completion(args):
    parser._completion(_value(args, "shell", "bash"))
    return 0


def _handle_hook(args):
    from .. import hooks
    return hooks.main()


def _handle_init(args):
    workspace = handlers.init(_value(args, "workspace", "."), _value(args, "no_agent", False))
    return _show("init", {"workspace": workspace, "ok": True}, args)


def _handle_run(args):
    command = _value(args, "command", [])
    if isinstance(command, (tuple, list)):
        if command and command[0] == "--":
            command = command[1:]
        command = command[0] if len(command) == 1 else shlex.join(command)
    if not command:
        _err("run", "a command is required")
        return 2
    return handlers.run(command, _value(args, "workspace", "."))


def _handle_verify(args):
    return _show("verify", kernel.verify(_value(args, "claim", ".")), args)


def _handle_assess(args):
    result = assess.assess(_value(args, "claim", "."), _value(args, "mutants", 100))
    ok = result["measured"]["identity"]["ok"] and result["measured"]["audit"]["ok"]
    return _show("assess", result, args, ok=ok)


def _handle_rebuild(args):
    claim = _value(args, "claim")
    producer = handlers._expand_producer(_value(args, "producer"))
    result = kernel.rebuild(claim, producer, _value(args, "into"),
                            guidance=not _value(args, "without_guidance", False))
    return _show("rebuild", result, args)


def _handle_pull(args):
    return _show("pull", registry.pull(_value(args, "claim"),
                                        _value(args, "workspace", ".")), args)


def _handle_export(args):
    return _show("export", transfer.export(_value(args, "claim"),
                                            _value(args, "archive"),
                                            blind=_value(args, "blind", False)), args)


def _handle_import(args):
    return _show("import", transfer.import_(_value(args, "archive"),
                                             _value(args, "into")), args)


def _handle_record(args):
    path = _value(args, "output")
    if _value(args, "check", False):
        target = path or _value(args, "claim")
        doc = record.read(target)
        signers = _value(args, "signers")
        signer = record.signer(target, signers) if signers else None
        return _show("record", {"ok": True, "digest": record.digest(doc),
                                 "signer": signer}, args)
    doc = record.emit(_value(args, "claim", "."))
    if path:
        record.write(doc, path)
        if _value(args, "key"):
            record.sign(path, args.key)
    return _show("record", {"ok": True, "record": doc, "path": path}, args)


def _handle_sign(args):
    claim = _value(args, "claim", ".")
    if _value(args, "review", False):
        return _show("sign", attest.review_packet(claim), args)
    if _value(args, "check", False):
        return _show("sign", attest.sign_check(claim, signers=_value(args, "signers")), args)
    if not _value(args, "key") or not _value(args, "identity"):
        _err("sign", "--key and --as are required")
        return 2
    return _show("sign", attest.sign(claim, args.key, args.identity), args)


def _dispatch_pack(args):
    # Older porcelain accepts an output directory with -o.  Acceptance
    # without that destination is ambiguous and must fail before packing.
    if _value(args, "accept") and not _value(args, "output"):
        _err("pack", "--accept requires -o/--output")
        return 2
    root = _value(args, "root") or _value(args, "path")
    name = _value(args, "name")
    gate = _value(args, "gate")
    gate_output = _value(args, "gate_output") or _value(args, "output")
    if not root or not name or not gate or not gate_output:
        _err("pack", "root, name, --gate and --gate-output are required")
        return 2
    result = pack.pack(root, name, _value(args, "generated") or [],
                       _value(args, "inputs") or [], gate, gate_output,
                       claim_format=_value(args, "claim_format", 3),
                       mutation_floor=_value(args, "mutation_floor"),
                       requires=_value(args, "requires"), by=_value(args, "by"),
                       inputs_manifest=_value(args, "inputs_manifest"),
                       environment=_value(args, "environment"))
    return _show("pack", result, args)


def _dispatch_audit(args):
    claim = _value(args, "claim", ".")
    if _value(args, "shallow", False):
        result = kernel.audit(claim)
    else:
        result = registry.audit_deep(claim)
        # A plain kernel reseal may replace the component links in the
        # manifest.  The recipe's `from` declarations still carry the
        # component names and must be checked against the supplied bytes.
        parsed = kernel.load_recipe(claim)
        for step in parsed.get("step", []):
            component_name = step.get("from")
            if not component_name:
                continue
            component = os.path.join(claim, kernel.STORE, "sealed", component_name)
            supplied = os.path.join(claim, step["output"])
            if not os.path.isdir(component):
                row = {"name": component_name, "ok": False, "status": "unresolved"}
            else:
                try:
                    outputs = {item["output"] for item in kernel.load_recipe(component).get("step", [])}
                    mapping = {step["output"]: supplied} if step["output"] in outputs else None
                    checked = kernel.audit(component, produce_from=mapping)
                    row = {"name": component_name, "ok": checked["ok"],
                           "status": "ok" if checked["ok"] else "failed"}
                except kernel.ClaimError:
                    row = {"name": component_name, "ok": False, "status": "failed"}
            result.setdefault("layers", []).append(row)
            result["ok"] = result["ok"] and row["ok"]
    return _show("audit", result, args)


def _dispatch_status(args):
    workspace = _value(args, "workspace") or _value(args, "claim", ".")
    if _value(args, "claims", False):
        return _show("status", {"claims": registry.claims(workspace)}, args)
    if _value(args, "deps", False):
        return _show("status", registry.deps(workspace), args)
    if _value(args, "tree", False) or _value(args, "structure", False):
        return _show("status", registry.deps(workspace), args)
    try:
        view = views._claim_view(workspace)
    except kernel.ClaimError:
        view = {"phase": "draft", "workspace": workspace, "files": handlers._scan_workspace(workspace)}
    return _show("status", view, args, ok=view.get("verified", {}).get("ok", True),
                 status=view.get("status", view.get("phase")))


def _dispatch_crosscheck(args):
    first, second, third = (_value(args, key) for key in ("m1", "m2", "m3"))
    call = kernel.record_proof if _value(args, "record_proof", False) else kernel.crosscheck
    result = call(first, second, third, mutants=_value(args, "mutants"))
    return _show("crosscheck", result, args)


def main(argv=None):
    parsed = parser._parser()[0].parse_args(argv)
    verb = _value(parsed, "canonical") or parsed.verb
    actions = {
        "help": _handle_help, "completion": _handle_completion,
        "hook": _handle_hook, "init": _handle_init, "run": _handle_run,
        "verify": _handle_verify, "assess": _handle_assess,
        "rebuild": _handle_rebuild, "pull": _handle_pull,
        "sign": _handle_sign, "export": _handle_export,
        "record": _handle_record, "import": _handle_import,
        "pack": _dispatch_pack, "audit": _dispatch_audit,
        "status": _dispatch_status, "crosscheck": _dispatch_crosscheck,
    }
    try:
        return actions[verb](parsed)
    except (kernel.ClaimError, OSError, ValueError) as exc:
        _err(verb, str(exc))
        return 1
