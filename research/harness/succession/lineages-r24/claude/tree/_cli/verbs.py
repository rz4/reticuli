"""reticuli._cli.verbs: the verb handlers (spec/layers.md "surface";
checks/verbs_check.py is this module's definition).

Every porcelain verb gets one function here: a simple verb gets a
`_handle_*`, and a verb whose behavior branches on its own flags (`pack`'s
`--accept`, `audit`'s `--shallow`, `status`'s `--tree`/`--claims`,
`crosscheck`'s legs) gets a `_dispatch_*` instead -- the name says whether
there is a decision to read before the verb's real work starts. Each one
takes an attribute-bag (`argparse.Namespace`, or an equivalent stand-in) and
returns a process exit code: `0` success, a nonzero verdict code on a
refusal the layer below raised in words, `2` on a usage error caught here
before anything is built. Handlers read their own arguments defensively
(`getattr(..., default)`), because the same function is exercised directly
with purpose-built namespaces as well as through `main`'s real argv parse,
and the two need not carry identical attribute names for every field.

`audit` composes DEEP by default (`registry.audit_deep`): a composed claim's
whole ancestry is re-earned, not just its own gates, so a forged component
cannot hide behind its dependent's gate. `--shallow` is the explicit,
honest opt-down to `kernel.audit`'s own-gates-only form.

`main` builds the grammar once (`parser._parser`), parses `argv`, and routes
the parsed verb to its handler; a `kernel.ClaimError` escaping a handler is
the one place `main` itself catches, so a refusal from any layer still
speaks through `output._err` once, uniformly. Stdlib only.
"""
import json
import os
import sys

from reticuli import hooks, kernel, pack, record, registry

from . import handlers, output, parser, report, statusview, views


# -- plumbing: help, completion, the agent-hook event -----------------------

def _handle_help(args) -> int:
    """`ret help [topic] [-a]`: one command's own usage, everything at
    once under `-a`, or the top-level usage with no topic given."""
    if getattr(args, "all", False):
        return parser._help_all()
    topic = getattr(args, "topic", None)
    if topic:
        return parser._help_topic(topic)
    p, _sub = parser._parser()
    p.print_help()
    return 0


def _handle_completion(args) -> int:
    """`ret completion [shell]`: print a shell completion script."""
    parser._completion(getattr(args, "shell", "bash"))
    return 0


def _handle_hook(args) -> int:
    """`ret hook`: the installed Claude Code hook command. The payload
    comes on stdin, never from `args`; malformed JSON is a silent no-op,
    matching the installed hook's own contract -- stdout is interpreted by
    its caller, so nothing is ever printed here."""
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0
    hooks.event(payload)
    return 0


# -- init: mark a workspace, wire the agent handshake ------------------------

def _handle_init(args) -> int:
    ws = getattr(args, "dir", ".")
    no_agent = getattr(args, "no_agent", False)
    try:
        data = handlers.init(ws, no_agent=no_agent)
    except kernel.ClaimError as e:
        output._err("init", str(e))
        return 1
    output._finish("init", data, True, "ok", args)
    return 0


# -- run: the CLI's own traced predicate -------------------------------------

def _handle_run(args) -> int:
    """Run the given command in the given workspace and hand back ITS exit
    code UNCHANGED (`handlers.run`'s own contract). Reads `command` (a list
    of shell-string parts, joined) and `workspace`; falls back to the
    argparse names (`cmd`, `dir`) the real `run` verb actually carries, so
    this one function serves both a direct call and `main`'s routing."""
    command = getattr(args, "command", None)
    if command is None:
        command = [getattr(args, "cmd", "")]
    workspace = getattr(args, "workspace", None)
    if workspace is None:
        workspace = getattr(args, "dir", ".")
    return handlers.run(" ".join(command), workspace)


# -- the straightforward verification/reconstruction verbs ------------------

def _handle_verify(args) -> int:
    envelope = report._r_verify(getattr(args, "dir", "."), args)
    return 0 if envelope["ok"] else 1


def _handle_assess(args) -> int:
    envelope = report._r_assess(getattr(args, "dir", "."), args)
    return 0 if envelope["ok"] else 1


def _handle_rebuild(args) -> int:
    """Preflight a named producer's credential before anything spends on
    it (`handlers._expand_producer`), then regrow through `kernel.rebuild`."""
    try:
        command, env = handlers._expand_producer(getattr(args, "producer", None))
    except kernel.ClaimError as e:
        output._err("rebuild", str(e))
        return 1
    args.producer = command
    args.producer_env = env
    envelope = report._r_rebuild(getattr(args, "dir", "."), args)
    return 0 if envelope["ok"] else 1


def _handle_pull(args) -> int:
    envelope = report._r_pull(getattr(args, "dir", "."), args)
    return 0 if envelope["ok"] else 1


def _handle_sign(args) -> int:
    envelope = report._r_sign(getattr(args, "dir", "."), args)
    return 0 if envelope["ok"] else 1


def _handle_export(args) -> int:
    envelope = report._r_export(getattr(args, "dir", "."), args)
    return 0 if envelope["ok"] else 1


def _handle_import(args) -> int:
    envelope = report._r_import(args)
    return 0 if envelope["ok"] else 1


def _handle_record(args) -> int:
    """`ret record`: write a signed record by default; `--check` reads one
    back and reports whether it verifies against the trust anchor instead
    -- the retired `attest --check` folded into this verb's own option."""
    d = getattr(args, "dir", ".")
    out = getattr(args, "out", None)
    key = getattr(args, "key", None)
    check = getattr(args, "check", False)
    try:
        if check:
            if not out:
                output._err("record", "--check needs --out naming the record to check")
                return 2
            anchor = os.environ.get("RETICULI_SIGNERS")
            who = record.signer(out, anchor) if anchor else None
            ok = who is not None
            output._finish("record", {"signer": who}, ok, "ok" if ok else "unverified", args)
            return 0 if ok else 1

        doc = record.emit(d)
        if out:
            record.write(doc, out)
            if key:
                record.sign(out, key)
        output._finish("record", doc, True, "ok", args, root=doc.get("root"))
        return 0
    except kernel.ClaimError as e:
        output._err("record", str(e))
        return 1


