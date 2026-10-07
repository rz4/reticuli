"""reticuli._cli.verbs: the verb handlers, and `main`'s own routing.

One `_handle_*` function per simple porcelain verb, and one `_dispatch_*`
per verb whose behavior actually branches (`pack` on `--accept`, `audit`
on deep-vs-shallow, `status` on `--tree`/`--claims`, `crosscheck` over
its three legs). Each takes the verb's already-parsed `args` namespace,
calls down into the layer that owns the behavior (`reticuli.kernel`,
`reticuli.registry`, `reticuli.transfer`, `reticuli.attest`,
`reticuli.record`, `reticuli.pack`, `reticuli.assess`, `reticuli.hooks`,
and `reticuli._cli.handlers` for session setup and traced `run`), and
renders the result through `reticuli._cli.report`/`output`/`statusview`.

Every handler and dispatch returns a process exit code -- 0 for success,
a small positive integer otherwise -- with one deliberate exception:
`_handle_run` returns the child command's own exit code unchanged, since
a session loop uses it as a predicate (`spec/layers.md`: the surface
layer's `run` is a pass-through, not a verdict of its own). `_dispatch_pack`
refuses, in words and before touching disk, an `--accept` invocation that
never named the gate's verdict file with `-o`/`--output` -- there is
nothing to seal without one.

`main` reads the grammar back from `reticuli._cli.parser`, so it can
never route a verb the parser does not also register.

Stdlib only.
"""
import json
import os
import sys
import tempfile

from reticuli import assess
from reticuli import attest
from reticuli import hooks
from reticuli import kernel
from reticuli import pack
from reticuli import record as record_lib
from reticuli import registry
from reticuli import transfer
from reticuli import _util

from reticuli._cli import handlers
from reticuli._cli import output
from reticuli._cli import parser
from reticuli._cli import report
from reticuli._cli import statusview
from reticuli._cli import views


# ==== plumbing: help, completion, the agent hook ============================

def _handle_help(args) -> int:
    if getattr(args, "all", False):
        parser._help_all()
        return 0
    topic = getattr(args, "topic", None)
    if topic is None:
        parser._help_all()
        return 0
    known = topic in parser._FULL_HELP or topic in parser._RETIRED_FOLD
    parser._help_topic(topic)
    return 0 if known else 1


def _handle_completion(args) -> int:
    shell = getattr(args, "shell", None) or "bash"
    parser._completion(shell)
    return 0


def _handle_hook(args) -> int:
    """Plumbing: record one coding-agent hook event. Never blocks the
    agent -- a malformed or unreadable payload is silently a no-op,
    the same discipline `reticuli.hooks.main` applies."""
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        payload = None
    if isinstance(payload, dict):
        payload.setdefault("hook_event_name", getattr(args, "event", None))
        try:
            hooks.event(payload)
        except Exception:
            pass
    return 0


# ==== authoring: init, the traced run =========================================

def _handle_init(args) -> int:
    path = getattr(args, "path", None) or "."
    no_agent = bool(getattr(args, "no_agent", False))
    result = handlers.init(path, no_agent=no_agent)
    env = report._r_init(result, args)
    return 0 if env["ok"] else 1


def _handle_run(args) -> int:
    """Run one command inside a workspace and return ITS exit code,
    unchanged -- the one handler that is a pass-through, not a verdict.
    Reads `args.command` (a list of tokens) when present, falling back
    to `args.cmd` (the parser's own grammar: a single literal string)."""
    tokens = getattr(args, "command", None)
    if tokens is None:
        tokens = getattr(args, "cmd", None)
    cmd = " ".join(tokens) if isinstance(tokens, (list, tuple)) else tokens
    ws = getattr(args, "workspace", None) or "."
    return handlers.run(cmd, ws=ws)


# ==== verification: identity, strength ========================================

def _handle_verify(args) -> int:
    path = getattr(args, "path", None) or "."
    try:
        result = kernel.verify(path)
    except kernel.ClaimError as exc:
        output._err("verify", str(exc))
        return 1
    env = report._r_verify(result, args)
    return 0 if env["ok"] else 1


def _handle_assess(args) -> int:
    path = getattr(args, "path", None) or "."
    try:
        result = assess.assess(path)
    except kernel.ClaimError as exc:
        output._err("assess", str(exc))
        return 1
    result = dict(result, ok=True)
    env = report._r_assess(result, args)
    return 0 if env["ok"] else 1


