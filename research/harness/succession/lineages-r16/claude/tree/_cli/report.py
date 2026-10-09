"""Action-verb renderers: one `_r_<verb>` per CLI verb that runs a lower-layer
operation and ends it through `output._finish`'s shared envelope.

Every verb's body is a thin call into the layer that actually does the
work (`kernel`, `registry`, `attest`, `record`, `transfer`, `pack`,
`authoring`, `hooks`, `assess`) -- this module's only job is argument
plumbing (reading `args`' attributes, defaulting the claim directory to
the current one) and the human/`--json` presentation `output.py` defines.
`_generic_contract` is that plumbing, factored once: a verb's body raises
`kernel.ClaimError` for a clean refusal, or returns a result dict whose
`ok`/`satisfied` flag and `status`/`verdict` word drive the envelope.

`_row` and `_when` are the two presentation primitives small enough to be
shared outright: a plain two-or-more-cell display line, and a ledger
timestamp rendered for a reader rather than a parser.
"""
import os
import tempfile

from reticuli import assess, attest, authoring, hooks, kernel, pack, record, registry, render, transfer
from reticuli._cli import output


def _dir(args) -> str:
    """The claim directory a verb operates on, defaulting to the cwd."""
    return getattr(args, "dir", None) or "."


def _row(*cells) -> str:
    """One display row: cells joined by two spaces -- the single-row case
    `render.table` (which needs the whole table at once) does not cover."""
    return "  ".join(str(c) for c in cells)


def _when(stamp) -> str:
    """A ledger `when` timestamp (`YYYY-MM-DDTHH:MM:SSZ`) for a reader:
    the `T`/`Z` punctuation swapped for a space, since every reader of
    this field already knows it is UTC."""
    if not isinstance(stamp, str):
        return str(stamp)
    return stamp.replace("T", " ").rstrip("Z")


def _t_init(data: dict) -> str:
    """`init`'s result as one terse line: name and short root."""
    return _row(data.get("name", "?"), render.short(data.get("root") or "") or "-" * 8)


def _generic_contract(cmd: str, args, fn, *, line=None) -> int:
    """Run one verb's body (`fn`, taking no arguments) through the CLI's
    shared contract: a `kernel.ClaimError` becomes a clean refusal rather
    than a traceback, and every outcome -- pass or refusal -- ends through
    `output._finish`'s envelope. `line`, if given, renders one extra
    human-mode line from the result before that envelope prints."""
    try:
        data = fn()
    except kernel.ClaimError as e:
        output._err(cmd, str(e))
        output._finish(cmd, {"error": str(e)}, False, "error", args, None)
        return 1

    ok = data.get("ok")
    if ok is None:
        ok = data.get("satisfied", True)
    ok = bool(ok)
    status = data.get("status") or data.get("verdict") or ("ok" if ok else "failed")

    if line is not None and not getattr(args, "json", False):
        output._line(args, line(data))
    output._finish(cmd, data, ok, str(status), args, data.get("root"))
    return 0 if ok else 1


# -------------------------------------------------------------------- verify
def _r_verify(args) -> int:
    d = _dir(args)
    return _generic_contract("verify", args, lambda: kernel.verify(d))


# --------------------------------------------------------------------- audit
def _r_audit(args) -> int:
    d = _dir(args)
    deep = bool(getattr(args, "deep", False))
    fn = (lambda: registry.audit_deep(d)) if deep else (lambda: kernel.audit(d))
    return _generic_contract("audit", args, fn)


# -------------------------------------------------------------------- assess
def _r_assess(args) -> int:
    d = _dir(args)
    mutants = getattr(args, "mutants", None)
    return _generic_contract("assess", args, lambda: assess.assess(d, mutants=mutants))


# ------------------------------------------------------------------- rebuild
def _r_rebuild(args) -> int:
    d = _dir(args)
    into = getattr(args, "into", None) or tempfile.mkdtemp(prefix="reticuli-rebuild-")
    producer = getattr(args, "producer", None) or os.environ.get("RETICULI_PRODUCER")
    ws = getattr(args, "ws", None)
    reuse = bool(getattr(args, "reuse", False))

    def fn():
        result = dict(registry.rebuild_chain(d, producer, into, ws=ws, reuse=reuse))
        result["into"] = into
        return result

    return _generic_contract("rebuild", args, fn, line=lambda data: f"rebuilt into {data['into']}")


# ---------------------------------------------------------------------- seal
def _r_seal(args) -> int:
    d = _dir(args)
    return _generic_contract("seal", args, lambda: registry.seal_with(d))


# ----------------------------------------------------------------- crosscheck
def _r_crosscheck(args) -> int:
    d = _dir(args)
    m2 = getattr(args, "m2", None)
    m3 = getattr(args, "m3", None)
    mutants = getattr(args, "mutants", None)

    def fn():
        if not m2 or not m3:
            raise kernel.ClaimError("crosscheck requires a second and third machine (--m2, --m3)")
        return registry.crosscheck_deep(d, m2, m3, mutants=mutants)

    return _generic_contract("crosscheck", args, fn)


