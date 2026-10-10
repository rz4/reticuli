"""Report: rendering for the action-verb surface (verify, audit, assess,
rebuild, seal, crosscheck, record, sign, attest, export, pack, ...).

Each `_r_<verb>` takes the verb's own result dict and the parsed CLI
`args`, prints the right view -- a short line by default, a fuller table
under `-v`/`--verbose`, nothing at all under `--json` (the envelope is
the whole of stdout there) -- and returns exactly what `output._finish`
produced, the one shape a script can read back whether a human saw the
printed line or not. `_row`/`_when` are the two small formatting choices
every renderer below shares: one labeled value, one timestamp. A verb
with nothing bespoke to say beyond its own fields renders through
`_generic_contract` rather than growing a one-line `_r_<verb>` of its
own.
"""
from .. import render
from . import output


def _when(ts) -> str:
    """A ledger/record timestamp, human: `render.ago` where parseable,
    `"unknown"` where absent, the raw value otherwise -- a malformed
    stamp is a display problem, not a reason to refuse the rest of the
    row."""
    if not ts:
        return "unknown"
    try:
        return render.ago(ts)
    except (ValueError, TypeError):
        return str(ts)


def _row(label: str, value) -> tuple:
    """One row of a verbose dump: `label` paired with `value`, with an
    empty value shown as `-` so a table column is never blank."""
    return (label, "-" if value in (None, "", [], {}) else value)


def _verbose(args) -> bool:
    return bool(getattr(args, "verbose", False)) and not getattr(args, "json", False)


def _dump(rows, args, *, headers=None) -> None:
    output._line(render.table(rows, headers=headers), args=args)


def _generic_contract(cmd: str, result: dict, args, *, ok_key: str = "ok",
                       status_key: str = None, root_key: str = "root") -> dict:
    """The fallback renderer: `ok` (default `True` when the key is
    absent -- a verb whose result carries no verdict field earned its
    envelope just by returning), an optional named status field (else
    `"ok"`/`"failed"`), and an optional root. Verbose mode dumps every
    field of `result` as a row."""
    ok = bool(result.get(ok_key, True))
    status = result.get(status_key) if status_key else ("ok" if ok else "failed")
    root = result.get(root_key)
    if _verbose(args):
        _dump([_row(k, v) for k, v in result.items()], args)
    return output._finish(cmd, result, ok, status, args, root)


def _gates_rows(gates) -> list:
    return [(g.get("output"), g.get("status"), g.get("quarantine") or "-")
            for g in (gates or [])]


# ------------------------------------------------------------- identity ----

def _r_verify(result: dict, args) -> dict:
    ok = result["ok"]
    if _verbose(args):
        _dump([_row("name", result.get("name")), _row("root", result.get("root")),
               _row("recomputed", result.get("recomputed"))], args)
    return output._finish("verify", result, ok, "ok" if ok else "mismatch", args, result.get("root"))


def _r_seal(result: dict, args) -> dict:
    if _verbose(args):
        _dump([_row(k, v) for k, v in result.items()], args)
    return output._finish("seal", result, True, "sealed", args, result.get("root"))


def _r_audit(result: dict, args) -> dict:
    ok = result["ok"]
    status = result.get("verdict", "ok" if ok else "broken")
    if _verbose(args):
        if result.get("environment"):
            _dump([_row("environment", result["environment"])], args)
        _dump(_gates_rows(result.get("gates")), args, headers=("output", "status", "quarantine"))
    return output._finish("audit", result, ok, status, args, result.get("root"))


def _r_assess(result: dict, args) -> dict:
    ok = result["not_measured"] == 0
    status = "clean" if ok else "gaps"
    if _verbose(args):
        _dump([_row("measured", result["measured"]), _row("not measured", result["not_measured"]),
               _row("not applicable", result["not_applicable"])], args)
        if result.get("vacuous_gates"):
            _dump([_row("vacuous gate", g) for g in result["vacuous_gates"]], args)
    return output._finish("assess", result, ok, status, args, None)


def _r_rebuild(result: dict, args) -> dict:
    if _verbose(args):
        _dump([_row("name", result.get("name")), _row("root", result.get("root")),
               _row("quarantine", result.get("quarantine"))], args)
        _dump(_gates_rows(result.get("gates")), args, headers=("output", "status", "quarantine"))
    return output._finish("rebuild", result, True, "rebuilt", args, result.get("root"))


def _r_pack(result: dict, args) -> dict:
    ok = result.get("ok", True)
    if _verbose(args):
        _dump([_row("name", result.get("name")), _row("root", result.get("root"))], args)
    return output._finish("pack", result, ok, "packed" if ok else "failed", args, result.get("root"))