def _dispatch_audit(args) -> int:
    """`audit`: re-execute every gate cold. Deep (composed claims
    included) by default; `--shallow` opts out to this claim's own
    gates alone (`spec/verification.md`)."""
    path = getattr(args, "path", None) or "."
    shallow = bool(getattr(args, "shallow", False))
    try:
        base = kernel.audit(path)
        if shallow:
            result = dict(base)
        else:
            deep = registry.audit_deep(path)
            result = dict(base, ok=base["ok"] and deep["ok"], layers=deep["layers"])
    except kernel.ClaimError as exc:
        output._err("audit", str(exc))
        return 1
    env = report._r_audit(result, args)
    return 0 if env["ok"] else 1


# ==== reconstruction: rebuild, the three-machine test =========================

def _handle_rebuild(args) -> int:
    path = getattr(args, "path", None) or "."
    producer = getattr(args, "producer", None)
    if not producer:
        output._err("rebuild", "rebuild needs --producer naming the producer")
        return 2
    into = getattr(args, "into", None) or tempfile.mkdtemp(prefix="reticuli-rebuild-")
    without_guidance = bool(getattr(args, "without_guidance", False))
    try:
        result = kernel.rebuild(path, producer, into, guidance=not without_guidance)
    except kernel.ClaimError as exc:
        output._err("rebuild", str(exc))
        return 1
    result = dict(result, ok=True, into=into)
    env = report._r_rebuild(result, args)
    return 0 if env["ok"] else 1


def _dispatch_crosscheck(args) -> int:
    m1 = getattr(args, "m1", None)
    m2 = getattr(args, "m2", None)
    m3 = getattr(args, "m3", None)
    try:
        result = registry.crosscheck_deep(m1, m2, m3)
    except kernel.ClaimError as exc:
        output._err("crosscheck", str(exc))
        return 1
    result = dict(result, ok=result.get("satisfied", False))
    env = report._r_crosscheck(result, args)
    return 0 if env["ok"] else 1


# ==== composition and transport: pull, export, import =========================

def _handle_pull(args) -> int:
    component = getattr(args, "component", None)
    ws = getattr(args, "workspace", None) or os.getcwd()
    try:
        result = registry.pull(component, ws)
    except kernel.ClaimError as exc:
        output._err("pull", str(exc))
        return 1
    env = report._r_pull(result, args)
    return 0 if env["ok"] else 1


def _handle_export(args) -> int:
    path = getattr(args, "path", None) or "."
    out = getattr(args, "out", None)
    if not out:
        out = os.path.basename(os.path.abspath(path).rstrip(os.sep)) + ".tar"
    try:
        transfer.export(path, out)
    except kernel.ClaimError as exc:
        output._err("export", str(exc))
        return 1
    env = report._r_export({"ok": True, "path": out}, args)
    return 0 if env["ok"] else 1


def _handle_import(args) -> int:
    archive = getattr(args, "archive", None)
    into = getattr(args, "into", None) or "."
    try:
        result = transfer.import_(archive, into)
    except kernel.ClaimError as exc:
        output._err("import", str(exc))
        return 1
    env = report._r_import(result, args)
    return 0 if env["ok"] else 1


# ==== authoring a claim: pack =================================================

def _dispatch_pack(args) -> int:
    """`pack`: write a project's recipe, and (`--accept`) compute the
    root and seal it. An `--accept` invocation with no `-o`/`--output`
    naming the gate's verdict file is refused as a usage error, in
    words, before anything is written."""
    cmd = "pack"
    accept = getattr(args, "accept", None)
    out_name = getattr(args, "output", None)
    if accept and not out_name:
        output._err(cmd, "pack --accept needs -o/--output naming the gate's verdict file")
        return 2

    path = os.path.abspath(getattr(args, "path", None) or ".")
    name = getattr(args, "name", None)
    inputs_manifest = getattr(args, "inputs_manifest", None)

    if not accept:
        env = report._r_pack({"ok": True, "path": path, "accepted": False}, args)
        return 0 if env["ok"] else 1

    if not name:
        output._err(cmd, "pack --accept needs --name naming the claim")
        return 2

    gate = getattr(args, "gate", None)
    if not gate and getattr(args, "pytest", None):
        gate = "pytest"
    if not gate:
        output._err(cmd, "pack --accept needs --gate (or --pytest) naming the gate command")
        return 2

    generated = getattr(args, "generated", None) or []
    if isinstance(generated, str):
        generated = [generated]

    target = path
    into = getattr(args, "into", None)
    force = bool(getattr(args, "force", False))
    if into:
        target = os.path.abspath(into)
        if os.path.isdir(target) and os.listdir(target) and not force:
            output._err(cmd, f"refusing to pack into a non-empty directory without --force: {target!r}")
            return 2
        _util.copy_into(path, target)

    try:
        result = pack.pack(target, name, generated=generated, gate=gate,
                            gate_output=out_name, inputs_manifest=inputs_manifest)
    except kernel.ClaimError as exc:
        output._err(cmd, str(exc))
        return 1

    env = report._r_pack(result, args)
    return 0 if env["ok"] else 1


