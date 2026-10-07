"""The verb surface: one `_handle_*`/`_dispatch_*` function per porcelain
verb, plus the plumbing (`hook`, `help`, `completion`), and `main()` --
the thing `ret` actually runs (`spec/layers.md`'s surface layer).

A `_handle_*` binds one verb straight onto a single layer call, through
the CLI's one output contract (`report._generic_contract` /
`output._finish`/`_err`). A `_dispatch_*` picks among a verb's own
branches first (`pack`'s `--accept`, `status`'s `--tree`/`--claims`/
`--deps`/`--structure`, `crosscheck`'s `--deep`) before doing the same.
Every one of them returns a process-style exit code (0 ok, 1 a layer
refusal, 2 a usage error caught before anything was built) -- `main()`
just parses argv with `_cli/parser.py`'s grammar and `sys.exit`s what the
matched verb returns.

`run` and `pack` are this module's two directly-tested behaviors: `run`
passes a child command's exit code through unchanged, and `pack` refuses
`--accept` without `-o`/`--output` (nothing to seal without knowing the
gate's pinned output) before it writes anything. `_arg` reads an
argument under any of several attribute names, so a handler is not
pinned to one exact argparse `dest` spelling.

Stdlib only.
"""
import os

from .. import hooks
from .. import kernel
from .. import pack as pack_mod
from .. import record as record_mod
from .. import registry
from . import handlers
from . import output
from . import parser
from . import report
from . import statusview

_MISSING = object()


def _arg(args, *names, default=None):
    """The first of `names` present (and not `None`) on `args`."""
    for name in names:
        value = getattr(args, name, _MISSING)
        if value is not _MISSING and value is not None:
            return value
    return default


# ---------------------------------------------------------------------------
# init / run: session setup and a traced run
# ---------------------------------------------------------------------------

def _handle_init(args) -> int:
    ws = _arg(args, "path", "ws", default=".")
    no_agent = bool(_arg(args, "no_agent", default=False))
    env = report._generic_contract(
        "init", lambda ws: handlers.init(ws, no_agent=no_agent), args, ws)
    return 0 if env["ok"] else 1


def _handle_run(args) -> int:
    """Run the child command for real and return its exit code UNCHANGED
    -- this handler is the predicate contract itself, not an envelope
    around it."""
    command = _arg(args, "command", "cmd")
    if isinstance(command, (list, tuple)):
        command = " ".join(command)
    ws = _arg(args, "workspace", "ws", default=".")
    return handlers.run(command, ws)


# ---------------------------------------------------------------------------
# status: the branching view of a workspace or a sealed claim
# ---------------------------------------------------------------------------

def _status_claim(d: str, args) -> dict:
    def _run(d):
        view = statusview._v_status_claim(d)
        view["ok"] = True
        return view
    env = report._generic_contract("status", _run, args, d)
    if not getattr(args, "json", False):
        print(statusview._t_status_claim(env["data"]))
    return env


def _dispatch_status(args) -> int:
    path = _arg(args, "path", default=".")
    ws = _arg(args, "ws")
    if _arg(args, "tree", default=False):
        env = statusview._r_tree(path, args, ws=ws)
    elif _arg(args, "claims", default=False):
        env = statusview._r_claims(path, args)
    elif _arg(args, "deps", default=False):
        env = statusview._r_deps(path, args)
    elif _arg(args, "structure", default=False):
        env = statusview._r_structure(path, args)
    elif os.path.isfile(os.path.join(os.path.abspath(path), kernel.MANIFEST)):
        env = _status_claim(path, args)
    else:
        env = statusview._r_status_draft(path, args)
    return 0 if env["ok"] else 1


# ---------------------------------------------------------------------------
# pack: seal a project as a self-claim
# ---------------------------------------------------------------------------

def _dispatch_pack(args) -> int:
    proj = _arg(args, "path", "root", default=".")
    name = _arg(args, "name") or os.path.basename(
        os.path.abspath(proj).rstrip(os.sep))
    generated = _arg(args, "generated", default=[]) or []
    inputs = _arg(args, "inputs", default=[]) or []
    gate = _arg(args, "gate")
    gate_output = _arg(args, "output")
    pytest_flag = _arg(args, "pytest")
    accept = _arg(args, "accept")

    if pytest_flag and not gate:
        gate = "pytest -q"

    # --accept without -o/--output is refused in words, before anything
    # is built: there is nothing to seal without knowing the gate's own
    # pinned verdict file.
    if accept and not gate_output:
        output._err(
            "pack",
            "refused: --accept requires -o/--output naming the gate's pinned verdict file")
        return 2
    if not gate:
        output._err("pack", "refused: pack requires --gate")
        return 2
    if not gate_output:
        output._err(
            "pack",
            "refused: pack requires -o/--output naming the gate's pinned verdict file")
        return 2

    try:
        result = pack_mod.pack(proj, name, generated=generated, inputs=inputs,
                                gate=gate, gate_output=gate_output)
    except kernel.ClaimError as e:
        output._err("pack", str(e))
        return 1

    data = dict(result)
    data["accepted"] = bool(accept)
    env = output._finish("pack", data, True, "sealed", args, result.get("root"))
    return 0 if env["ok"] else 1


