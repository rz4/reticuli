"""Verbs: the action handlers `main()` routes argv to (spec/layers.md,
"surface").

A `_handle_*` function takes the parsed arguments for one porcelain verb
and returns a plain result -- a dict for `report.py` to render, or, for
`run`, the child's own exit code, unwrapped. A `_dispatch_*` function is
the composite case: a verb whose outcome depends on more than one
lower-layer call (folded flags, a multi-leg test, a usage check that must
run before anything is built) -- it renders its own result and returns
the process exit code directly, the same contract `report.py`'s `_r_*`
renderers return.

`pack`'s usage check runs before a single byte is touched: `--accept`
(acceptance-test paths that double as the gate's deciders) names nothing
to pin without `-o/--output` to say where the gate's own verdict lands,
so that combination refuses in words, at exit code 2, before any file is
written. `run` is the other cleanly-isolable contract: the child's exit
code reaches the caller completely unwrapped.

`main()` builds the grammar (`parser._parser`), dispatches on the parsed
verb (aliases resolved through `parser.ALIASES`), and turns any
`handlers.HandlerError` or `kernel.ClaimError` into the one-voice refusal
line (`output._err`) and a non-zero exit code -- nothing above this
module ever sees a raw traceback for an ordinary refusal.
"""
import glob
import json
import os
import shutil
import sys
import tempfile

from . import handlers
from . import output
from . import parser
from . import report
from . import statusview
from .. import attest
from .. import assess as assess_mod
from .. import kernel
from .. import pack as pack_mod
from .. import record as record_mod
from .. import registry
from .. import render
from .. import transfer
from .. import hooks


# ===========================================================================
# Handlers: one porcelain verb in, one plain result out.
# ===========================================================================


def _handle_help(args):
    """`ret help [topic] [-a]`: detailed help for one verb, or (with
    `--all`) the full listing including accepted older spellings.
    """
    if getattr(args, "all", False):
        parser._help_all()
        return 0
    topic = getattr(args, "topic", None)
    if topic:
        parser._help_topic(topic)
        return 0
    p, _choices = parser._parser()
    p.print_help()
    return 0


def _handle_completion(args):
    """`ret completion [shell]`: print a shell completion script."""
    parser._completion(getattr(args, "shell", "bash"))
    return 0


def _handle_hook(args):
    """`ret hook <name> [workspace]`: the coding-agent hook entry point.
    Reads one JSON payload from stdin and turns it into a trace event
    (`hooks.event`) -- a no-op, never a refusal, for a payload that
    traces to nothing.
    """
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        payload = {}
    hooks.event(payload)
    return 0


def _handle_init(args):
    """`ret init [workspace] [--no-agent]`."""
    return handlers.init(getattr(args, "workspace", ".") or ".",
                          no_agent=getattr(args, "no_agent", False))


def _handle_run(args):
    """`ret run <cmd> [workspace]`: the child's exit code, unwrapped.
    `args.command` may be the shell command as a single string or as a
    list of tokens (joined with spaces before the shell sees them).
    """
    command = getattr(args, "command", None)
    if command is None:
        command = getattr(args, "cmd", "")
    if isinstance(command, (list, tuple)):
        command = " ".join(command)
    return handlers.run(command, getattr(args, "workspace", ".") or ".")


def _handle_verify(args):
    """`ret verify [claim]`: identity only, no gate executed."""
    return kernel.verify(getattr(args, "claim", ".") or ".")


def _handle_assess(args):
    """`ret assess [claim]`: measure specification strength."""
    return assess_mod.assess(getattr(args, "claim", ".") or ".")


def _handle_rebuild(args):
    """`ret rebuild [claim] [--out PATH]`: regrow the generated outputs
    into a fresh directory (a scratch one, absent `--out`) via the
    named or literal `RETICULI_PRODUCER`.
    """
    d = getattr(args, "claim", ".") or "."
    into = getattr(args, "out", None) or tempfile.mkdtemp(prefix="rebuild-")
    producer = os.environ.get("RETICULI_PRODUCER", ":")
    if producer in handlers._PRODUCERS:
        handlers._ensure(producer)
        producer = handlers._expand_producer(producer)
    return kernel.rebuild(d, producer, into)


def _handle_pull(args):
    """`ret pull <source> [workspace]`: materialize `source`'s declared
    bytes into `workspace`.
    """
    return registry.pull(args.source, getattr(args, "workspace", ".") or ".")


