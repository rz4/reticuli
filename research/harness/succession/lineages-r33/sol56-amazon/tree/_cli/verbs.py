"""Implement the command verbs for the :mod:`reticuli` command line.

The parser is intentionally kept in :mod:`reticuli._cli.parser`; this module
is the (small) composition layer which turns its namespaces into calls on the
public Reticuli modules.  Handlers return process status codes and never turn
a child command's status into the generic Reticuli failure status.
"""
from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from types import SimpleNamespace
from typing import Any, Callable

from reticuli import assess as assessment
from reticuli import attest, authoring, feedback, heldout, hooks, kernel, pack
from reticuli import record as records
from reticuli import registry, reuse, transfer

from . import handlers, output, parser, report, statusview, views


def _get(args: Any, *names: str, default: Any = None) -> Any:
    """Return the first present namespace member in *names*."""
    for name in names:
        if hasattr(args, name):
            value = getattr(args, name)
            if value is not None:
                return value
    return default


def _command_name(args: Any, fallback: str) -> str:
    return str(_get(args, "command", "cmd", "verb", default=fallback))


def _quiet(args: Any) -> bool:
    return bool(getattr(args, "quiet", False))


def _ok(result: Any, default: bool = True) -> bool:
    if not isinstance(result, Mapping):
        return default
    if "ok" in result:
        return result.get("ok") is True
    if "satisfied" in result:
        return result.get("satisfied") is True
    verdict = result.get("verdict")
    if verdict in {"reject", "broken", "failed", "mismatch", "incomplete"}:
        return False
    return default


def _status(result: Any, successful: str = "ok", failed: str = "failed") -> str:
    if isinstance(result, Mapping):
        value = result.get("verdict", result.get("status"))
        if value is not None:
            return str(value)
    return successful if _ok(result) else failed


def _respond(command: str, result: Any, args: Any,
             renderer: Callable[[Any, bool], str] | None = None,
             *, successful: str = "ok", failed: str = "failed",
             ok: bool | None = None) -> int:
    """Render one action result using the common JSON/text contracts."""
    holds = _ok(result) if ok is None else bool(ok)
    status = _status(result, successful, failed)
    if bool(getattr(args, "json", False)):
        if _quiet(args):
            return 0 if holds else 1
        return output._finish(command, result, holds, status, args)
    if not _quiet(args):
        text = (renderer(result, bool(getattr(args, "verbose", False)))
                if renderer is not None else
                report._generic_contract(command, result,
                                         verbose=bool(getattr(args, "verbose", False))))
        if text:
            output._line(text)
    return 0 if holds else 1


def _usage(command: str, fact: str) -> int:
    output._err(command, fact)
    return 2


def _handle_help(args: Any) -> int:
    if bool(getattr(args, "all", False)):
        return parser._help_all(args)
    return parser._help_topic(args)


def _handle_completion(args: Any) -> int:
    return parser._completion(args)


def _handle_hook(args: Any) -> int:
    # Hook input is deliberately harmless: hooks.main already treats malformed
    # or unsupported editor events as no-ops.
    return hooks.main()


def _handle_init(args: Any) -> int:
    path = _get(args, "path", "workspace", default=".")
    result = handlers.init(path, no_agent=bool(getattr(args, "no_agent", False)))
    return _respond("init", result, args, report._r_init,
                    successful="initialized")


