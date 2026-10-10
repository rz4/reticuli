"""The verb surface: one `_handle_<verb>`/`_dispatch_<verb>` per porcelain
command in `parser.PORCELAIN`, plus the plumbing (`help`, `completion`,
`hook`). Each function takes the verb's own parsed `args` namespace and
returns an integer exit code; printing goes through `output`/`report`/
`statusview`, never a bare `print`, so `--json` stays the one and only
thing on stdout when it is set.

A `_handle_*` verb is a direct call into one lower-layer function. A
`_dispatch_*` verb composes more than one call because the right thing to
run depends on the claim's own shape or the caller's flags:

- `pack` validates its invocation (a usage error refuses in words, before
  touching disk) and then builds the recipe and seals.
- `audit` re-earns a composed claim's whole dependency chain by default
  (`registry.audit_deep`, folded with the claim's own `kernel.audit`); a
  forged component invisible to its own gate still fails here. `--shallow`
  is the explicit, honest opt-down to the claim's own gates alone.
- `status` shows one claim's ladder, or a workspace's claim/dependency
  listing, depending on what the caller pointed it at.
- `crosscheck` assembles the three-machine test over whatever its legs
  are -- a claim directory or a signed record, mixed freely -- deep-auditing
  every directory leg by default, same as `audit`.

`main()` is the thin router from a parsed argv to these two tables; nothing
below it needs argparse at all, which is what lets the conformance gate
call every handler directly with a hand-built namespace.
"""
import json
import os
import sys

from .. import assess
from .. import attest
from .. import heldout
from .. import hooks
from .. import kernel
from .. import pack
from .. import record
from .. import registry
from .. import transfer
from . import handlers
from . import output
from . import parser
from . import report
from . import statusview
from . import views


def _as_patterns(value) -> list:
    """A `generated=`/`inputs=` argument, normalized to a list of pattern
    strings -- `None` becomes no patterns at all, a bare string is one
    pattern, not one pattern per character."""
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    return list(value)


# ----------------------------------------------------------------- help --

def _handle_help(args) -> int:
    if getattr(args, "all", False) or not getattr(args, "topic", None):
        return parser._help_all()
    return parser._help_topic(args.topic)


def _handle_completion(args) -> int:
    return parser._completion(getattr(args, "shell", None) or "bash")


def _handle_hook(args) -> int:
    """The coding-agent hook entry point: one JSON payload on stdin,
    mapped to a trace event and appended to the session's trace. Malformed
    input or an event `hooks.event` does not recognize is a no-op, never a
    refusal -- a hook that crashes a coding agent's own turn is worse than
    one that silently traces nothing."""
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    try:
        hooks.event(payload)
    except Exception:
        pass
    return 0


# ----------------------------------------------------------------- init --

def _handle_init(args) -> int:
    ws = getattr(args, "path", None) or "."
    result = handlers.init(ws, no_agent=getattr(args, "no_agent", False))
    envelope = report._r_init(result, args)
    return 0 if envelope["ok"] else 1


# ------------------------------------------------------------------ run --

def _handle_run(args) -> int:
    """Run `args.command` inside `args.workspace`, returning the child's
    exit code UNCHANGED -- so a session can chain `ret run` as a
    predicate, same as `handlers.run` itself promises."""
    cmd = args.command
    if isinstance(cmd, (list, tuple)):
        cmd = " ".join(cmd)
    ws = getattr(args, "workspace", None) or getattr(args, "path", None) or "."
    return handlers.run(cmd, ws)


# --------------------------------------------------------------- verify --

def _handle_verify(args) -> int:
    d = getattr(args, "claim", None) or getattr(args, "path", None) or "."
    try:
        result = kernel.verify(d)
    except kernel.ClaimError as exc:
        output._err("verify", str(exc))
        return 1
    envelope = report._r_verify(result, args)
    return 0 if envelope["ok"] else 1


# --------------------------------------------------------------- assess --

def _handle_assess(args) -> int:
    d = getattr(args, "claim", None) or "."
    mutants = getattr(args, "mutants", None) or 20
    try:
        result = dict(assess.assess(d, mutants))
        if getattr(args, "coverage", False):
            result["coverage"] = heldout.coverage(d)
    except kernel.ClaimError as exc:
        output._err("assess", str(exc))
        return 1
    envelope = report._r_assess(result, args)
    return 0 if envelope["ok"] else 1


# -------------------------------------------------------------- rebuild --

def _handle_rebuild(args) -> int:
    d = getattr(args, "claim", None) or "."
    into = getattr(args, "into", None)
    if not into:
        output._err("rebuild", "needs --into naming the fresh target directory")
        return 2
    producer = getattr(args, "producer", None) or os.environ.get("RETICULI_PRODUCER")
    if not producer:
        output._err("rebuild", "no producer given; pass --producer or set RETICULI_PRODUCER")
        return 2

    try:
        comp_links = registry.components(d)
    except kernel.ClaimError:
        comp_links = []

    try:
        if comp_links:
            result = registry.rebuild_chain(d, producer, into, reuse=getattr(args, "reuse", False))
        else:
            result = kernel.rebuild(
                d, producer, into,
                guidance=not getattr(args, "without_guidance", False),
            )
    except kernel.ClaimError as exc:
        output._err("rebuild", str(exc))
        return 1
    report._r_rebuild(result, args)
    return 0


