"""Report: rendering the action verbs (spec/layers.md, "surface").

Every verb above the kernel returns a plain result dict -- a manifest, a
verdict, a count -- and never prints anything itself. `report.py` is where
that dict becomes terminal output: one `_r_<verb>` function per verb,
each reducing to the shared contract `_generic_contract` applies
(`output._finish`'s five-field envelope under `--json`, a short colored
line otherwise), returning the process exit code (`0` on success, `1`
otherwise). `_row`/`_when` are the small display helpers a renderer reaches
for; nothing here runs a gate or touches a claim's bytes -- a render is a
presentation of a result already computed below this layer.
"""
from . import output
from .. import render


def _generic_contract(command, result, args, *, ok=None, status=None, root=None):
    """The shape every `_r_*` renderer reduces to: finish `command` with
    `result` as `--json`'s `data`, deriving `ok`/`status`/`root` from the
    result dict unless the caller already knows better (`crosscheck`'s
    `satisfied`, `pull`'s `materialized`, ...). A result with no verdict
    field of its own (`seal`, `export`, `attest`, `sign`, ...) succeeded
    simply by existing -- the call that produced it already raised
    `kernel.ClaimError` on any refusal.
    """
    data = result if isinstance(result, dict) else {"result": result}
    if ok is None:
        ok = data.get("ok", data.get("satisfied", data.get("materialized", True)))
    ok = bool(ok)
    if status is None:
        status = data.get("status") or data.get("verdict") or ("ok" if ok else "failed")
    if root is None:
        root = data.get("root")
    output._finish(command, data, ok, status, args, root)
    return 0 if ok else 1


def _row(label, value):
    """One label/value display line: `"<label>: <value>"`."""
    return f"{label}: {value}"


def _when(when):
    """A timestamp (`spec/record.md`'s `when`, or a Unix epoch) rendered
    as a short relative time, e.g. `"3 minutes ago"`; `"unknown"` for
    `None`.
    """
    if when is None:
        return "unknown"
    return render.ago(when)


# -- verify / audit / assess -------------------------------------------------


def _r_verify(result, args):
    return _generic_contract("verify", result, args)


def _r_audit(result, args):
    return _generic_contract("audit", result, args)


def _r_assess(result, args):
    return _generic_contract("assess", result, args, ok=True, status="measured")


# -- seal / rebuild / crosscheck / record ------------------------------------


def _r_seal(result, args):
    return _generic_contract("seal", result, args, ok=True, status="sealed")


def _r_rebuild(result, args):
    return _generic_contract("rebuild", result, args, ok=True, status="rebuilt")


def _r_crosscheck(result, args):
    root = (result.get("roots") or {}).get("M1") if isinstance(result, dict) else None
    return _generic_contract(
        "crosscheck", result, args,
        ok=result.get("satisfied"), status=result.get("verdict"), root=root,
    )


def _r_record(result, args):
    ok = all(g.get("status") == "ok" for g in result.get("gates", []))
    return _generic_contract("record", result, args, ok=ok, status="recorded")


# -- attest / sign / review --------------------------------------------------


def _r_attest(result, args):
    return _generic_contract("attest", result, args, ok=True, status="attested")


def _r_attest_check(result, args):
    return _generic_contract("attest-check", result, args)


def _r_sign(result, args):
    return _generic_contract("sign", result, args, ok=True, status="signed")


def _r_sign_check(result, args):
    return _generic_contract("sign-check", result, args)


def _r_review(result, args):
    ok = bool(result.get("audit", {}).get("ok", True))
    return _generic_contract("review", result, args, ok=ok, status="reviewed")


# -- export / import / pull / pack -------------------------------------------


def _r_export(result, args):
    return _generic_contract("export", result, args, ok=True, status="exported", root=None)


def _r_import(result, args):
    return _generic_contract("import", result, args)


def _r_pull(result, args):
    return _generic_contract(
        "pull", result, args, ok=result.get("materialized", True), status="pulled",
    )


def _r_pack(result, args):
    return _generic_contract("pack", result, args)


# -- hooks / init -------------------------------------------------------------


def _r_hooks(result, args):
    return _generic_contract("hooks", result, args, ok=True, status=result.get("status"))


def _r_init(result, args):
    return _generic_contract(
        "init", result, args, ok=True, status=result.get("status", "initialized"),
    )


def _t_init(result, args):
    """The terse form of `_r_init`: one line, no envelope."""
    output._line(f"init: {result.get('status', 'initialized')}", args=args)
    return 0
