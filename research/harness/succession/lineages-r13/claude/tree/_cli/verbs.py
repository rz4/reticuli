"""The verb handlers: `main()`'s own routing table (spec/layers.md's
surface layer).

Each porcelain verb gets one `_handle_*` function; the four verbs whose
behavior is more than "call one lower-layer function and render the
result" (`pack`, `audit`, `status`, `crosscheck`) get a `_dispatch_*`
function instead -- the split is naming only, both kinds return the
process's own exit code, having already printed through `output.py`'s
one-voice envelope or error line.

Two handlers carry a sharper contract than "whatever the CLI needs", because
they are the two cleanly isolable from argparse's own shape: `_handle_run`
returns the child's exit code unchanged (never translated into a different
one), reading `args.command` (a string, or a list of tokens to join) and
`args.workspace` rather than the parser's own `cmd`/`ws` dest names, so a
caller can drive it directly without building a `Namespace` through
`argparse`. `_dispatch_pack` refuses an invalid invocation -- `--accept`
without `-o`/`--output` naming the gate's own verdict file -- in words, with
exit code 2, before anything is built.

This module reaches `reticuli.kernel` and every layer above it; it never
reaches into `reticuli._kernel` directly (spec/layers.md).
"""
import json
import os
import shutil
import sys
import tempfile
from types import SimpleNamespace

from . import handlers
from . import output
from . import parser
from . import report
from . import statusview
from . import views

from .. import assess as assess_mod
from .. import attest
from .. import hooks
from .. import kernel
from .. import pack as pack_mod
from .. import record as record_mod
from .. import registry
from .. import transfer

HANDLERS = ("_handle_help", "_handle_init", "_handle_completion", "_handle_hook",
            "_handle_run", "_handle_verify", "_handle_assess",
            "_handle_rebuild", "_handle_pull", "_handle_sign",
            "_handle_export", "_handle_record", "_handle_import")
DISPATCHES = ("_dispatch_pack", "_dispatch_audit", "_dispatch_status",
              "_dispatch_crosscheck")


# -------------------------------------------------------------- rendering --

def _detail(args, renderer, result) -> None:
    """The `-v` detail block, printed before the one-line summary -- never
    under `--json`, where the envelope is the only output."""
    if renderer is None:
        return
    if getattr(args, "verbose", False) and not getattr(args, "json", False):
        print(renderer(result))


def _emit(command: str, result, args, renderer=None, ok: bool = True,
          status: str = "ok", root: str = None) -> int:
    """Finish a verb that already has its result in hand: the `-v` block,
    then the envelope (through `output._finish`), then the exit code the
    result itself earned -- 0 when it holds, 1 when it does not."""
    _detail(args, renderer, result)
    output._finish(command, result, ok, status, args, root=root)
    return 0 if ok else 1


# ----------------------------------------------------------------- plumbing --

def _handle_help(args) -> int:
    """`ret help [topic] [-a]`: the full grammar, one verb's own detail, or
    (with neither) the plain `-h` text."""
    if getattr(args, "all", False):
        parser._help_all()
        return 0
    topic = getattr(args, "topic", None)
    if topic:
        parser._help_topic(topic)
        return 0
    p, _ = parser._parser()
    p.print_help()
    return 0


def _handle_completion(args) -> int:
    """`ret completion [shell]`: a shell completion script, generated from
    the grammar the parser itself accepts."""
    parser._completion(getattr(args, "shell", "bash"))
    return 0


def _handle_hook(args) -> int:
    """`ret hook`: forward one coding-agent hook payload (read as JSON from
    stdin) into the current session's draft trace."""
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        payload = None
    hooks.event(payload)
    return 0


# ------------------------------------------------------------------- init --

def _handle_init(args) -> int:
    """`ret init [path] [--no-agent]`: mark a workspace, wiring the
    coding-agent handshake unless told not to."""
    try:
        result = handlers.init(args.path, no_agent=getattr(args, "no_agent", False))
    except handlers.HandlerError as exc:
        output._err("init", str(exc))
        return 1
    return _emit("init", result, args, renderer=report._r_init, status="initialized")


# -------------------------------------------------------------------- run --

def _handle_run(args) -> int:
    """`ret run <cmd> [ws]`: run `cmd` with `ws` as its working directory,
    tracing it first if `ws` is a marked workspace. Returns the child's own
    exit code unchanged -- never translated into a different one -- reading
    `args.command` (a string, or a list of tokens joined with spaces) and
    `args.workspace`, so a caller can drive this directly without building
    an `argparse.Namespace`."""
    command = args.command
    cmd = command if isinstance(command, str) else " ".join(command)
    ws = getattr(args, "workspace", ".")
    return handlers.run(cmd, ws)


# ---------------------------------------------------------------- verify --

def _handle_verify(args) -> int:
    """`ret verify [path]`: the sealed root against what the bytes present
    recompute to."""
    try:
        result = kernel.verify(args.path)
    except kernel.ClaimError as exc:
        output._err("verify", str(exc))
        return 1
    status = "verified" if result.get("ok") else "mismatch"
    return _emit("verify", result, args, renderer=report._r_verify,
                 ok=bool(result.get("ok")), status=status, root=result.get("root"))