# ----------------------------------------------------------------- pull --

def _handle_pull(args) -> int:
    src = getattr(args, "claim", None) or getattr(args, "source", None)
    ws = getattr(args, "path", None) or "."
    if not src:
        output._err("pull", "needs the claim to pull")
        return 2
    try:
        result = registry.pull(src, ws)
    except kernel.ClaimError as exc:
        output._err("pull", str(exc))
        return 1
    report._r_pull(result, args)
    return 0


# ----------------------------------------------------------------- sign --

def _handle_sign(args) -> int:
    d = getattr(args, "claim", None) or "."
    key = getattr(args, "key", None)
    identity = getattr(args, "identity", None)
    if not key or not identity:
        output._err("sign", "needs --key and --identity")
        return 2
    try:
        result = attest.sign(d, key, identity, getattr(args, "workspace", None))
    except kernel.ClaimError as exc:
        output._err("sign", str(exc))
        return 1
    report._r_sign(result, args)
    return 0


# --------------------------------------------------------------- export --

def _handle_export(args) -> int:
    d = getattr(args, "claim", None) or "."
    out = getattr(args, "output", None)
    if not out:
        output._err("export", "needs -o/--output naming the archive path")
        return 2
    try:
        transfer.export(d, out, blind=getattr(args, "blind", False))
        root = kernel.read_manifest(d).get("root")
    except kernel.ClaimError as exc:
        output._err("export", str(exc))
        return 1
    report._r_export({"path": out, "root": root}, args)
    return 0


# --------------------------------------------------------------- import --

def _handle_import(args) -> int:
    archive = getattr(args, "archive", None) or getattr(args, "path", None)
    dest = getattr(args, "into", None)
    if not archive or not dest:
        output._err("import", "needs an archive path and --into naming the destination")
        return 2
    try:
        result = transfer.import_(archive, dest)
    except kernel.ClaimError as exc:
        output._err("import", str(exc))
        return 1
    envelope = report._r_import(result, args)
    return 0 if envelope["ok"] else 1


# --------------------------------------------------------------- record --

def _handle_record(args) -> int:
    d = getattr(args, "claim", None) or "."
    try:
        doc = record.emit(d)
    except kernel.ClaimError as exc:
        output._err("record", str(exc))
        return 1
    out = getattr(args, "output", None)
    if out:
        record.write(doc, out)
        key = getattr(args, "key", None)
        if key:
            record.sign(out, key)
    report._r_record(doc, args)
    return 0


# ----------------------------------------------------------------- pack --