# ------------------------------------------------------------- crosscheck --

def _r_crosscheck(result: dict, args) -> dict:
    ok = result["satisfied"]
    status = result["verdict"]
    root = (result.get("roots") or {}).get("M1")
    if _verbose(args):
        _dump([_row("equivalence", result.get("equivalence")), _row("reuse", result.get("reuse")),
               _row("rejected", result.get("rejected")), _row("incomplete", result.get("incomplete")),
               _row("independence", result.get("independence"))], args)
        cost = result.get("cost") or {}
        _dump([_row("comparable", cost.get("comparable"))], args)
    return output._finish("crosscheck", result, ok, status, args, root)


# ------------------------------------------------------------------ record --

def _r_record(result: dict, args) -> dict:
    if _verbose(args):
        _dump([_row("name", result.get("name")), _row("root", result.get("root")),
               _row("build digest", result.get("build_digest")), _row("when", _when(result.get("when")))], args)
        _dump(_gates_rows(result.get("gates")), args, headers=("output", "status", "sandbox"))
    return output._finish("record", result, True, "recorded", args, result.get("root"))


# ------------------------------------------------------------------ attest --

def _r_attest(result: dict, args) -> dict:
    if _verbose(args):
        _dump([_row(k, v) for k, v in result.items()], args)
    return output._finish("attest", result, True, "attested", args, result.get("root"))


def _r_attest_check(result: dict, args) -> dict:
    ok = result["ok"]
    if _verbose(args):
        rows = [(a.get("identity") or "-", a.get("root") or "-", a.get("verdict"))
                for a in result.get("attestations", [])]
        _dump(rows, args, headers=("identity", "root", "verdict"))
    return output._finish("attest-check", result, ok, "ok" if ok else "failed", args, None)


# -------------------------------------------------------------- ceremony --

def _r_review(result: dict, args) -> dict:
    ok = result["audit"]["ok"] and (result.get("deep_audit") is None or result["deep_audit"]["ok"])
    if _verbose(args):
        _dump([_row("root", result.get("root")), _row("sign root", result.get("sign_root")),
               _row("build digest", result.get("build_digest")), _row("proof", result.get("proof"))], args)
        _dump(_gates_rows(result["audit"].get("gates")), args, headers=("output", "status", "quarantine"))
    return output._finish("review", result, ok, "clean" if ok else "broken", args, result.get("root"))


def _r_sign(result: dict, args) -> dict:
    if _verbose(args):
        _dump([_row(k, v) for k, v in result.items()], args)
    return output._finish("sign", result, True, "signed", args, result.get("sign_root"))


def _r_sign_check(result: dict, args) -> dict:
    ok = result["ok"]
    if _verbose(args):
        rows = [(a.get("identity") or "-", a.get("root") or "-", a.get("verdict"))
                for a in result.get("authorizations", [])]
        _dump(rows, args, headers=("identity", "root", "verdict"))
    return output._finish("sign-check", result, ok, "ok" if ok else "failed", args, None)


# ------------------------------------------------------------- exchange --

def _r_export(result: dict, args) -> dict:
    if _verbose(args):
        _dump([_row("path", result.get("path"))], args)
    return output._finish("export", result, True, "exported", args, result.get("root"))


def _r_import(result: dict, args) -> dict:
    ok = result.get("ok", False)
    if _verbose(args):
        _dump([_row(k, v) for k, v in result.items()], args)
    return output._finish("import", result, ok, "ok" if ok else "failed", args, result.get("root"))


def _r_pull(result: dict, args) -> dict:
    if _verbose(args):
        _dump([_row(k, v) for k, v in result.items()], args)
    return output._finish("pull", result, True, "pulled", args, result.get("root"))


# ------------------------------------------------------------------ hooks --

def _r_hooks(result: dict, args) -> dict:
    status = result.get("status") or ("wired" if result.get("wired") else "already wired")
    if _verbose(args) and result.get("wired"):
        _dump([_row("event", e) for e in result["wired"]], args)
    return output._finish("hooks", result, True, status, args, None)


# ------------------------------------------------------------------- init --

def _t_init(result: dict) -> str:
    """The terse line `init` prints by default: where the fresh draft
    landed, named what."""
    name = result.get("name") or "(unnamed)"
    path = result.get("path") or "."
    return f"drafted {name!r} at {path}"


def _r_init(result: dict, args) -> dict:
    if _verbose(args):
        _dump([_row(k, v) for k, v in result.items()], args)
    else:
        output._line(_t_init(result), args=args)
    return output._finish("init", result, True, "draft", args, None)