def _handle_sign(args):
    """`ret sign [claim] [--key KEY]`: a human signs the chain root over
    a freshly assembled review packet.
    """
    key = getattr(args, "key", None)
    if not key:
        raise handlers.HandlerError("sign needs --key")
    principal = os.environ.get("USER") or os.environ.get("LOGNAME") or "unknown"
    return attest.sign(getattr(args, "claim", ".") or ".", key, principal)


def _handle_export(args):
    """`ret export [claim] [--out PATH]`: a portable claim archive,
    named after the claim directory when `--out` is absent.
    """
    d = getattr(args, "claim", ".") or "."
    tar_path = getattr(args, "out", None)
    if not tar_path:
        base = os.path.abspath(d.rstrip(os.sep) or ".")
        tar_path = base + ".tar"
    return transfer.export(d, tar_path)


def _handle_record(args):
    """`ret record [claim] [--key KEY] [--as NAME] [--check]`: write an
    execution record, or (with `--check`) read back and return an
    existing one instead of writing one.
    """
    d = getattr(args, "claim", ".") or "."
    name = getattr(args, "as_", None) or "record.json"
    path = name if os.path.isabs(name) else os.path.join(d, name)
    if getattr(args, "check", False):
        return record_mod.read(path)
    doc = record_mod.emit(d)
    record_mod.write(doc, path)
    key = getattr(args, "key", None)
    if key:
        record_mod.sign(path, key)
    return doc


def _handle_import(args):
    """`ret import <archive> [workspace]`: restore a claim archive and
    verify identity immediately from the received bytes.
    """
    return transfer.import_(args.archive, getattr(args, "workspace", ".") or ".")


# ===========================================================================
# Dispatches: composite verbs. Each renders its own result and returns
# the process exit code.
# ===========================================================================


def _expand_globs(d, patterns):
    out = []
    for pattern in patterns:
        for full in sorted(glob.glob(os.path.join(d, pattern))):
            if os.path.isfile(full):
                rel = os.path.relpath(full, d).replace(os.sep, "/")
                if rel not in out:
                    out.append(rel)
    return sorted(out)


def _dispatch_pack(args):
    """`ret pack [path] [--name] [--generated ...] [--gate | --pytest]
    [-o/--output] [--accept ...] [--root] [--into] [--force]`.

    Without `--accept`, writes a draft recipe (the implementation globs
    named by `--generated`, no gate yet) and stops -- the project is not
    sealed. With `--accept` (one or more acceptance-test paths, pinned
    as inputs and run as the gate's deciders), the claim is packed and
    sealed immediately: refuses as a usage error, in words, before
    building anything, when `--accept` is given without `-o/--output` to
    name where the gate's own verdict lands.
    """
    d = getattr(args, "path", None) or getattr(args, "workspace", ".") or "."
    accept = getattr(args, "accept", None) or []
    output_name = getattr(args, "output", None)

    if accept and not output_name:
        output._err("pack", "--accept needs -o/--output to name the gate's verdict file")
        return 2

    name = getattr(args, "name", None) or os.path.basename(os.path.abspath(d).rstrip(os.sep)) or "claim"
    generated = getattr(args, "generated", None) or []

    if not accept:
        gen_paths = _expand_globs(d, generated) if generated else []
        draft = {
            "claim": {"name": name, "inputs": []},
            "step": [{"kind": "produce", "output": p, "class": "generated"} for p in gen_paths],
        }
        with open(os.path.join(d, kernel.RECIPE), "w", encoding="utf-8") as f:
            f.write(render.dump_recipe(draft))
        return report._r_pack({"ok": True, "status": "drafted", "name": name}, args)

    recipe_path = os.path.join(d, kernel.RECIPE)
    force = getattr(args, "force", False)
    if os.path.isfile(recipe_path) and not force:
        output._err("pack", f"{d!r} already has a recipe; use --force to overwrite")
        return 2

    gate = getattr(args, "gate", None)
    if gate:
        gate_cmd = gate
    elif getattr(args, "pytest", False):
        gate_cmd = f"python3 -m pytest && printf ok > {output_name}"
    else:
        checks = " && ".join(f"python3 {a}" for a in accept)
        gate_cmd = f"{checks} && printf ok > {output_name}"

    gen_patterns = list(generated) if generated else ["*"]
    inputs = list(accept)

    try:
        result = pack_mod.pack(d, name, gen_patterns, inputs, gate_cmd, output_name)
    except kernel.ClaimError as exc:
        output._err("pack", str(exc))
        return 1

    expected_root = getattr(args, "root", None)
    if expected_root and result.get("root") != expected_root:
        output._err("pack", f"packed root {result.get('root')} does not match expected {expected_root}")
        return 1

    into = getattr(args, "into", None)
    if into:
        shutil.copytree(d, into, dirs_exist_ok=True)

    return report._r_pack(result, args)