def _dispatch_pack(args) -> int:
    """Validate the invocation in words, before touching disk, then build
    and seal. `--accept` names the gate verdict's expected content; it is
    meaningless without `-o` naming which file that is, so it refuses
    first rather than guessing."""
    if getattr(args, "accept", None) and not getattr(args, "output", None):
        output._err("pack", "--accept needs -o/--output naming the gate's verdict file")
        return 2

    root = getattr(args, "path", None) or getattr(args, "root", None)
    if not root:
        output._err("pack", "needs a project directory to pack")
        return 2

    gate_output = getattr(args, "output", None)
    if not gate_output:
        output._err("pack", "needs -o/--output naming the gate's verdict file")
        return 2

    gate = getattr(args, "gate", None)
    if not gate and getattr(args, "pytest", None):
        gate = f"pytest && printf ok > {gate_output}"
    if not gate:
        output._err("pack", "needs --gate (or --pytest) naming the acceptance command")
        return 2

    name = getattr(args, "name", None) or os.path.basename(os.path.abspath(root))
    generated = _as_patterns(getattr(args, "generated", None))
    inputs = _as_patterns(getattr(args, "inputs", None))

    if getattr(args, "force", False):
        manifest_path = os.path.join(root, kernel.MANIFEST)
        if os.path.isfile(manifest_path):
            os.remove(manifest_path)

    try:
        result = pack.pack(root, name, generated, inputs, gate, gate_output)
    except kernel.ClaimError as exc:
        output._err("pack", str(exc))
        return 1

    accepted = getattr(args, "accept", None)
    if accepted:
        out_path = os.path.join(root, gate_output)
        try:
            with open(out_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
        except OSError as exc:
            output._err("pack", f"cannot verify --accept: {exc}")
            return 1
        if content not in accepted:
            output._err("pack", f"gate output does not match --accept: {content!r}")
            return 1

    report._r_pack(result, args)
    return 0


# ---------------------------------------------------------------- audit --

def _dispatch_audit(args) -> int:
    """Re-earn a claim's own gates, and -- unless `--shallow` opts down --
    re-earn its whole declared dependency chain too, so a component
    forged in a way its own gate cannot see still fails under its
    dependent's name."""
    d = args.claim
    try:
        result = dict(kernel.audit(d))
    except kernel.ClaimError as exc:
        output._err("audit", str(exc))
        return 1

    ok = result["ok"]
    if not getattr(args, "shallow", False):
        try:
            comp_links = registry.components(d)
        except kernel.ClaimError:
            comp_links = []
        if comp_links:
            deep = registry.audit_deep(d)
            result["deep"] = deep
            ok = ok and deep["ok"]
    result["ok"] = ok

    if not getattr(args, "quiet", False):
        report._r_audit(result, args)
    return 0 if ok else 1


# --------------------------------------------------------------- status --

def _dispatch_status(args) -> int:
    """One claim's ladder when pointed at a claim; a workspace's own
    claim/dependency listing otherwise, or when `--tree`/`--claims`/
    `--deps` asks for it explicitly."""
    ws = getattr(args, "path", None) or "."

    if getattr(args, "tree", False):
        return 0 if statusview._r_tree(ws, args)["ok"] else 1
    if getattr(args, "claims", False):
        return 0 if statusview._r_claims(ws, args)["ok"] else 1
    if getattr(args, "deps", False):
        return 0 if statusview._r_deps(ws, args)["ok"] else 1

    claim = getattr(args, "claim", None) or ws
    has_recipe = (os.path.isfile(os.path.join(claim, kernel.RECIPE))
                  or os.path.isfile(os.path.join(claim, kernel.LEGACY_RECIPE)))
    if not has_recipe:
        return 0 if statusview._r_claims(ws, args)["ok"] else 1

    try:
        ph = kernel.phase(claim)
    except kernel.ClaimError as exc:
        output._err("status", str(exc))
        return 1

    if ph == "draft":
        return 0 if statusview._r_status_draft(claim, args)["ok"] else 1

    view = views._claim_view(claim)
    if report._verbose(args):
        output._line(statusview._v_status_claim(view), args=args)
    else:
        output._line(statusview._t_status_claim(view), args=args)
    envelope = output._finish("status", view, bool(view.get("verified")),
                               view.get("phase") or "draft", args, view.get("root"))
    return 0 if envelope["ok"] else 1


# ------------------------------------------------------------ crosscheck --

def _dispatch_crosscheck(args) -> int:
    """The three-machine test over whatever its three legs are -- a claim
    directory or a signed record, mixed freely -- deep-auditing every
    directory leg by default, same as `audit`; `--shallow` opts down to
    the plain, non-recursive comparison."""
    m1 = getattr(args, "m1", None)
    m2 = getattr(args, "m2", None)
    m3 = getattr(args, "m3", None)
    if not (m1 and m2 and m3):
        output._err("crosscheck", "needs three legs: --m1, --m2, --m3 "
                                   "(each a claim directory or a signed record)")
        return 2

    mutants = getattr(args, "mutants", None)
    deep = not getattr(args, "shallow", False) and all(os.path.isdir(p) for p in (m1, m2, m3))
    try:
        if deep:
            result = registry.crosscheck_deep(m1, m2, m3, mutants=mutants)
        else:
            result = kernel.crosscheck(m1, m2, m3, mutants=mutants)
    except kernel.ClaimError as exc:
        output._err("crosscheck", str(exc))
        return 1

    if result["satisfied"] and getattr(args, "record", False):
        try:
            kernel.record_proof(m1, m2, m3)
        except kernel.ClaimError as exc:
            output._err("crosscheck", str(exc))

    envelope = report._r_crosscheck(result, args)
    return 0 if envelope["ok"] else 1


# ----------------------------------------------------------------- main --

_HANDLERS = {
    "help": _handle_help, "init": _handle_init, "completion": _handle_completion,
    "hook": _handle_hook, "run": _handle_run, "verify": _handle_verify,
    "assess": _handle_assess, "rebuild": _handle_rebuild, "pull": _handle_pull,
    "sign": _handle_sign, "export": _handle_export, "record": _handle_record,
    "import": _handle_import,
}

_DISPATCHES = {
    "pack": _dispatch_pack, "audit": _dispatch_audit,
    "status": _dispatch_status, "crosscheck": _dispatch_crosscheck,
}


def main(argv=None) -> int:
    """Parse `argv` against `parser`'s grammar and route to the verb's own
    handler or dispatch -- the one place either table is read as a whole."""
    p, _ = parser._parser()
    args = p.parse_args(argv)
    verb = parser.ALIASES.get(args.verb, args.verb)
    if verb is None:
        p.print_help()
        return 0
    fn = _HANDLERS.get(verb) or _DISPATCHES.get(verb)
    if fn is None:
        output._err("ret", f"no such command: {args.verb}")
        return 2
    return fn(args)


if __name__ == "__main__":
    sys.exit(main())
