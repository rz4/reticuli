"""reticuli._cli.report -- rendering the action verbs (spec/layers.md: surface).

Every `_r_<verb>` function is the CLI's rendering of one verb: run the
layer call the verb names, fold whatever it returns (or whatever
`kernel.ClaimError` it raises) into the one envelope `output._finish`
prints, and return that envelope so a caller holding it never has to
re-derive it. `_generic_contract` is the one place that fold happens,
since every verb shares the same refusal shape -- a `ClaimError` becomes
the one-voice error line, never a traceback.

`_row` and `_when` are the two render primitives the status family
(`statusview.py`) and this module both lean on: one aligned line of
columns, and one human reading of a timestamp.
"""
import os

from reticuli import kernel, registry, transfer, attest, record, pack, hooks, assess, render
from reticuli._cli import output


# -- the one fold every verb shares ------------------------------------------

def _generic_contract(command: str, args, fn) -> dict:
    """Run `fn()` -- a zero-argument call into the layer below -- and fold
    its outcome into the envelope every verb ends in. A `kernel.ClaimError`
    becomes the one-voice refusal line, never a traceback; any other
    result is read for its own `ok`/`status` (or `verdict`) fields, falling
    back to a plain pass when the result names neither."""
    try:
        result = fn()
    except kernel.ClaimError as e:
        output._err(command, str(e))
        return output._finish(command, {"error": str(e)}, False, str(e), args)

    if isinstance(result, dict):
        ok = bool(result.get("ok", True))
        status = result.get("status") or result.get("verdict") or ("ok" if ok else "failed")
    else:
        ok, status = True, "ok"
    return output._finish(command, result, ok, status, args)


# -- shared render primitives ------------------------------------------------

def _row(*columns) -> str:
    """One line of aligned columns -- `render.table`'s own alignment,
    applied to a single row."""
    return render.table([list(columns)])


def _when(ts) -> str:
    """A human reading of a timestamp: `render.ago` for a unix time, the
    value itself (stringified) for anything else -- a record's `when` is
    already a UTC string, not a float."""
    if isinstance(ts, (int, float)):
        return render.ago(ts)
    return "" if ts is None else str(ts)


# -- init / hooks: before anything is a claim --------------------------------

def _r_init(args) -> dict:
    """`init`: scaffold a fresh draft workspace -- just `.reticuli/`, so a
    session has somewhere to leave its trace before anything is sealed."""
    def run():
        ws = os.path.abspath(args.workspace)
        os.makedirs(os.path.join(ws, kernel.STORE), exist_ok=True)
        return {"ok": True, "workspace": ws}
    return _generic_contract("init", args, run)


def _t_init(result: dict) -> str:
    """One terse line for a freshly initialized workspace."""
    return f"initialized {result.get('workspace', '')}"


def _r_hooks(args) -> dict:
    """`hooks`: wire the coding-agent handshake into a project's Claude
    Code settings (`hooks.install`)."""
    return _generic_contract("hooks", args, lambda: hooks.install(args.workspace))


# -- the kernel's own verbs ---------------------------------------------

def _r_verify(args) -> dict:
    """`verify`: identity + gates re-run on present bytes (`kernel.verify`)."""
    return _generic_contract("verify", args, lambda: kernel.verify(args.claim))


def _r_audit(args) -> dict:
    """`audit`: deep re-earning, earned vs. carried (`kernel.audit`)."""
    return _generic_contract("audit", args, lambda: kernel.audit(args.claim))


def _r_assess(args) -> dict:
    """`assess`: how much the gates would have caught, measured by
    mutation testing (`assess.assess`)."""
    mutants = getattr(args, "mutants", 50)
    return _generic_contract("assess", args, lambda: assess.assess(args.claim, mutants=mutants))


# -- sealing, rebuilding, crosschecking ---------------------------------

def _r_seal(args) -> dict:
    """`seal`: compute the root, write the manifest, record any declared
    component links (`registry.seal_with`)."""
    components = getattr(args, "components", None)
    return _generic_contract("seal", args,
                              lambda: registry.seal_with(args.claim, components=components))