def _shell_command(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        words = [str(item) for item in value]
        # argparse.REMAINDER is argv-shaped and should preserve argument
        # boundaries.  Older callers passed a one-item shell command; retaining
        # that item verbatim is what makes ``[\"exit 7\"]`` useful.
        if len(words) == 1:
            return words[0]
        return shlex.join(words)
    return ""


def _handle_run(args: Any) -> int:
    command = _shell_command(_get(args, "argv", "command", default=[]))
    workspace = _get(args, "directory", "workspace", "path", default=".")
    if not command:
        return _usage("run", "a command is required")
    # The parser's authoring command requires an initialized session and is
    # traced by handlers.run.  The older programmatic predicate surface uses
    # ``command``/``workspace`` and may deliberately run in a bare temporary
    # directory; its child's status is still passed through unchanged.
    if (not hasattr(args, "argv") and hasattr(args, "command") and
            not os.path.isdir(os.path.join(os.fspath(workspace), kernel.STORE))):
        return int(subprocess.run(command, cwd=os.fspath(workspace), shell=True,
                                  check=False).returncode)
    return handlers.run(command, workspace)


def _handle_verify(args: Any) -> int:
    result = kernel.verify(_get(args, "claim", "path", default="."))
    return _respond("verify", result, args, report._r_verify,
                    successful="holds", failed="mismatch")


def _audit_claim(claim: Any, args: Any) -> Mapping[str, Any]:
    shallow = bool(getattr(args, "shallow", False))
    if shallow:
        return kernel.audit(claim)

    # Audit is composed by default.  Cached verdicts are meaningful only for
    # the exact top-level realization, so explicit --reuse may avoid that work
    # only for an uncomposed claim; registry.audit_deep remains authoritative
    # whenever component links are present.
    if bool(getattr(args, "reuse", False)):
        try:
            links = kernel.read_manifest(claim).get("components", [])
        except kernel.ClaimError:
            links = []
        if not links:
            cached = reuse.lookup(claim)
            if cached is not None:
                return cached
            result = kernel.audit(claim)
            if result.get("ok") is True:
                reuse.remember(claim, result)
            return result
    return registry.audit_deep(claim)


def _dispatch_audit(args: Any) -> int:
    claim = _get(args, "claim", "path", default=".")
    result = _audit_claim(claim, args)
    return _respond("audit", result, args, report._r_audit,
                    successful="earned", failed="broken")


def _handle_assess(args: Any) -> int:
    claim = _get(args, "claim", "path", default=".")
    mutants = _get(args, "mutants", default=100)
    heldout_command = getattr(args, "heldout", None)
    result = assessment.assess(claim, mutants=mutants,
                               heldout=heldout_command)
    if heldout_command:
        try:
            measured = heldout.run(claim, heldout_command)
            result.setdefault("measured", {})["heldout"] = measured
            if measured.get("status") != "ok":
                result["ok"] = False
        except kernel.ClaimError as exc:
            result.setdefault("not_measured", {})["heldout"] = str(exc)
            result["ok"] = False
    return _respond("assess", result, args, report._r_assess,
                    successful="measured", failed="incomplete")


def _producer_environment(name: Any) -> dict[str, str]:
    env = {key: os.environ[key] for key in handlers._PRODUCER_PASSTHROUGH
           if key in os.environ}
    descriptor = handlers._PRODUCERS.get(name) if isinstance(name, str) else None
    credential = None
    if isinstance(descriptor, Mapping):
        credential = descriptor.get("credential")
    elif isinstance(descriptor, (tuple, list)) and len(descriptor) > 1:
        credential = descriptor[1]
    if credential and str(credential) in os.environ:
        env[str(credential)] = os.environ[str(credential)]
    return env


def _handle_rebuild(args: Any) -> int:
    source = _get(args, "claim", "path", default=".")
    into = _get(args, "into", "output")
    producer_name = _get(args, "producer")
    if producer_name is None:
        return _usage("rebuild", "--producer is required")
    if into is None:
        return _usage("rebuild", "--into is required")
    producer = handlers._expand_producer(producer_name)
    options = {
        "produce_from": _get(args, "produce_from"),
        "input_from": _get(args, "input_from", "seed_from"),
        "guidance": bool(_get(args, "guidance", default=True)),
        "producer_env": _producer_environment(producer_name),
    }
    # None means "not supplied" to the kernel, but passing it explicitly is
    # supported; retain the keys for a stable call contract.
    if bool(getattr(args, "shallow", False)):
        result = kernel.rebuild(source, producer, into, **options)
    else:
        result = registry.rebuild_chain(
            source, producer, into,
            ws=_get(args, "workspace"),
            reuse=bool(getattr(args, "reuse", False)), **options)
    return _respond("rebuild", result, args, report._r_rebuild,
                    successful="earned")


def _handle_pull(args: Any) -> int:
    claim = _get(args, "claim", "source")
    workspace = _get(args, "workspace", "into", default=".")
    if claim is None:
        return _usage("pull", "a claim is required")
    result = registry.pull(claim, workspace)
    return _respond("pull", result, args, report._r_pull,
                    successful="materialized", ok=True)


def _handle_export(args: Any) -> int:
    claim = _get(args, "claim", "path", default=".")
    archive = _get(args, "archive", "output")
    if archive is None:
        return _usage("export", "an archive path is required")
    result = transfer.export(claim, archive,
                             blind=bool(getattr(args, "blind", False)))
    return _respond("export", result, args, report._r_export,
                    successful="written", ok=True)


def _handle_import(args: Any) -> int:
    archive = _get(args, "archive", "path")
    into = _get(args, "into", "output", default=".")
    if archive is None:
        return _usage("import", "an archive path is required")
    result = transfer.import_(archive, into)
    if isinstance(result, Mapping) and "path" not in result:
        result = {**result, "path": os.path.abspath(os.fspath(into))}
    return _respond("import", result, args, report._r_import,
                    successful="restored")


def _handle_sign(args: Any) -> int:
    claim = _get(args, "claim", "path", default=".")
    key = _get(args, "key")
    identity = _get(args, "identity", "as_identity", "as_")
    if key is None:
        return _usage("sign", "--key is required")
    if identity is None:
        return _usage("sign", "--as is required")
    result = attest.sign(claim, key, identity,
                         ws=_get(args, "workspace"))
    return _respond("sign", result, args, report._r_sign,
                    successful="authorized", ok=True)


def _handle_record(args: Any) -> int:
    claim = _get(args, "claim", default=".")
    path = _get(args, "path", "output")
    if bool(getattr(args, "check", False)):
        candidate = path or claim
        doc = records.read(candidate)
        signers = _get(args, "signers")
        signer = records.signer(candidate, signers) if signers else None
        signature_present = os.path.isfile(os.fspath(candidate) + ".sig")
        ok = signer is not None if signers else signature_present
        result = {"ok": ok, "status": "signed" if ok else "refused",
                  "path": os.path.abspath(os.fspath(candidate)),
                  "name": doc.get("name"), "root": doc.get("root"),
                  "build_digest": doc.get("build_digest"),
                  "signature": signer}
        return _respond("record", result, args, report._r_record,
                        successful="signed", failed="refused")

    doc = records.emit(claim, tool=handlers._version_line())
    if path is None:
        path = str(doc.get("name", "claim")) + ".record.json"
    records.write(doc, path)
    signature = None
    key = _get(args, "key")
    if key:
        signature = records.sign(path, key)
    result = {"ok": True, "status": "written", "path": os.path.abspath(os.fspath(path)),
              "name": doc["name"], "root": doc["root"],
              "build_digest": doc["build_digest"], "when": doc["when"]}
    if signature:
        result["signature"] = os.path.abspath(signature)
    return _respond("record", result, args, report._r_record,
                    successful="written")


def _as_list(value: Any) -> list[str]:
    if value is None or value is False:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Sequence):
        return [str(item) for item in value]
    return [str(value)]


