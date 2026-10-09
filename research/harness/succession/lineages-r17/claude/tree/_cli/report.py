"""The action-verb renderers (`spec/layers.md`: surface, `_cli/report.py`).

Every verb's own layer (`kernel`, `registry`, `attest`, `transfer`, `pack`,
`hooks`, `assess`) does the work and hands back a result shaped however that
layer finds natural; nothing here calls into a layer or touches a
filesystem -- presentation only, the same discipline `render.py` states for
itself. `_generic_contract` is the one path every `_r_<verb>` function
funnels through: derive `ok`/`status` from a result the ordinary way (an
`"ok"` key, a `"status"` key, else `"ok"`/`"failed"`) and close the verb out
through `output._finish`, so every verb speaks the same `--json` envelope and
one-voice text line no matter how differently its own result dict is shaped.
A handful of verbs (`audit`, `crosscheck`, `record`, `assess`) print a short
extra line or two of detail in text mode, through `output._line`, which stays
silent under `--json` on its own.

`_row`/`_when` are the two small display helpers every renderer here can
reach for: a "label: value" text line, and a `spec/record.md` UTC stamp
rendered with its relative age.

Stdlib only.
"""
import datetime

from reticuli import render
from reticuli._cli import output


# =============================================================================
# shared helpers
# =============================================================================

def _row(label: str, value) -> str:
    """One "label: value" text line; a falsy `value` renders as `"--"`."""
    if value in (None, "", [], {}):
        value = "--"
    return f"{label}: {value}"