# -- pack: refuse before building, else seal a project in place -------------

def _dispatch_pack(args) -> int:
    """`ret pack`: `--accept` (the retired `seal`) needs `-o`/`--into`
    naming the sealed claim's destination -- refused in words, with exit
    2, before anything is built, so an invalid invocation never spends."""
    cmd = "pack"
    accept = getattr(args, "accept", False)
    into = getattr(args, "into", None)
    if accept and not into:
        output._err(cmd, "--accept needs -o/--into naming the sealed claim's "
                         "destination; refusing before building anything")
        return 2

    d = getattr(args, "path", None) or getattr(args, "dir", None) or "."
    raw_envelope = getattr(args, "envelope", None) or []
    envelope = {}
    for item in raw_envelope:
        unit, _, value = item.partition("=")
        if unit and value:
            envelope[unit] = float(value)

    try:
        result = pack.pack(
            d,
            getattr(args, "name", None),
            getattr(args, "generated", None) or [],
            getattr(args, "inputs", None) or [],
            getattr(args, "gate", None),
            gate_output=getattr(args, "gate_output", None) or getattr(args, "output", None) or "OK",
            claim_format=getattr(args, "format", None),
            envelope=envelope or None,
            mutation_floor=getattr(args, "mutation_floor", None),
            requires=getattr(args, "requires", None),
            inputs_manifest=getattr(args, "inputs_manifest", None),
            environment=getattr(args, "environment", None),
        )
    except kernel.ClaimError as e:
        output._err(cmd, str(e))
        return 1

    output._finish(cmd, result, True, "ok", args, root=result.get("root"))
    return 0


# -- audit: deep composition by default, shallow the explicit opt-down -----

def _dispatch_audit(args) -> int:
    """`ret audit`: re-earn the whole composed ancestry by default
    (`registry.audit_deep`) -- a forged component cannot hide behind its
    dependent's own gate. `--shallow` opts down to the claim's own gates
    only (`kernel.audit`), honestly spelled rather than silently assumed."""
    cmd = "audit"
    d = getattr(args, "claim", None) or getattr(args, "dir", None) or "."
    shallow = getattr(args, "shallow", False)
    try:
        result = kernel.audit(d) if shallow else registry.audit_deep(d)
    except kernel.ClaimError as e:
        output._err(cmd, str(e))
        return 1
    ok = bool(result.get("ok"))
    if not getattr(args, "quiet", False):
        output._finish(cmd, result, ok, "ok" if ok else "failed", args)
    return 0 if ok else 1


# -- status: one claim's own state, or the store-wide views ------------------

def _dispatch_status(args) -> int:
    """`ret status`: `--tree`/`--claims` show the store-wide views; with
    neither, a claim not yet sealed reports its draft readiness
    (`feedback.advise`, over `statusview._r_status_draft`), and a sealed
    one reports what `views._claim_view` already knows."""
    d = getattr(args, "dir", ".")
    if getattr(args, "tree", False):
        statusview._r_tree(d, args)
        return 0
    if getattr(args, "claims", False):
        statusview._r_claims(d, args)
        return 0

    if not os.path.isfile(os.path.join(d, kernel.MANIFEST)):
        envelope = statusview._r_status_draft(d, args)
        return 0 if envelope["ok"] else 1

    try:
        view = views._claim_view(d)
    except kernel.ClaimError as e:
        output._err("status", str(e))
        return 1

    if getattr(args, "json", False):
        output._finish("status", view, view["verified"], view["phase"], args, root=view["root"])
    else:
        text = statusview._v_status_claim(d) if getattr(args, "verbose", False) \
            else statusview._t_status_claim(d)
        print(text)
    return 0 if view["verified"] else 1


# -- crosscheck: the three-machine test --------------------------------------

def _dispatch_crosscheck(args) -> int:
    envelope = report._r_crosscheck(args.m1, args.m2, args.m3, args)
    return 0 if envelope["ok"] else 1


# -- main: build the grammar, parse argv, route ------------------------------

_ROUTES = {
    "init": _handle_init,
    "run": _handle_run,
    "status": _dispatch_status,
    "pack": _dispatch_pack,
    "pull": _handle_pull,
    "export": _handle_export,
    "import": _handle_import,
    "verify": _handle_verify,
    "audit": _dispatch_audit,
    "assess": _handle_assess,
    "rebuild": _handle_rebuild,
    "crosscheck": _dispatch_crosscheck,
    "record": _handle_record,
    "sign": _handle_sign,
    "hook": _handle_hook,
    "help": _handle_help,
    "completion": _handle_completion,
}


def main(argv=None) -> int:
    """Build the grammar fresh, parse `argv` (or `sys.argv[1:]`), and route
    to the matching verb's handler. A `kernel.ClaimError` that escapes a
    handler is caught once, here, so every verb refuses through the same
    one-voice line regardless of which layer raised it."""
    p, _sub = parser._parser()
    args = p.parse_args(argv)
    verb = getattr(args, "verb", None)
    if verb is None:
        p.print_help()
        return 0
    handler = _ROUTES.get(verb)
    if handler is None:
        output._err(verb, "no such command")
        return 2
    try:
        return handler(args)
    except kernel.ClaimError as e:
        output._err(verb, str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