def _copy_project(source: Any, destination: Any, force: bool = False) -> str:
    src = os.path.abspath(os.fspath(source))
    dst = os.path.abspath(os.fspath(destination))
    if src == dst:
        return src
    if os.path.lexists(dst):
        if not force:
            if not os.path.isdir(dst) or os.listdir(dst):
                raise kernel.ClaimError("claim destination is not empty")
        elif os.path.isdir(dst) and not os.path.islink(dst):
            shutil.rmtree(dst)
        else:
            os.unlink(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(kernel.STORE))
    return dst


def _dispatch_pack(args: Any) -> int:
    command = "pack"
    accept = getattr(args, "accept", False)
    if accept:
        # The observed-session form has always required an explicit -o: unlike
        # ordinary in-place packing, silently choosing a destination here risks
        # overwriting the author's workspace.
        destination = _get(args, "output")
        if destination is None:
            return _usage(command, "--accept requires -o/--output")
        outputs = _as_list(accept) if accept is not True else _as_list(
            _get(args, "gate_output", "root"))
        if not outputs:
            return _usage(command, "--accept requires at least one verdict output")
        workspace = _get(args, "project", "path", default=".")
        result = authoring.build_claim(
            workspace, outputs, destination,
            name=_get(args, "name"),
            claim=_as_list(_get(args, "input", "inputs")),
            generated=_as_list(_get(args, "generated")))
        return _respond(command, result, args, report._r_pack,
                        successful="sealed")

    source = _get(args, "project", "path", default=".")
    destination = _get(args, "into")
    root = _copy_project(source, destination,
                         bool(getattr(args, "force", False))) if destination else os.path.abspath(os.fspath(source))
    name = _get(args, "name", default=os.path.basename(root))
    generated = _as_list(_get(args, "generated", "produce"))
    inputs = _as_list(_get(args, "input", "inputs", "seed"))
    gate = _get(args, "gate")
    pytest_value = _get(args, "pytest")
    if gate is None and pytest_value:
        extra = "" if pytest_value is True else " " + shlex.quote(str(pytest_value))
        gate = "python3 -m pytest" + extra
    gate_output = _get(args, "gate_output", "output", "root")
    if not generated:
        return _usage(command, "at least one --generated output is required")
    if not gate:
        return _usage(command, "--gate is required")
    if not gate_output:
        return _usage(command, "--gate-output is required")
    result = pack.pack(
        root, name, generated, inputs, gate, gate_output,
        claim_format=_get(args, "claim_format", "format", default=3),
        mutation_floor=_get(args, "mutation_floor"),
        requires=_as_list(_get(args, "require", "requires")),
        inputs_manifest=_get(args, "inputs_manifest"),
        environment=_get(args, "environment"),
    )
    return _respond(command, result, args, report._r_pack,
                    successful="sealed")