def _r_rebuild(args) -> dict:
    """`rebuild`: regrow a claim's generated outputs with a producer, its
    declared components rebuilt first (`registry.rebuild_chain`)."""
    def run():
        return registry.rebuild_chain(
            args.claim, args.producer, args.into,
            ws=getattr(args, "workspace", None),
            reuse=getattr(args, "reuse", False),
        )
    return _generic_contract("rebuild", args, run)


def _r_crosscheck(args) -> dict:
    """`crosscheck`: the three-machine test, deep over every ancestor
    (`registry.crosscheck_deep`)."""
    return _generic_contract("crosscheck", args,
                              lambda: registry.crosscheck_deep(args.m1, args.m2, args.m3))


# -- records, attestation, authorization ---------------------------------

def _r_record(args) -> dict:
    """`record`: emit this machine's signed statement of a claim's
    current results (`record.emit`), writing and signing it when a
    destination and key are given."""
    def run():
        doc = record.emit(args.claim)
        path = getattr(args, "out", None)
        if path:
            record.write(doc, path)
            key = getattr(args, "key", None)
            if key:
                record.sign(path, key)
        return {"ok": True, **doc}
    return _generic_contract("record", args, run)


def _r_attest(args) -> dict:
    """`attest`: lightweight testimony that THIS build's verdicts
    reproduce, signed (`attest.attest`)."""
    return _generic_contract("attest", args,
                              lambda: attest.attest(args.claim, args.key, args.identity))


def _r_attest_check(args) -> dict:
    """`attest_check`: is each attestation intact, non-drifted, and --
    given anchored signers -- actually signed (`attest.check`)."""
    return _generic_contract("attest_check", args,
                              lambda: attest.check(args.claim, signers=getattr(args, "signers", None)))


def _r_review(args) -> dict:
    """`review`: what a keyholder reads before signing -- identity, the
    folded sign_root, a fresh cold audit, recorded-proof state
    (`attest.review_packet`)."""
    return _generic_contract("review", args, lambda: attest.review_packet(args.claim, args.workspace))


def _r_sign(args) -> dict:
    """`sign`: the accountable authorization ceremony over a reviewed
    claim (`attest.sign`)."""
    return _generic_contract("sign", args,
                              lambda: attest.sign(args.claim, args.key, args.identity, args.workspace))


def _r_sign_check(args) -> dict:
    """`sign_check`: the ceremony's own integrity -- is each authorization
    anchored and its reviewed packet intact (`attest.sign_check`)."""
    return _generic_contract("sign_check", args,
                              lambda: attest.sign_check(args.claim, args.workspace,
                                                         signers=getattr(args, "signers", None)))


# -- moving a claim between places ---------------------------------------

def _r_export(args) -> dict:
    """`export`: a deterministic tar of a claim's declared content
    (`transfer.export`)."""
    blind = getattr(args, "blind", False)
    return _generic_contract("export", args, lambda: transfer.export(args.claim, args.out, blind=blind))


def _r_import(args) -> dict:
    """`import`: extract a tar's declared content and verify the claim's
    identity holds from the received bytes alone (`transfer.import_`)."""
    return _generic_contract("import", args, lambda: transfer.import_(args.tar, args.dest))


def _r_pull(args) -> dict:
    """`pull`: materialize a claim as a dependency of a fresh workspace
    (`registry.pull`)."""
    return _generic_contract("pull", args, lambda: registry.pull(args.claim, args.dest))


def _r_pack(args) -> dict:
    """`pack`: seal a project as a self-claim from declared glob patterns
    (`pack.pack`)."""
    def run():
        return pack.pack(
            args.workspace, args.name,
            generated=getattr(args, "generated", ()),
            inputs=getattr(args, "inputs", ()),
            gate=args.gate, gate_output=args.gate_output,
            mutation_floor=getattr(args, "mutation_floor", None),
            requires=getattr(args, "requires", None),
            by=getattr(args, "by", None),
            envelope=getattr(args, "envelope", None),
        )
    return _generic_contract("pack", args, run)