# ---------------------------------------------------------------- assess --

def _handle_assess(args) -> int:
    """`ret assess [path]`: a mutation-testing budget, bucketed into what
    the tests actually proved."""
    try:
        result = assess_mod.assess(args.path)
    except kernel.ClaimError as exc:
        output._err("assess", str(exc))
        return 1
    return _emit("assess", result, args, renderer=report._r_assess, status="measured")


# --------------------------------------------------------------- rebuild --

def _handle_rebuild(args) -> int:
    """`ret rebuild [path] [--producer NAME] [--into DIR]`: regrow a
    claim's generated outputs into a fresh room, blind to the one already
    on disk."""
    producer = getattr(args, "producer", None)
    if not producer:
        output._err("rebuild", "needs --producer naming a producer command or shortcut")
        return 2
    try:
        cmd, env = handlers._expand_producer(producer)
    except handlers.HandlerError as exc:
        output._err("rebuild", str(exc))
        return 1

    into = getattr(args, "into", None) or tempfile.mkdtemp(prefix="reticuli-rebuild-")
    try:
        result = kernel.rebuild(args.path, cmd, into, producer_env=env or None)
    except kernel.ClaimError as exc:
        output._err("rebuild", str(exc))
        return 1

    result = dict(result)
    result["into"] = into
    return _emit("rebuild", result, args, renderer=report._r_rebuild,
                 status=result.get("status", "ok"), root=result.get("root"))


# ----------------------------------------------------------------- pull --

def _handle_pull(args) -> int:
    """`ret pull <component> [path]`: materialize another claim's bytes
    into the workspace as a dependency."""
    try:
        result = registry.pull(args.component, args.path)
    except kernel.ClaimError as exc:
        output._err("pull", str(exc))
        return 1
    return _emit("pull", result, args, renderer=report._r_pull, status="pulled",
                 root=result.get("root"))


# ----------------------------------------------------------------- sign --

def _handle_sign(args) -> int:
    """`ret sign [path] [--key KEY]`: the signing ceremony over the claim's
    own signature-chain root."""
    key = getattr(args, "key", None)
    if not key:
        output._err("sign", "needs --key naming a signing key")
        return 2
    principal = os.environ.get("USER") or os.environ.get("USERNAME") or "unknown"
    try:
        result = attest.sign(args.path, key, principal)
    except kernel.ClaimError as exc:
        output._err("sign", str(exc))
        return 1
    return _emit("sign", result, args, renderer=report._r_sign, status="signed",
                 root=result.get("root"))


# --------------------------------------------------------------- export --

def _handle_export(args) -> int:
    """`ret export [path] [--out FILE]`: a deterministic tar of the
    claim's own declared content."""
    try:
        manifest = kernel.read_manifest(args.path)
    except kernel.ClaimError as exc:
        output._err("export", str(exc))
        return 1
    out = getattr(args, "out", None) or f"{manifest['name']}-{manifest['root'][:12]}.tar"
    try:
        result = transfer.export(args.path, out)
    except kernel.ClaimError as exc:
        output._err("export", str(exc))
        return 1
    result = dict(result)
    result["out"] = out
    return _emit("export", result, args, renderer=report._r_export,
                 ok=bool(result.get("ok")), status="exported")


# --------------------------------------------------------------- import --

def _handle_import(args) -> int:
    """`ret import <archive> [path]`: extract and reseal a transferred
    claim -- identity recomputed from the bytes received, never trusted
    off the wire."""
    try:
        result = transfer.import_(args.archive, args.path)
    except kernel.ClaimError as exc:
        output._err("import", str(exc))
        return 1
    ok = bool(result.get("ok"))
    status = "imported" if ok else "mismatch"
    return _emit("import", result, args, renderer=report._r_import, ok=ok,
                 status=status, root=result.get("root"))


# --------------------------------------------------------------- record --

def _handle_record(args) -> int:
    """`ret record [path] [--key KEY] [--as NAME] [--check]`: write (or,
    with `--check`, review) a signed statement of one machine's results."""
    as_name = getattr(args, "as_name", None) or "record"
    path = os.path.join(args.path, as_name + ".json")

    if getattr(args, "check", False):
        try:
            doc = kernel.record_read(path)
        except kernel.ClaimError as exc:
            output._err("record", str(exc))
            return 1
        return _emit("record", doc, args, renderer=report._r_record, status="checked",
                     root=doc.get("root"))

    try:
        doc = record_mod.emit(args.path)
    except kernel.ClaimError as exc:
        output._err("record", str(exc))
        return 1
    record_mod.write(doc, path)
    key = getattr(args, "key", None)
    if key:
        record_mod.sign(path, key)

    doc = dict(doc)
    doc["path"] = path
    return _emit("record", doc, args, renderer=report._r_record, status="written",
                 root=doc.get("root"))


# =========================================================== dispatches --