# ---------------------------------------------------------------------------
# pull / export / import: composition and transport
# ---------------------------------------------------------------------------

def _handle_pull(args) -> int:
    claim = _arg(args, "claim")
    ws = _arg(args, "ws")
    env = report._r_pull(args, claim, ws)
    return 0 if env["ok"] else 1


def _handle_export(args) -> int:
    d = _arg(args, "claim")
    tar_path = _arg(args, "tar_path")
    blind = bool(_arg(args, "blind", default=False))
    env = report._r_export(d, args, tar_path, blind)
    return 0 if env["ok"] else 1


def _handle_import(args) -> int:
    tar_path = _arg(args, "tar_path")
    into = _arg(args, "into")
    env = report._r_import(args, tar_path, into)
    return 0 if env["ok"] else 1


# ---------------------------------------------------------------------------
# verify / audit / assess: verification
# ---------------------------------------------------------------------------

def _handle_verify(args) -> int:
    d = _arg(args, "claim", default=".")
    env = report._r_verify(d, args)
    return 0 if env["ok"] else 1


def _dispatch_audit(args) -> int:
    d = _arg(args, "claim", default=".")
    env = report._r_audit(d, args)
    return 0 if env["ok"] else 1


def _handle_assess(args) -> int:
    d = _arg(args, "claim", default=".")
    mutants = _arg(args, "mutants")
    env = report._r_assess(d, args, mutants=mutants)
    return 0 if env["ok"] else 1


# ---------------------------------------------------------------------------
# rebuild / crosscheck: reconstruction and the three-machine test
# ---------------------------------------------------------------------------

def _handle_rebuild(args) -> int:
    d = _arg(args, "claim")
    producer = _arg(args, "producer")
    into = _arg(args, "into")
    ws = _arg(args, "ws")
    reuse = bool(_arg(args, "reuse", default=False))
    guidance = _arg(args, "guidance", default=True)
    if ws:
        env = report._generic_contract(
            "rebuild", registry.rebuild_chain, args, d, producer, into,
            ws=ws, reuse=reuse)
    else:
        env = report._r_rebuild(d, args, producer, into, guidance=guidance)
    return 0 if env["ok"] else 1


def _dispatch_crosscheck(args) -> int:
    leg1 = _arg(args, "leg1")
    leg2 = _arg(args, "leg2")
    leg3 = _arg(args, "leg3")
    mutants = _arg(args, "mutants")
    deep = bool(_arg(args, "deep", default=False))
    env = report._r_crosscheck(leg1, leg2, leg3, args, mutants=mutants, deep=deep)
    return 0 if env["ok"] else 1


# ---------------------------------------------------------------------------
# record / sign: evidence and the signing ceremony
# ---------------------------------------------------------------------------

def _handle_record(args) -> int:
    d = _arg(args, "claim", default=".")
    key = _arg(args, "key")
    identity = _arg(args, "identity")
    check = getattr(args, "check", None)
    if key:
        if not identity:
            output._err("record", "refused: --key requires --as IDENTITY")
            return 2
        env = report._r_attest(d, args, key, identity)
    elif check is not None:
        env = report._r_attest_check(d, args, check or None)
    else:
        out = _arg(args, "out")
        env = report._r_record(d, args, out=out)
    return 0 if env["ok"] else 1


def _handle_sign(args) -> int:
    target = _arg(args, "target")
    key = _arg(args, "key")
    identity = _arg(args, "identity")
    ws = _arg(args, "ws")
    proof = bool(_arg(args, "proof", default=False))
    if proof:
        def _run(target):
            record_mod.sign(target, key)
            return {"ok": True, "signed": target}
        env = report._generic_contract("sign", _run, args, target)
    else:
        env = report._r_sign(target, args, key, identity, ws)
    return 0 if env["ok"] else 1


# ---------------------------------------------------------------------------
# hook / help / completion: plumbing
# ---------------------------------------------------------------------------

def _handle_hook(args) -> int:
    hooks.main()
    return 0


def _handle_help(args) -> int:
    if _arg(args, "all", default=False):
        parser._help_all()
        return 0
    topic = _arg(args, "topic")
    if topic:
        parser._help_topic(topic)
        return 0
    p, _subparsers = parser._parser()
    p.print_help()
    return 0


def _handle_completion(args) -> int:
    shell = _arg(args, "shell", default="bash")
    parser._completion(shell)
    return 0


# ---------------------------------------------------------------------------
# main: parse argv, dispatch, exit with the verb's own code
# ---------------------------------------------------------------------------

_DISPATCH = {
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


def main(argv: list = None) -> int:
    p, _subparsers = parser._parser()
    args = p.parse_args(argv)

    if getattr(args, "version", False):
        print(handlers._version_line())
        return 0

    verb = getattr(args, "verb", None)
    if not verb:
        p.print_help()
        return 0

    canonical = parser.ALIASES.get(verb, verb)
    fn = _DISPATCH.get(canonical)
    if fn is None:
        output._err(verb, f"unknown command: {verb!r}")
        return 2

    try:
        return fn(args)
    except kernel.ClaimError as e:
        output._err(canonical, str(e))
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