# --------------------------------------------------------------------- sign
def _r_sign(args) -> int:
    d = _dir(args)
    key = getattr(args, "key", None)
    identity = getattr(args, "identity", None)
    ws = getattr(args, "ws", None)

    def fn():
        if not key or not identity:
            raise kernel.ClaimError("sign requires --key and --identity")
        return attest.sign(d, key, identity, ws=ws)

    return _generic_contract("sign", args, fn)


def _r_sign_check(args) -> int:
    d = _dir(args)
    ws = getattr(args, "ws", None)
    signers = getattr(args, "signers", None) or os.environ.get("RETICULI_SIGNERS")
    return _generic_contract("sign-check", args, lambda: attest.sign_check(d, ws=ws, signers=signers))


def _r_review(args) -> int:
    d = _dir(args)
    ws = getattr(args, "ws", None)
    return _generic_contract("review", args, lambda: attest.review_packet(d, ws=ws))


# -------------------------------------------------------------------- attest
def _r_attest(args) -> int:
    d = _dir(args)
    key = getattr(args, "key", None)
    identity = getattr(args, "identity", None)

    def fn():
        if not key or not identity:
            raise kernel.ClaimError("attest requires --key and --identity")
        return attest.attest(d, key, identity)

    return _generic_contract("attest", args, fn)


def _r_attest_check(args) -> int:
    d = _dir(args)
    signers = getattr(args, "signers", None) or os.environ.get("RETICULI_SIGNERS")
    return _generic_contract("attest-check", args, lambda: attest.check(d, signers))


# -------------------------------------------------------------------- record
def _r_record(args) -> int:
    d = _dir(args)
    path = getattr(args, "out", None) or os.path.join(d, "record.json")
    key = getattr(args, "key", None)

    def fn():
        doc = record.emit(d)
        record.write(doc, path)
        if key:
            record.sign(path, key)
        return {"ok": True, "path": path, "name": doc["name"], "root": doc["root"],
                "signed": bool(key)}

    return _generic_contract("record", args, fn)


# ------------------------------------------------------------------- export
def _r_export(args) -> int:
    d = _dir(args)
    tar_path = getattr(args, "out", None)
    blind = bool(getattr(args, "blind", False))

    def fn():
        if not tar_path:
            raise kernel.ClaimError("export requires --out")
        transfer.export(d, tar_path, blind=blind)
        return {"ok": True, "tar": tar_path, "blind": blind}

    return _generic_contract("export", args, fn)


def _r_import(args) -> int:
    tar_path = getattr(args, "tar", None)
    dest = getattr(args, "dest", None) or _dir(args)

    def fn():
        if not tar_path:
            raise kernel.ClaimError("import requires a tar path")
        return transfer.import_(tar_path, dest)

    return _generic_contract("import", args, fn)


def _r_pull(args) -> int:
    src = getattr(args, "src", None)
    dest = getattr(args, "dest", None)

    def fn():
        if not src or not dest:
            raise kernel.ClaimError("pull requires a source and a destination")
        return registry.pull(src, dest)

    return _generic_contract("pull", args, fn)


# ---------------------------------------------------------------------- pack
def _r_pack(args) -> int:
    root_dir = _dir(args)
    name = getattr(args, "name", None)
    generated = getattr(args, "generated", None) or []
    inputs = getattr(args, "inputs", None) or []
    gate = getattr(args, "gate", None)
    gate_output = getattr(args, "gate_output", None) or "gate"
    component = getattr(args, "component", None)
    claim_format = getattr(args, "format", None)
    envelope = getattr(args, "envelope", None)
    mutation_floor = getattr(args, "mutation_floor", None)
    requires = getattr(args, "requires", None)
    by = getattr(args, "by", None)
    inputs_manifest = getattr(args, "inputs_manifest", None)
    environment = getattr(args, "environment", None)

    def fn():
        if not name or not gate:
            raise kernel.ClaimError("pack requires --name and --gate")
        return pack.pack(root_dir, name, generated, inputs, gate, gate_output,
                          component=component, claim_format=claim_format,
                          envelope=envelope, mutation_floor=mutation_floor,
                          requires=requires, by=by, inputs_manifest=inputs_manifest,
                          environment=environment)

    return _generic_contract("pack", args, fn)


# ---------------------------------------------------------------------- init
def _r_init(args) -> int:
    ws = _dir(args)
    into = getattr(args, "into", None) or ws
    outputs = getattr(args, "outputs", None) or []
    name = getattr(args, "name", None)
    pin = getattr(args, "pin", None)
    generated = getattr(args, "generated", None)

    def fn():
        return authoring.build_claim(ws, outputs, into, name=name, claim=pin, generated=generated)

    return _generic_contract("init", args, fn, line=_t_init)


# --------------------------------------------------------------------- hooks
def _r_hooks(args) -> int:
    project_dir = _dir(args)
    return _generic_contract("hooks", args, lambda: hooks.install(project_dir))