def _claim_nodes(paths: Sequence[Any]) -> list[dict[str, Any]]:
    nodes = []
    for path in paths:
        try:
            nodes.append(registry.structure(path))
        except kernel.ClaimError:
            nodes.append(views._claim_view(path))
    return nodes


def _dispatch_status(args: Any) -> int:
    paths = _get(args, "paths", default=None)
    if not paths:
        paths = [_get(args, "path", "claim", default=".")]
    elif isinstance(paths, (str, os.PathLike)):
        paths = [paths]

    if bool(getattr(args, "claims", False)):
        data = {"claims": [item for path in paths for item in registry.claims(path)]}
        text = statusview._r_claims(data, bool(getattr(args, "verbose", False)))
    elif bool(getattr(args, "deps", False)):
        merged = {"claims": [item for path in paths
                              for item in registry.deps(path).get("claims", [])]}
        data = merged
        text = statusview._r_deps(data, bool(getattr(args, "verbose", False)))
    elif bool(getattr(args, "tree", False)):
        nodes = _claim_nodes(paths)
        data = {"claims": nodes}
        text = statusview._r_tree(data)
    elif bool(getattr(args, "files", False)):
        rows = []
        for path in paths:
            recipe_value = kernel.load_recipe(path)
            rendered = statusview._files_claim({"path": os.path.abspath(os.fspath(path))},
                                               recipe_value, path)
            rows.append(rendered)
        data = {"paths": [os.path.abspath(os.fspath(path)) for path in paths]}
        text = "\n\n".join(row for row in rows if row)
    else:
        claim_views = []
        for path in paths:
            view = views._claim_view(path)
            # An initialized workspace without a readable recipe is an
            # authoring draft; enrich it with the trace advice.
            if view.get("error") and os.path.isdir(os.path.join(os.fspath(path), kernel.STORE)):
                advice = feedback.advise(path)
                view.update(advice)
            claim_views.append(view)
        data = {"claims": claim_views}
        verbose = bool(getattr(args, "verbose", False))
        text = "\n\n".join(
            (statusview._r_status_draft(item, verbose)
             if item.get("phase") == "draft" else
             statusview._v_status_claim(item) if verbose else
             statusview._t_status_claim(item)) for item in claim_views)

    if bool(getattr(args, "json", False)):
        return output._finish("status", data, True, "ok", args)
    if not _quiet(args) and text:
        output._line(text)
    return 0


