"""`_cli/verbs.py`: the verb handlers and composite dispatches
(`spec/layers.md`'s surface layer) -- `checks/verbs_check.py`, this module's
definition.

Each porcelain verb has one `_handle_*` (a plain call into a layer below) or
`_dispatch_*` (a verb whose own usage rules must be checked before anything
is built, e.g. `pack`'s `--accept` needing `-o`). Every one of them ends by
either returning a plain refusal through `_cli/output.py`'s `_err`/`_finish`
or by returning the child's own exit code (`run`) unchanged, so a caller can
use either as a predicate.

Built from `reticuli.kernel` and every layer below the surface
(`reticuli._util`, `reticuli.registry`, `reticuli.transfer`, `reticuli.attest`,
`reticuli.record`, `reticuli.assess`, `reticuli.pack`, `reticuli.hooks`) plus
this layer's own `handlers.py`/`output.py`/`parser.py`/`statusview.py` --
never a kernel private (`spec/layers.md`). Stdlib only.
"""
import json
import os
import sys

from reticuli import assess, attest, hooks, kernel, pack, record, registry, transfer
from reticuli._cli import handlers, output, parser, statusview

# -- init, run: session setup and a traced run. ----------------------------


def _handle_init(args) -> int:
    path = getattr(args, "path", ".")
    no_agent = getattr(args, "no_agent", False)
    data = handlers.init(path, no_agent=no_agent)
    output._finish("init", data, True, data.get("status"), args)
    return 0


def _handle_run(args) -> int:
    """Run the verb's child command and return its exit code unchanged --
    the predicate contract (`checks/verbs_check.py`). Reads `args.command`
    (falling back to `args.cmd`, the parser's own dest) and `args.workspace`.
    """
    cmd_arg = getattr(args, "command", None)
    if cmd_arg is None:
        cmd_arg = getattr(args, "cmd", [])
    cmd = " ".join(cmd_arg) if isinstance(cmd_arg, (list, tuple)) else str(cmd_arg)
    ws = getattr(args, "workspace", ".")

    rc = handlers.run(cmd, ws)
    output._finish("run", {"command": cmd, "exit": rc}, rc == 0,
                    "ok" if rc == 0 else "failed", args)
    return rc


# -- help, completion, hook: plumbing. --------------------------------------


def _handle_help(args) -> int:
    if getattr(args, "all", False):
        parser._help_all()
        return 0
    topic = getattr(args, "topic", None)
    if topic:
        parser._help_topic(topic)
    else:
        parser._help_all()
    return 0


def _handle_completion(args) -> int:
    parser._completion(getattr(args, "shell", "bash"))
    return 0


def _handle_hook(args) -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    hooks.event(payload)
    return 0


# -- verify, assess: verification that never earns a new verdict. ----------


def _handle_verify(args) -> int:
    path = getattr(args, "path", ".")
    try:
        result = kernel.verify(path)
    except kernel.ClaimError as e:
        output._err("verify", str(e))
        return 1
    ok = result.get("ok")
    output._finish("verify", result, ok, "holds" if ok else "drifted", args,
                    root=result.get("root"))
    return 0 if ok else 1


def _handle_assess(args) -> int:
    path = getattr(args, "path", ".")
    mutants = getattr(args, "mutants", None)
    try:
        data = assess.assess(path, mutants=mutants)
    except kernel.ClaimError as e:
        output._err("assess", str(e))
        return 1
    output._finish("assess", data, True, "measured", args)
    return 0


# -- rebuild, pull: reconstruction and composition. -------------------------


def _handle_rebuild(args) -> int:
    claim = getattr(args, "claim", None)
    producer = getattr(args, "producer", None)
    if not claim or not producer:
        output._err("rebuild", "a claim and a producer are required")
        return 2
    into = getattr(args, "into", ".")
    try:
        data = registry.rebuild_chain(claim, producer, into)
    except kernel.ClaimError as e:
        output._err("rebuild", str(e))
        return 1
    output._finish("rebuild", data, True, "regrown", args, root=data.get("root"))
    return 0


def _handle_pull(args) -> int:
    claim = getattr(args, "claim", None)
    if not claim:
        output._err("pull", "a claim is required")
        return 2
    into = getattr(args, "into", ".")
    try:
        data = registry.pull(claim, into)
    except kernel.ClaimError as e:
        output._err("pull", str(e))
        return 1
    output._finish("pull", data, True, "pulled", args, root=data.get("root"))
    return 0


# -- sign: a human authorizes a claim or proof. -----------------------------


def _handle_sign(args) -> int:
    path = getattr(args, "path", ".")
    key = getattr(args, "key", None)
    if not key:
        output._err("sign", "--key is required")
        return 2
    identity_name = getattr(args, "identity", None) or os.environ.get("USER", "signer")
    try:
        data = attest.sign(path, key, identity_name)
    except kernel.ClaimError as e:
        output._err("sign", str(e))
        return 1
    output._finish("sign", data, True, "recorded", args)
    return 0


# -- export, import: portable archives. -------------------------------------