def _dispatch_audit(args):
    """`ret audit [claim] [--shallow]`: re-run every gate cold; deep
    (every declared component re-earns its own gate too) by default,
    `--shallow` opts out.
    """
    d = getattr(args, "claim", ".") or "."
    result = kernel.audit(d)
    if not getattr(args, "shallow", False):
        deep = registry.audit_deep(d)
        result = dict(result)
        result["layers"] = deep.get("layers", [])
        result["ok"] = bool(result.get("ok")) and bool(deep.get("ok", True))
    return report._r_audit(result, args)


def _dispatch_status(args):
    """`ret status [workspace] [--tree] [--claims]`: the retired `tree`
    and `claims` verbs folded in as flags; otherwise a sealed claim's own
    status, a draft session's sealability, or the workspace's structure
    -- whichever `workspace` actually holds.
    """
    ws = getattr(args, "workspace", ".") or "."

    if getattr(args, "tree", False):
        return statusview._r_tree(ws, args)
    if getattr(args, "claims", False):
        return statusview._r_claims(ws, args)

    recipe_present = (os.path.isfile(os.path.join(ws, kernel.RECIPE))
                       or os.path.isfile(os.path.join(ws, "claim.toml")))
    if recipe_present:
        if getattr(args, "verbose", False):
            return statusview._v_status_claim(ws, args)
        return statusview._t_status_claim(ws, args)

    trace_path = os.path.join(ws, kernel.STORE, "draft.jsonl")
    if os.path.isfile(trace_path):
        return statusview._r_status_draft(ws, args)

    return statusview._r_structure(ws, args)


def _dispatch_crosscheck(args):
    """`ret crosscheck [claim]`: the three-machine test, with M2
    (transfer) and M3 (independent rebuild) derived on the fly from M1
    (`claim`) -- export/import for M2, the named or literal
    `RETICULI_PRODUCER` for M3.
    """
    m1 = getattr(args, "claim", ".") or "."
    scratch = tempfile.mkdtemp(prefix="crosscheck-")
    try:
        m2 = os.path.join(scratch, "m2")
        m3 = os.path.join(scratch, "m3")
        tar_path = os.path.join(scratch, "export.tar")

        transfer.export(m1, tar_path)
        transfer.import_(tar_path, m2)

        producer = os.environ.get("RETICULI_PRODUCER", ":")
        if producer in handlers._PRODUCERS:
            handlers._ensure(producer)
            producer = handlers._expand_producer(producer)
        kernel.rebuild(m1, producer, m3)

        result = kernel.crosscheck(m1, m2, m3)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return report._r_crosscheck(result, args)


# ===========================================================================
# main: build the grammar, dispatch, translate refusals.
# ===========================================================================

_SIMPLE = {
    "init": (_handle_init, report._r_init),
    "pull": (_handle_pull, report._r_pull),
    "export": (_handle_export, report._r_export),
    "import": (_handle_import, report._r_import),
    "verify": (_handle_verify, report._r_verify),
    "assess": (_handle_assess, report._r_assess),
    "rebuild": (_handle_rebuild, report._r_rebuild),
    "record": (_handle_record, report._r_record),
    "sign": (_handle_sign, report._r_sign),
}

_DISPATCH = {
    "pack": _dispatch_pack,
    "audit": _dispatch_audit,
    "status": _dispatch_status,
    "crosscheck": _dispatch_crosscheck,
}


def main(argv=None):
    """Build the argv grammar, dispatch the parsed verb to its handler
    or composite dispatch, and translate any refusal
    (`handlers.HandlerError`, `kernel.ClaimError`) into the one-voice
    error line and a non-zero exit code.
    """
    p, _choices = parser._parser()
    args = p.parse_args(argv)

    if getattr(args, "version", False):
        print(handlers._version_line())
        return 0

    verb = args.verb
    if verb is None:
        p.print_help()
        return 1

    canonical = parser.ALIASES.get(verb, verb)

    try:
        if canonical == "help":
            return _handle_help(args)
        if canonical == "completion":
            return _handle_completion(args)
        if canonical == "hook":
            return _handle_hook(args)
        if canonical == "run":
            return _handle_run(args)

        if canonical in _DISPATCH:
            return _DISPATCH[canonical](args)

        if canonical in _SIMPLE:
            handler, renderer = _SIMPLE[canonical]
            return renderer(handler(args), args)
    except handlers.HandlerError as exc:
        output._err(canonical, str(exc))
        return 2
    except kernel.ClaimError as exc:
        output._err(canonical, str(exc))
        return 1

    p.error(f"unknown command: {verb}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
