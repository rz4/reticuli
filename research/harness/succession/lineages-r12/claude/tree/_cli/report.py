"""Action-verb renderers: `verify`, `audit`, `assess`, `rebuild`, `seal`,
`crosscheck`, `record`, `sign`, `export`, `pack`, `attest`, `attest_check`,
`sign_check`, `import`, `pull`, `hooks`, `init`, `review` (`spec/layers.md`'s
surface layer).

Every verb's renderer collapses to one shape: run the layer call, and turn
its outcome -- a result dict, or a `kernel.ClaimError` refusal -- into the
CLI's one output contract (`_cli/output.py`'s `_finish`/`_err`). That shape
is `_generic_contract`; every `_r_*` function below is a thin binding of
one verb's call onto it. `_row` and `_when` are the small render helpers
the family shares for listing detail lines.

Exact human-facing wording is not pinned here -- the comprehensive surface
suite driving the assembled CLI pins it; this module only has to import
cleanly against the layers below and expose the renderer surface whole.

Stdlib only.
"""
import os

from .. import assess as assess_mod
from .. import attest as attest_mod
from .. import hooks as hooks_mod
from .. import kernel
from .. import pack as pack_mod
from .. import record as record_mod
from .. import registry
from .. import render
from .. import transfer
from . import output


# ---------------------------------------------------------------------------
# Shared render helpers
# ---------------------------------------------------------------------------

def _row(label: str, value) -> str:
    """One `label: value` line of verbose/table detail output."""
    return f"  {label}: {value}"


def _when(ts) -> str:
    """A human-friendly rendering of a timestamp -- a float unix epoch
    rendered directly, or a `spec/record.md` UTC string (`when`) parsed
    first."""
    if isinstance(ts, str):
        from datetime import datetime, timezone
        dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        ts = dt.timestamp()
    return render.ago(ts)


# ---------------------------------------------------------------------------
# The one output contract every verb's renderer collapses to
# ---------------------------------------------------------------------------

def _result_ok(data: dict) -> bool:
    if "ok" in data:
        return bool(data["ok"])
    if "satisfied" in data:
        return bool(data["satisfied"])
    audit = data.get("audit")
    if isinstance(audit, dict) and "ok" in audit:
        return bool(audit["ok"])
    return True


def _result_status(data: dict, ok: bool) -> str:
    if "verdict" in data:
        return data["verdict"]
    if "status" in data:
        return data["status"]
    return "ok" if ok else "failed"


def _result_root(data: dict):
    for key in ("root", "recomputed"):
        if key in data:
            return data[key]
    return None


def _generic_contract(cmd: str, fn, args, *fn_args, **fn_kwargs) -> dict:
    """Run `fn`, and render its outcome through the CLI's one contract: a
    `kernel.ClaimError` refusal becomes `_err` plus a `refused` envelope; a
    result becomes `_finish`'s envelope, with `ok`/`status`/`root` read
    from whichever of the layer's own result-dict conventions apply.
    """
    try:
        result = fn(*fn_args, **fn_kwargs)
    except kernel.ClaimError as e:
        output._err(cmd, str(e))
        return output._finish(cmd, {}, False, "refused", args, None)
    data = result if isinstance(result, dict) else {"result": result}
    ok = _result_ok(data)
    status = _result_status(data, ok)
    root = _result_root(data)
    return output._finish(cmd, data, ok, status, args, root)


# ---------------------------------------------------------------------------
# Identity and verdicts
# ---------------------------------------------------------------------------

def _r_verify(d: str, args) -> dict:
    return _generic_contract("verify", kernel.verify, args, d)


def _r_seal(d: str, args) -> dict:
    return _generic_contract("seal", registry.seal_with, args, d)


def _r_audit(d: str, args, produce_from: dict = None) -> dict:
    return _generic_contract("audit", kernel.audit, args, d, produce_from)


def _r_assess(d: str, args, mutants: int = None) -> dict:
    return _generic_contract("assess", assess_mod.assess, args, d, mutants)


def _r_rebuild(d: str, args, producer: str, into: str, **kwargs) -> dict:
    with output._Progress(args, total=1) as progress:
        progress.step(f"rebuilding {output._rel(d)} into {output._rel(into)}")
        return _generic_contract("rebuild", kernel.rebuild, args, d, producer, into, **kwargs)


# ---------------------------------------------------------------------------
# The three-machine test
# ---------------------------------------------------------------------------

def _r_crosscheck(leg1: str, leg2: str, leg3: str, args, mutants: int = None,
                  deep: bool = False) -> dict:
    fn = registry.crosscheck_deep if deep else kernel.crosscheck
    return _generic_contract("crosscheck", fn, args, leg1, leg2, leg3, mutants)


def _r_record(d: str, args, out: str = None) -> dict:
    def _run(d):
        doc = record_mod.emit(d)
        if out:
            record_mod.write(doc, out)
        return doc
    return _generic_contract("record", _run, args, d)


# ---------------------------------------------------------------------------
# Attestation and the signing ceremony
# ---------------------------------------------------------------------------

def _r_attest(d: str, args, key: str, identity: str) -> dict:
    return _generic_contract("attest", attest_mod.attest, args, d, key, identity)


def _r_attest_check(d: str, args, signers: str = None) -> dict:
    return _generic_contract("attest", attest_mod.check, args, d, signers)


def _r_sign(d: str, args, key: str, identity: str, ws: str = None) -> dict:
    return _generic_contract("sign", attest_mod.sign, args, d, key, identity, ws)


def _r_sign_check(d: str, args, ws: str = None, signers: str = None) -> dict:
    return _generic_contract("sign", attest_mod.sign_check, args, d, ws, signers)


def _r_review(d: str, args, ws: str = None) -> dict:
    return _generic_contract("review", attest_mod.review_packet, args, d, ws)


# ---------------------------------------------------------------------------
# Transfer and the registry
# ---------------------------------------------------------------------------

def _r_export(d: str, args, tar_path: str, blind: bool = False) -> dict:
    return _generic_contract("export", transfer.export, args, d, tar_path, blind)


def _r_import(args, tar_path: str, into: str) -> dict:
    return _generic_contract("import", transfer.import_, args, tar_path, into)


def _r_pull(args, d: str, ws2: str) -> dict:
    return _generic_contract("pull", registry.pull, args, d, ws2)


def _r_pack(args, root: str, name: str, **kwargs) -> dict:
    return _generic_contract("pack", pack_mod.pack, args, root, name, **kwargs)


# ---------------------------------------------------------------------------
# Agents and a fresh claim
# ---------------------------------------------------------------------------

def _r_hooks(args, proj: str) -> dict:
    return _generic_contract("hooks", hooks_mod.install, args, proj)


def _t_init(name: str) -> str:
    """The skeleton recipe `init` writes, rendered as text -- shown to a
    human before anything touches disk."""
    recipe = {"claim": {"name": name, "inputs": []}, "step": []}
    return render.dump_recipe(recipe)


def _r_init(d: str, args, name: str) -> dict:
    def _run(d, name):
        recipe_path = os.path.join(d, kernel.RECIPE)
        if os.path.isfile(recipe_path):
            raise kernel.ClaimError(f"refused: {recipe_path!r} already exists")
        os.makedirs(d, exist_ok=True)
        with open(recipe_path, "w", encoding="utf-8") as f:
            f.write(_t_init(name))
        return {"ok": True, "name": name, "path": recipe_path}
    return _generic_contract("init", _run, args, d, name)