def _dispatch_crosscheck(args: Any) -> int:
    legs = (_get(args, "m1"), _get(args, "m2"), _get(args, "m3"))
    if any(leg is None for leg in legs):
        return _usage("crosscheck", "M1, M2, and M3 are required")
    options = {"tolerance": _get(args, "tolerance"),
               "mutants": _get(args, "mutants")}
    shallow = bool(getattr(args, "shallow", False))
    record_proof = bool(getattr(args, "record_proof", False))
    all_directories = all(os.path.isdir(os.fspath(leg)) for leg in legs)
    if record_proof:
        if shallow or not all_directories:
            result = kernel.record_proof(*legs, **options)
        else:
            result = registry.record_proof_deep(*legs, **options)
    elif shallow or not all_directories:
        result = kernel.crosscheck(*legs, **options)
    else:
        result = registry.crosscheck_deep(*legs, **options)
    return _respond("crosscheck", result, args, report._r_crosscheck,
                    successful="accept", failed="reject",
                    ok=bool(result.get("satisfied")))


_HANDLERS: dict[str, Callable[[Any], int]] = {
    "help": _handle_help,
    "completion": _handle_completion,
    "hook": _handle_hook,
    "init": _handle_init,
    "run": _handle_run,
    "verify": _handle_verify,
    "audit": _dispatch_audit,
    "assess": _handle_assess,
    "rebuild": _handle_rebuild,
    "pull": _handle_pull,
    "export": _handle_export,
    "import": _handle_import,
    "sign": _handle_sign,
    "record": _handle_record,
    "pack": _dispatch_pack,
    "status": _dispatch_status,
    "crosscheck": _dispatch_crosscheck,
}


def main(argv: Sequence[str] | None = None) -> int:
    """Parse *argv*, dispatch one verb, and return a process status."""
    root_parser, _ = parser._parser()
    args = root_parser.parse_args(argv)
    command = parser.ALIASES.get(str(getattr(args, "command", args.verb)),
                                 str(getattr(args, "command", args.verb)))
    handler = _HANDLERS.get(command)
    if handler is None:
        return _usage(command, "unknown command")
    try:
        return int(handler(args))
    except kernel.ClaimError as exc:
        output._err(command, exc)
        return 1
    except (OSError, ValueError, TypeError) as exc:
        # Filesystem bytes and malformed untrusted inputs are ordinary CLI
        # refusals.  Parser usage errors remain argparse's status 2.
        output._err(command, exc)
        return 1
    except KeyboardInterrupt:
        output._err(command, "interrupted")
        return 130


__all__ = [
    "_dispatch_audit", "_dispatch_crosscheck", "_dispatch_pack",
    "_dispatch_status", "_handle_assess", "_handle_completion",
    "_handle_export", "_handle_help", "_handle_hook", "_handle_import",
    "_handle_init", "_handle_pull", "_handle_rebuild", "_handle_record",
    "_handle_run", "_handle_sign", "_handle_verify", "main",
]
