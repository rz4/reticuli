"""reticuli._cli.report: the action-verb renderers.

One `_r_*` function per CLI verb, each taking the verb's already-computed
result dict (whatever `kernel`, `registry`, `attest`, `record`, `pack`,
`transfer`, or `hooks` returned) and `args` (for `--json`/`-v`/`--color`),
and rendering it through the shared envelope (`_generic_contract`, a thin
wrap of `output._finish`). Verbose mode adds verb-specific detail rows via
`_row`; `--json` always wins and prints nothing but the envelope.

`_t_init` is the terse, one-line form of an `init` result, for a caller
that wants a summary without the full envelope (e.g. a batch listing).

None of this calls back into `kernel` itself: the verb already ran by the
time its result reaches a renderer here, so this module only ever reads
the dict it is handed.

Stdlib only.
"""
import datetime

from reticuli import render
from reticuli._cli import output


def _row(key, value, *, indent: int = 2) -> None:
    """One `  key: value` line, the verbose-mode primitive every
    `_r_*` renderer below shares."""
    output._line(" " * indent + f"{key}: {value}")


def _when(ts) -> str:
    """A human gloss of a timestamp that may be a unix epoch number
    (ledger/trace events) or an ISO-8601 `when` string (a record, an
    attestation) -- `render.ago`'s spelling either way, or the raw
    value when neither reading applies."""
    if isinstance(ts, bool):
        return str(ts)
    if isinstance(ts, (int, float)):
        return render.ago(ts)
    if isinstance(ts, str):
        try:
            dt = datetime.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            return ts
        return render.ago(dt.replace(tzinfo=datetime.timezone.utc).timestamp())
    return "unknown"


def _verbose(args) -> bool:
    return bool(getattr(args, "verbose", False)) and not getattr(args, "json", False)


def _generic_contract(cmd: str, result: dict, args) -> dict:
    """The envelope every action verb shares: ok/refused, root, status --
    `output._finish` wearing one verb's result. Every `_r_*` renderer
    calls this first, then lays its own verbose rows on top."""
    result = result if isinstance(result, dict) else {"ok": bool(result)}
    ok = bool(result.get("ok", True))
    status = result.get("status") or result.get("verdict") or ("ok" if ok else "refused")
    return output._finish(cmd, result, ok, status, args)


# ---- identity and verdicts -------------------------------------------------

def _r_verify(result: dict, args) -> dict:
    env = _generic_contract("verify", result, args)
    if _verbose(args):
        _row("recomputed", result.get("recomputed"))
    return env


def _r_audit(result: dict, args) -> dict:
    env = _generic_contract("audit", result, args)
    if _verbose(args):
        for gate in result.get("gates", []):
            _row(gate.get("output"), f"{gate.get('status')} (quarantine={gate.get('quarantine')})")
        for missing in result.get("environment", []):
            _row("missing", missing)
    return env


def _r_assess(result: dict, args) -> dict:
    env = _generic_contract("assess", result, args)
    if _verbose(args):
        _row("mutants", result.get("mutants"))
        _row("rate", result.get("rate"))
        for bucket in ("measured", "not_measured", "not_applicable"):
            for path in result.get(bucket, []):
                _row(bucket, path)
    return env


# ---- regrowth and sealing ---------------------------------------------------

def _r_rebuild(result: dict, args) -> dict:
    env = _generic_contract("rebuild", result, args)
    if _verbose(args):
        _row("quarantine", result.get("quarantine"))
        for gate in result.get("gates", []):
            _row(gate.get("output"), gate.get("status"))
        for comp in result.get("rebuilt_components") or []:
            _row("component", f"{comp.get('component')} -> {render.short(comp.get('root') or '')}")
    return env


def _r_seal(result: dict, args) -> dict:
    env = _generic_contract("seal", result, args)
    if _verbose(args):
        for comp in result.get("components") or []:
            _row("component", comp.get("component"))
    return env


def _r_pack(result: dict, args) -> dict:
    return _generic_contract("pack", result, args)


def _r_init(result: dict, args) -> dict:
    env = _generic_contract("init", result, args)
    if _verbose(args):
        for name in result.get("created", []):
            _row("created", name)
    return env


def _t_init(result: dict, args=None) -> str:
    """The terse, one-line form of an `init` result."""
    path = result.get("path", "")
    created = result.get("created") or []
    return f"init: {path} ({len(created)} file(s))"


# ---- the three-machine test and the record transport ------------------------

def _r_crosscheck(result: dict, args) -> dict:
    env = _generic_contract("crosscheck", result, args)
    if _verbose(args):
        for role, r in (result.get("roots") or {}).items():
            _row(role, render.short(r) if r else r)
        if result.get("rejected"):
            _row("rejected", ", ".join(result["rejected"]))
        if result.get("incomplete"):
            _row("incomplete", ", ".join(result["incomplete"]))
        _row("independence", result.get("independence"))
    return env


def _r_record(result: dict, args) -> dict:
    env = _generic_contract("record", result, args)
    if _verbose(args):
        if "when" in result:
            _row("when", _when(result.get("when")))
        for gate in result.get("gates", []):
            _row(gate.get("output"), gate.get("status"))
    return env


def _r_export(result: dict, args) -> dict:
    return _generic_contract("export", result, args)


def _r_import(result: dict, args) -> dict:
    return _generic_contract("import", result, args)


def _r_pull(result: dict, args) -> dict:
    env = _generic_contract("pull", result, args)
    if _verbose(args):
        _row("materialized", result.get("materialized"))
        _row("name", result.get("name"))
    return env


# ---- signatures: attestation, authorization, and their checks -------------

def _r_attest(result: dict, args) -> dict:
    env = _generic_contract("attest", result, args)
    if _verbose(args):
        _row("statement", result.get("statement"))
        _row("signature", result.get("signature"))
    return env


def _r_attest_check(result: dict, args) -> dict:
    env = _generic_contract("attest-check", result, args)
    if _verbose(args):
        for a in result.get("attestations", []):
            _row(a.get("identity") or "unknown", a.get("verdict"))
    return env


def _r_sign(result: dict, args) -> dict:
    env = _generic_contract("sign", result, args)
    if _verbose(args):
        _row("statement", result.get("statement"))
        _row("signature", result.get("signature"))
    return env


def _r_sign_check(result: dict, args) -> dict:
    env = _generic_contract("sign-check", result, args)
    if _verbose(args):
        for a in result.get("authorizations", []):
            _row(a.get("identity") or "unknown", a.get("verdict"))
    return env


def _r_review(result: dict, args) -> dict:
    env = _generic_contract("review", result, args)
    if _verbose(args):
        _row("sign_root", render.short(result.get("sign_root") or ""))
        _row("build_digest", render.short(result.get("build_digest") or ""))
        audit = result.get("audit") or {}
        _row("audit", audit.get("verdict"))
    return env


# ---- the agent handshake -----------------------------------------------------

def _r_hooks(result: dict, args) -> dict:
    status = result.get("status", "unknown")
    env = output._finish("hooks", result, status != "error", status, args)
    if _verbose(args):
        for name in result.get("wired", []):
            _row("wired", name)
    return env