def _handle_export(args) -> int:
    path = getattr(args, "path", ".")
    out = getattr(args, "out", None)
    if not out:
        output._err("export", "--out is required")
        return 2
    blind = getattr(args, "blind", False)
    try:
        data = transfer.export(path, out, blind=blind)
    except kernel.ClaimError as e:
        output._err("export", str(e))
        return 1
    output._finish("export", data, True, "exported", args)
    return 0


def _handle_import(args) -> int:
    archive = getattr(args, "archive", None)
    if not archive:
        output._err("import", "an archive is required")
        return 2
    into = getattr(args, "into", ".")
    try:
        data = transfer.import_(archive, into)
    except kernel.ClaimError as e:
        output._err("import", str(e))
        return 1
    ok = data.get("ok")
    output._finish("import", data, ok, "ok" if ok else "failed", args,
                    root=data.get("root"))
    return 0 if ok else 1


# -- record: write (or check) a signed statement of one machine's results. -


def _handle_record(args) -> int:
    path = getattr(args, "path", ".")

    if getattr(args, "check", False):
        try:
            doc = kernel.record_read(path)
        except kernel.ClaimError as e:
            output._err("record", str(e))
            return 1
        anchor = os.environ.get("RETICULI_SIGNERS")
        signer_name = kernel.record_signer(path, anchor) if anchor else None
        ok = signer_name is not None if anchor else True
        data = {"name": doc.get("name"), "root": doc.get("root"), "signer": signer_name}
        output._finish("record", data, ok, "checked", args, root=doc.get("root"))
        return 0 if ok else 1

    try:
        doc = record.emit(path)
    except kernel.ClaimError as e:
        output._err("record", str(e))
        return 1

    out_path = os.path.join(path, "record.json")
    record.write(doc, out_path)
    key = getattr(args, "key", None)
    if key:
        record.sign(out_path, key)
    output._finish("record", doc, True, "recorded", args, root=doc.get("root"))
    return 0


# -- pack: the one verb whose own usage must be refused before anything is
# built (`checks/verbs_check.py` pins this one in words). -------------------


def _dispatch_pack(args) -> int:
    path = getattr(args, "path", ".")
    accept = getattr(args, "accept", None)
    output_name = getattr(args, "output", None)

    if accept and not output_name:
        output._err("pack", "--accept requires -o/--output to name the "
                     "gate's verdict file")
        return 2

    gate = getattr(args, "gate", None)
    if not gate:
        output._err("pack", "--gate is required to name the acceptance command")
        return 2
    if not output_name:
        output._err("pack", "-o/--output is required to name the gate's "
                     "verdict file")
        return 2

    name = getattr(args, "name", None) or os.path.basename(os.path.abspath(path))
    generated = getattr(args, "generated", None) or []
    inputs = getattr(args, "pytest", None) or []

    try:
        data = pack.pack(path, name, generated, inputs, gate, output_name)
    except kernel.ClaimError as e:
        output._err("pack", str(e))
        return 1

    into = getattr(args, "into", None)
    if into:
        try:
            registry.pull(path, into)
        except kernel.ClaimError as e:
            output._err("pack", str(e))
            return 1

    output._finish("pack", data, True, "sealed", args, root=data.get("root"))
    return 0


# -- audit: the only verb that re-earns a verdict, deep by default. --------


def _dispatch_audit(args) -> int:
    path = getattr(args, "path", ".")
    shallow = getattr(args, "shallow", False)

    try:
        base = kernel.audit(path, shallow=True)
    except kernel.ClaimError as e:
        output._err("audit", str(e))
        return 1

    result = dict(base)
    if not shallow:
        try:
            deep = registry.audit_deep(path)
        except kernel.ClaimError as e:
            output._err("audit", str(e))
            return 1
        result["layers"] = deep.get("layers", [])
        result["ok"] = bool(base.get("ok")) and bool(deep.get("ok"))

    ok = result.get("ok")
    output._finish("audit", result, ok, result.get("verdict", "?"), args,
                    root=result.get("root"))
    return 0 if ok else 1


# -- status: carried state, nothing re-earned. ------------------------------


def _dispatch_status(args) -> int:
    path = getattr(args, "path", ".")

    if getattr(args, "claims", False):
        output._line(statusview._r_claims(path), args)
        return 0
    if getattr(args, "tree", False):
        output._line(statusview._r_tree(path), args)
        return 0

    verbose = getattr(args, "verbose", False)
    try:
        line = statusview._v_status_claim(path) if verbose else statusview._t_status_claim(path)
    except kernel.ClaimError as e:
        output._err("status", str(e))
        return 1
    output._line(line, args)
    return 0


# -- crosscheck: the three-machine test, deep by default. ------------------


def _dispatch_crosscheck(args) -> int:
    manifests = getattr(args, "manifests", None) or []
    if len(manifests) != 3:
        output._err("crosscheck", "requires exactly three machines")
        return 2
    m1, m2, m3 = manifests

    try:
        result = registry.crosscheck_deep(m1, m2, m3)
    except kernel.ClaimError as e:
        output._err("crosscheck", str(e))
        return 1

    ok = result.get("satisfied")
    output._finish("crosscheck", result, ok, result.get("verdict", "?"), args,
                    root=(result.get("roots") or {}).get("M1"))
    return 0 if ok else 1