def _when(stamp: str) -> str:
    """A `spec/record.md` UTC `when` stamp rendered with its relative age,
    e.g. `"2026-09-16T20:14:03Z (3 hours ago)"`; the bare stamp if it is
    missing or does not parse."""
    if not stamp:
        return "--"
    try:
        dt = datetime.datetime.strptime(
            stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
    except ValueError:
        return stamp
    age = (datetime.datetime.now(datetime.timezone.utc) - dt).total_seconds()
    return f"{stamp} ({render.ago(age)})"


# =============================================================================
# the shared `_finish` contract
# =============================================================================

def _generic_contract(command: str, data, args, *, ok=None, status=None,
                       error: str = None) -> bool:
    """Close `command` out through `output._finish`, deriving `ok`/`status`
    from `data` the ordinary way unless the caller already knows them.

    Returns the `ok` value used, so a renderer that prints extra detail
    lines can gate them on it without recomputing anything.
    """
    if not isinstance(data, dict):
        data = {"result": data}
    if ok is None:
        ok = bool(data.get("ok", True))
    if status is None:
        status = data.get("status") or ("ok" if ok else "failed")
    output._finish(command, data, ok, status, args, error=error)
    return ok


# =============================================================================
# kernel verbs
# =============================================================================

def _r_verify(args, result: dict) -> bool:
    """Render `kernel.verify`: `ok` iff present bytes still hash to the
    sealed root (`spec/verification.md`: identity only, no gate run)."""
    ok = result.get("ok", False)
    return _generic_contract("verify", result, args, ok=ok,
                              status="ok" if ok else "mismatch")


def _r_seal(args, manifest: dict) -> bool:
    """Render `kernel.seal`: freezing a present workspace never fails short
    of raising."""
    return _generic_contract("seal", manifest, args, ok=True, status="sealed")


def _r_rebuild(args, result: dict) -> bool:
    """Render `kernel.rebuild` / `registry.rebuild_chain`: the generated
    outputs regrew and every gate passed, or the call would have raised."""
    return _generic_contract("rebuild", result, args, ok=True, status="rebuilt")


def _r_audit(args, result: dict) -> bool:
    """Render `kernel.audit` / `registry.audit_deep`: `ok` iff every
    verdict is earned, not carried (`spec/verification.md`). In text mode,
    one extra line per gate names its own status."""
    ok = result.get("ok", False)
    status = result.get("verdict") or ("ok" if ok else "failed")
    done = _generic_contract("audit", result, args, ok=ok, status=status)
    for gate in result.get("gates", []):
        output._line(args, "  " + _row(gate.get("output", "?"), gate.get("status")))
    return done


def _r_crosscheck(args, result: dict) -> bool:
    """Render `kernel.crosscheck` / `registry.crosscheck_deep`: the
    three-valued verdict (`spec/verification.md`) -- `satisfied` is `True`
    only when the verdict is `accept`. Text mode lists each hard condition
    that rejected or stayed incomplete."""
    ok = result.get("satisfied", result.get("verdict") == "accept")
    status = result.get("verdict", "incomplete")
    done = _generic_contract("crosscheck", result, args, ok=ok, status=status)
    for reason in result.get("rejected", []):
        output._line(args, f"  rejected: {reason}")
    for reason in result.get("incomplete", []):
        output._line(args, f"  incomplete: {reason}")
    return done


def _r_record(args, doc: dict) -> bool:
    """Render a `record.emit` document (`spec/record.md`): `ok` iff every
    gate the document states ran `ok`. Text mode adds the signer-facing
    `when` stamp."""
    gates = doc.get("gates", [])
    ok = bool(gates) and all(g.get("status") == "ok" for g in gates)
    done = _generic_contract("record", doc, args, ok=ok, status="recorded")
    output._line(args, _row("when", _when(doc.get("when"))))
    return done


def _r_sign(args, result: dict) -> bool:
    """Render `attest.sign`: the authorization ceremony (`spec/layers.md`)
    either lands a statement or raises."""
    return _generic_contract("sign", result, args, ok=True, status="signed")


def _r_sign_check(args, result: dict) -> bool:
    """Render `attest.sign_check`: `ok` iff at least one authorization
    verifies against the trust anchor and its packet still holds."""
    ok = result.get("ok", False)
    return _generic_contract("sign-check", result, args, ok=ok,
                              status="authorized" if ok else "unauthorized")


# =============================================================================
# exchange verbs
# =============================================================================

def _r_export(args, result: dict) -> bool:
    """Render `transfer.export`: a deterministic tar lands or the call
    raises."""
    return _generic_contract("export", result, args, ok=True, status="exported")


def _r_import(args, result: dict) -> bool:
    """Render `transfer.import_`: `ok` iff identity re-verifies on the
    received bytes."""
    ok = result.get("ok", False)
    return _generic_contract("import", result, args, ok=ok,
                              status="ok" if ok else "mismatch")


def _r_pull(args, result: dict) -> bool:
    """Render `registry.pull`: `ok` iff the claim materialized as a plain
    dependency of the target workspace."""
    ok = result.get("materialized", False)
    return _generic_contract("pull", result, args, ok=ok,
                              status="pulled" if ok else "failed")


def _r_attest(args, result: dict) -> bool:
    """Render `attest.attest`: a plain signed build statement lands or the
    call raises (it re-earns the verdict first, per that module)."""
    return _generic_contract("attest", result, args, ok=True, status="attested")


def _r_attest_check(args, result: dict) -> bool:
    """Render `attest.check`: `ok` iff every statement present still
    matches the claim's current bytes (and verifies, where an anchor was
    given)."""
    ok = result.get("ok", False)
    return _generic_contract("attest-check", result, args, ok=ok,
                              status="ok" if ok else "drifted")


def _r_review(args, result: dict) -> bool:
    """Render `attest.review_packet`: the pre-signing summary a human reads
    before running `sign` -- `ok` mirrors the nested audit's own verdict."""
    audit = result.get("audit") or {}
    ok = audit.get("ok", False)
    return _generic_contract("review", result, args, ok=ok,
                              status=audit.get("verdict", "incomplete"))


def _r_pack(args, result: dict) -> bool:
    """Render `pack.pack`: writing and sealing a self-claim."""
    return _generic_contract("pack", result, args, ok=result.get("ok", True),
                              status="packed")


def _r_hooks(args, result: dict) -> bool:
    """Render `hooks.install`: wiring the agent handshake into a project's
    settings never fails short of raising."""
    return _generic_contract("hooks", result, args, ok=True,
                              status=result.get("status", "wired"))


# =============================================================================
# surface verbs
# =============================================================================

def _t_init(result: dict) -> str:
    """The terse one-line summary of an `init` result: where a session's
    draft trace now lives."""
    return f"initialized {result.get('workspace', '.')}"


def _r_init(args, result: dict) -> bool:
    """Render `init`: starting a session's draft trace never fails short of
    raising. Text mode adds `_t_init`'s one-line summary."""
    done = _generic_contract("init", result, args, ok=True, status="initialized")
    output._line(args, _t_init(result))
    return done


def _r_assess(args, result: dict) -> bool:
    """Render `assess.assess`: a mutation-coverage measurement, never a
    pass/fail verdict on its own -- `ok` only says the measurement ran.
    Text mode adds the kill rate."""
    done = _generic_contract("assess", result, args, ok=True, status="measured")
    output._line(args, _row("rate", result.get("rate")))
    return done