# ==== status, the draft/sealed/signed ladder ==================================

def _dispatch_status(args) -> int:
    path = getattr(args, "path", None) or "."
    if getattr(args, "claims", False):
        print(statusview._r_claims(path))
        return 0
    if getattr(args, "tree", False):
        print(statusview._r_tree(path))
        return 0

    try:
        view = views._claim_view(path)
    except kernel.ClaimError as exc:
        output._err("status", str(exc))
        return 1

    if view["phase"] == "draft":
        result = statusview._r_status_draft(path)
        output._finish("status", result, True, "draft", args)
        return 0

    result = statusview._ledger_status_claim(path)
    output._finish("status", result, True, result.get("phase") or "sealed",
                    args, root=result.get("root"))
    return 0


# ==== evidence: the record transport, authorization ============================

def _handle_record(args) -> int:
    path = getattr(args, "path", None) or "."
    key = getattr(args, "key", None)

    if getattr(args, "check", False):
        rec_path = getattr(args, "as_", None)
        if not rec_path:
            output._err("record", "record --check needs --as naming the record file")
            return 2
        try:
            doc = record_lib.read(rec_path)
        except kernel.ClaimError as exc:
            output._err("record", str(exc))
            return 1
        signer = record_lib.signer(rec_path, key) if key else None
        env = report._r_record({"ok": True, "record": doc, "signer": signer}, args)
        return 0 if env["ok"] else 1

    try:
        doc = record_lib.emit(path)
    except kernel.ClaimError as exc:
        output._err("record", str(exc))
        return 1
    dest = getattr(args, "as_", None) or os.path.join(path, "record.json")
    record_lib.write(doc, dest)
    if key:
        record_lib.sign(dest, key)
    env = report._r_record(dict(doc, ok=True, path=dest), args)
    return 0 if env["ok"] else 1


def _handle_sign(args) -> int:
    path = getattr(args, "path", None) or "."
    key = getattr(args, "key", None)
    if not key:
        output._err("sign", "sign needs --key naming the ssh signing key")
        return 2
    identity = getattr(args, "identity", None) or os.environ.get("USER") or "unknown"
    try:
        result = attest.sign(path, key, identity)
    except kernel.ClaimError as exc:
        output._err("sign", str(exc))
        return 1
    env = report._r_sign(dict(result, ok=True), args)
    return 0 if env["ok"] else 1


# ==== main: route a parsed verb to its handler or dispatch =====================

HANDLERS = ("_handle_help", "_handle_init", "_handle_completion", "_handle_hook",
            "_handle_run", "_handle_verify", "_handle_assess",
            "_handle_rebuild", "_handle_pull", "_handle_sign",
            "_handle_export", "_handle_record", "_handle_import")
DISPATCHES = ("_dispatch_pack", "_dispatch_audit", "_dispatch_status",
              "_dispatch_crosscheck")

_ROUTES = {
    "help": _handle_help,
    "init": _handle_init,
    "completion": _handle_completion,
    "hook": _handle_hook,
    "run": _handle_run,
    "verify": _handle_verify,
    "assess": _handle_assess,
    "rebuild": _handle_rebuild,
    "pull": _handle_pull,
    "sign": _handle_sign,
    "export": _handle_export,
    "record": _handle_record,
    "import": _handle_import,
    "pack": _dispatch_pack,
    "audit": _dispatch_audit,
    "status": _dispatch_status,
    "crosscheck": _dispatch_crosscheck,
}


def main(argv=None) -> int:
    """Parse `argv` against the grammar `reticuli._cli.parser` registers
    and route it to the matching handler or dispatch -- the one place
    this module trusts the parser's own verb names, rather than
    repeating them."""
    p, _sub = parser._parser()
    args = p.parse_args(argv)
    verb = getattr(args, "verb", None)
    if not verb:
        p.print_help()
        return 1

    canon = parser.ALIASES.get(verb, verb)
    fn = _ROUTES.get(canon)
    if fn is None:
        output._err(canon, f"unrecognized command {verb!r}")
        return 2

    try:
        return fn(args)
    except kernel.ClaimError as exc:
        output._err(canon, str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