def _dispatch_pack(args) -> int:
    """`ret pack [path] [--accept]` (and the richer invocation this
    function also accepts: `--name`, `--generated`, `--gate`/`--pytest`,
    `-o`/`--output`, `--root`, `--into`): create a claim from a project
    directory in place. `--accept` refuses -- in words, with exit code 2,
    before anything is built -- unless `-o`/`--output` names the gate's
    own verdict file."""
    accept = getattr(args, "accept", False)
    output_name = getattr(args, "output", None)
    if accept and not output_name:
        output._err("pack", "--accept needs -o/--output naming the gate's verdict file")
        return 2

    d = getattr(args, "path", None) or "."
    name = getattr(args, "name", None) or os.path.basename(os.path.abspath(d).rstrip(os.sep))
    generated = getattr(args, "generated", None) or []
    gate = getattr(args, "gate", None)
    gate_output = output_name or "OK"
    pytest_target = getattr(args, "pytest", None)
    if not gate and pytest_target:
        gate = f"pytest {pytest_target} && printf ok > {gate_output}"
    if not gate:
        output._err("pack", "needs --gate (or --pytest) naming how the claim is checked")
        return 2

    try:
        result = pack_mod.pack(d, name, generated, [], gate, gate_output)
    except kernel.ClaimError as exc:
        output._err("pack", str(exc))
        return 1

    expected_root = getattr(args, "root", None)
    if expected_root and result.get("root") != expected_root:
        output._err(
            "pack", f"sealed root {result.get('root')} does not match "
                    f"expected {expected_root}")
        return 1

    into = getattr(args, "into", None)
    if into:
        shutil.copytree(d, into, dirs_exist_ok=True)

    return _emit("pack", result, args, renderer=report._r_pack,
                 ok=bool(result.get("ok")), status="sealed", root=result.get("root"))


def _dispatch_audit(args) -> int:
    """`ret audit [path]`: rerun a claim's acceptance criteria cold."""
    try:
        result = kernel.audit(args.path)
    except kernel.ClaimError as exc:
        output._err("audit", str(exc))
        return 1
    ok = bool(result.get("ok"))
    status = result.get("verdict", "reject")
    return _emit("audit", result, args, renderer=report._r_audit, ok=ok, status=status,
                 root=result.get("root"))


def _dispatch_status(args) -> int:
    """`ret status [path] [--tree] [--claims]`: a claim's own work, phase,
    and unresolved inputs -- or, with `--claims`/`--tree`, the workspace's
    registry read as a list or a dependency graph."""
    d = getattr(args, "path", None) or "."
    show_json = getattr(args, "json", False)

    if getattr(args, "claims", False):
        result = registry.claims(d)
        if not show_json:
            print(statusview._r_claims(result))
        output._finish("status", {"claims": result}, True, "claims", args)
        return 0

    if getattr(args, "tree", False):
        deps = registry.deps(d)
        if not show_json:
            print(statusview._r_deps(deps))
        output._finish("status", deps, True, "tree", args)
        return 0

    view = views._claim_view(d)
    if not show_json:
        print(statusview._t_status_claim(view))
        if getattr(args, "verbose", False):
            print(statusview._v_status_claim(view))
            print(statusview._files_claim(d))
            print(statusview._ledger_status_claim(views._read_residue(d)))
    ok = view.get("phase") != "invalid"
    output._finish("status", view, ok, view.get("phase", "unknown"), args,
                    root=view.get("root"))
    return 0 if ok else 1


def _dispatch_crosscheck(args) -> int:
    """`ret crosscheck <path> [path...]`: the three-machine test over
    exactly three legs -- a claim directory or a frozen record, either
    one."""
    paths = list(getattr(args, "paths", None) or [])
    if len(paths) != 3:
        output._err("crosscheck", "needs exactly three legs: m1 m2 m3")
        return 2
    try:
        result = kernel.crosscheck(*paths)
    except kernel.ClaimError as exc:
        output._err("crosscheck", str(exc))
        return 1
    ok = bool(result.get("satisfied"))
    status = result.get("verdict", "reject")
    return _emit("crosscheck", result, args, renderer=report._r_crosscheck, ok=ok,
                 status=status)


# ------------------------------------------------------------------- main --

_ROUTES = {
    "help": _handle_help,
    "completion": _handle_completion,
    "hook": _handle_hook,
    "init": _handle_init,
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
    """`ret`'s own entry point: parse argv against the grammar, resolve any
    accepted older spelling to its porcelain verb, and route to that verb's
    own handler or dispatch."""
    argv = sys.argv[1:] if argv is None else argv
    p, choices = parser._parser()
    args = p.parse_args(argv)

    verb = args.verb
    if verb is None:
        p.print_help()
        return 0
    canonical = parser.ALIASES.get(verb, verb)

    if canonical == "run":
        args = SimpleNamespace(command=[args.cmd], workspace=args.ws,
                                verbose=args.verbose, json=args.json)
        return _handle_run(args)

    route = _ROUTES.get(canonical)
    if route is None:
        p.error(f"unknown command: {verb!r}")
        return 2
    return route(args)


if __name__ == "__main__":
    sys.exit(main())
