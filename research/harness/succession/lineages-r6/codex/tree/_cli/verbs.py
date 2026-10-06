"""Command handlers for the ``ret`` interface.

The parser owns the grammar; this module translates parsed arguments into
the operations supplied by the kernel and the layers above it.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from reticuli import assess, attest, authoring, hooks, kernel, pack, record, registry, transfer
from . import handlers, output, parser, statusview, views


def _get(args: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        value = getattr(args, name, None)
        if value is not None:
            return value
    return default


def _emit(command: str, result: Any, args: Any, *, ok: bool | None = None) -> int:
    if ok is None:
        ok = bool(result.get("ok", True)) if isinstance(result, dict) else True
    status = (result.get("status") or result.get("verdict") or
              ("ok" if ok else "failed")) if isinstance(result, dict) else ("ok" if ok else "failed")
    output._finish(command, result, ok, str(status), args)
    return 0 if ok else 1


def _usage(command: str, message: str) -> int:
    output._err(command, message)
    return 2


def _handle_help(args: Any) -> int:
    if getattr(args, "all", False):
        parser._help_all()
    elif getattr(args, "topic", None):
        parser._help_topic(args.topic)
    else:
        print(parser._parser()[0].format_help(), end="")
    return 0


def _handle_init(args: Any) -> int:
    return _emit("init", handlers.init(_get(args, "workspace", "path", default="."),
                                        no_agent=getattr(args, "no_agent", False)), args)


def _handle_completion(args: Any) -> int:
    parser._completion(getattr(args, "shell", "bash"))
    return 0


def _handle_hook(args: Any) -> int:
    if getattr(args, "event", None):
        payload = json.load(sys.stdin)
        hooks.event(payload)
        return 0
    return hooks.main()


def _handle_run(args: Any) -> int:
    words = _get(args, "command", default=[])
    if isinstance(words, str):
        command = words
    else:
        words = list(words)
        if words[:1] == ["--"]:
            words.pop(0)
        command = " ".join(words)
    if not command:
        return _usage("run", "a command is required")
    return handlers.run(command, _get(args, "workspace", default="."),
                        producer=getattr(args, "producer", None))


def _handle_verify(args: Any) -> int:
    result = kernel.verify(_get(args, "claim", "path", default="."))
    return _emit("verify", result, args)


def _handle_assess(args: Any) -> int:
    result = assess.assess(_get(args, "claim", "path", default="."))
    return _emit("assess", result, args)


def _handle_rebuild(args: Any) -> int:
    claim = _get(args, "claim", "path")
    producer = getattr(args, "producer", None)
    into = getattr(args, "into", None)
    if not producer or not into:
        return _usage("rebuild", "--producer and --into are required")
    result = kernel.rebuild(claim, producer, into,
                            guidance=not getattr(args, "without_guidance", False))
    return _emit("rebuild", result, args)


def _handle_pull(args: Any) -> int:
    result = registry.pull(args.claim, _get(args, "into", default="."))
    return _emit("pull", result, args)


def _handle_sign(args: Any) -> int:
    claim = _get(args, "claim", "path", default=".")
    if getattr(args, "check", False):
        return _emit("sign check", attest.sign_check(claim), args)
    if not getattr(args, "key", None) or not getattr(args, "identity", None):
        return _usage("sign", "--key and --as are required")
    return _emit("sign", attest.sign(claim, args.key, args.identity), args)


def _handle_export(args: Any) -> int:
    claim = _get(args, "claim", "path", default=".")
    archive = _get(args, "archive", "output")
    if not archive:
        archive = os.path.basename(os.path.abspath(claim)) + ".tar"
    return _emit("export", transfer.export(claim, archive), args)


def _handle_record(args: Any) -> int:
    claim = _get(args, "claim", "path", default=".")
    if getattr(args, "check", False):
        path = _get(args, "archive", "output", default=claim)
        return _emit("record", record.read(path), args)
    doc = record.emit(claim)
    target = _get(args, "archive", "output")
    if target:
        record.write(doc, target)
        if getattr(args, "key", None):
            record.sign(target, args.key)
    return _emit("record", doc, args)


def _handle_import(args: Any) -> int:
    return _emit("import", transfer.import_(args.archive, _get(args, "into", default=".")), args)


def _dispatch_pack(args: Any) -> int:
    # A verdict output is necessary when the caller provides acceptance
    # commands. Check this before running a gate or writing a recipe.
    acceptance = getattr(args, "accept", None)
    verdict = _get(args, "output", "gate_output")
    if acceptance and not verdict:
        return _usage("pack", "--accept requires -o/--output for its verdict")

    project = _get(args, "project", "path", "root", default=".")
    name = _get(args, "name", default=os.path.basename(os.path.abspath(project)))
    generated = _get(args, "generated", default=[])
    inputs = _get(args, "inputs", "input", default=[])
    gate = _get(args, "gate")
    if isinstance(acceptance, list) and acceptance:
        gate = " && ".join(acceptance)
    if generated and gate and verdict:
        result = pack.pack(project, name, list(generated), list(inputs), gate, verdict,
                           inputs_manifest=getattr(args, "inputs_manifest", None))
        return _emit("pack", result, args)
    if verdict:
        into = _get(args, "into", default=os.path.join(project, ".reticuli", "sealed", name))
        result = authoring.build_claim(project, [verdict], into, name=name,
                                       claim=list(inputs), generated=list(generated))
        return _emit("pack", result, args)
    return _usage("pack", "an acceptance command and -o/--output are required")


def _dispatch_audit(args: Any) -> int:
    claim = _get(args, "claim", "path", default=".")
    result = kernel.audit(claim) if getattr(args, "shallow", False) else registry.audit_deep(claim)
    return _emit("audit", result, args)


def _dispatch_status(args: Any) -> int:
    path = _get(args, "path", "workspace", default=".")
    if getattr(args, "files", False):
        print(statusview._files_claim(path))
        return 0
    if getattr(args, "tree", False) or getattr(args, "deps", False):
        result = registry.deps(path)
        print(statusview._r_tree(result) if getattr(args, "tree", False)
              else statusview._r_deps(result))
        return 0
    if getattr(args, "claims", False):
        print(statusview._r_claims({"claims": registry.claims(path)}))
        return 0
    if os.path.isfile(os.path.join(path, kernel.RECIPE)) or os.path.isfile(os.path.join(path, "claim.toml")):
        view = views._claim_view(path)
        print(statusview._v_status_claim(view) if getattr(args, "verbose", False)
              else statusview._ledger_status_claim(view))
    else:
        print(statusview._r_claims({"claims": registry.claims(path)}))
    return 0


def _dispatch_crosscheck(args: Any) -> int:
    result = kernel.crosscheck(args.original, args.transfer, args.rebuild)
    return _emit("crosscheck", result, args, ok=bool(result.get("satisfied")))

