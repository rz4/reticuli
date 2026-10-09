"""The surface layer's action-verb renderers: one `_r_<verb>` per CLI verb
that calls a layer below and gets back a result dict, turning that dict
into the short human-facing block printed on the non-`--json` path
(`_cli/output.py`'s `_finish` is where the `--json` envelope lives instead).

Every specific renderer composes `_generic_contract`, so the one-voice
`label: value` block format (`_row`) never drifts between verbs; `_when`
is the one shared rendering of a `spec/record.md` UTC stamp. `_t_init` is
the one-line terse form of `_r_init`, the same split `_cli/statusview.py`
makes between its `_t_*`/`_v_*`/`_r_*` renderers.

Built from `reticuli.render` alone, so this module never reaches past the
authoring layer it sits above (`spec/layers.md`). Stdlib only.
"""
import calendar
import time

from reticuli import render


def _row(label: str, value) -> str:
    """One `label: value` line, indented for a renderer's body."""
    return f"  {label}: {value}"


def _when(stamp) -> str:
    """A `spec/record.md` UTC stamp (`YYYY-MM-DDTHH:MM:SSZ`) rendered with
    how long ago it was; an absent or unparseable stamp is shown as given
    rather than raising -- a renderer must still show *something*.
    """
    if not stamp:
        return "unknown"
    try:
        parsed = time.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        return str(stamp)
    elapsed = max(time.time() - calendar.timegm(parsed), 0)
    return f"{stamp} ({render.ago(elapsed)})"


def _generic_contract(title: str, data, fields=None) -> str:
    """Render `data` as `title` followed by one `_row` per key: `fields`,
    in order, when given (skipping any key `data` does not carry), else
    every key of `data` in sorted order. The one rendering primitive every
    specific `_r_*` renderer below composes from, so a verb whose result
    is just a flat dict of facts never needs its own hand-written block.
    """
    if not isinstance(data, dict):
        return f"{title}\n{_row('result', data)}"
    keys = [k for k in (fields if fields is not None else sorted(data)) if k in data]
    return "\n".join([title] + [_row(k, data[k]) for k in keys])


# -- kernel verbs -----------------------------------------------------------


def _r_seal(data: dict) -> str:
    return _generic_contract(f"seal: {data.get('name', '?')}", data, fields=("root",))


def _r_verify(data: dict) -> str:
    ok = data.get("ok")
    fields = ["name", "root"] + ([] if ok else ["recomputed", "changed"])
    return _generic_contract(f"verify: {'holds' if ok else 'drifted'}", data, fields=fields)


def _r_rebuild(data: dict) -> str:
    return _generic_contract("rebuild: regrown", data,
                              fields=("root", "quarantine", "rebuilt_components"))


def _r_audit(data: dict) -> str:
    return _generic_contract(f"audit: {data.get('verdict', '?')}", data,
                              fields=("ok", "verdict", "root", "layers"))


def _r_crosscheck(data: dict) -> str:
    return _generic_contract(f"crosscheck: {data.get('verdict', '?')}", data,
                              fields=("satisfied", "verdict", "roots", "deep"))


def _r_sign(data: dict) -> str:
    return _generic_contract("sign: recorded", data,
                              fields=("ceremony", "signature", "statement", "packet"))


# -- exchange-layer verbs: attest, record, transfer -------------------------


def _r_record(data: dict) -> str:
    title = f"record: {data.get('name', '?')} {render.short(data.get('root') or '')}"
    lines = [title, _row("when", _when(data.get("when")))]
    for gate in data.get("gates") or []:
        lines.append(_row(f"gate {gate.get('output')}", gate.get("status")))
    cost = data.get("cost")
    if cost:
        lines.append(_row("cost", cost))
    return "\n".join(lines)


def _r_attest(data: dict) -> str:
    return _generic_contract("attest: signed", data, fields=("signature", "statement"))


def _r_attest_check(data: dict) -> str:
    title = f"attest-check: {'ok' if data.get('ok') else 'failed'}"
    lines = [title]
    for a in data.get("attestations") or []:
        lines.append(_row(a.get("identity") or "?", a.get("verdict")))
    return "\n".join(lines)


def _r_sign_check(data: dict) -> str:
    title = f"sign-check: {'authorized' if data.get('ok') else 'unauthorized'}"
    lines = [title]
    for a in data.get("authorizations") or []:
        lines.append(_row(a.get("identity") or "?", a.get("verdict")))
    return "\n".join(lines)


def _r_review(data: dict) -> str:
    audit = data.get("audit") or {}
    return "\n".join([
        "review",
        _row("root", data.get("root")),
        _row("build_digest", data.get("build_digest")),
        _row("sign_root", data.get("sign_root")),
        _row("audit", audit.get("verdict", "?")),
        _row("proof", "recorded" if data.get("proof") else "none"),
    ])


def _r_export(data: dict) -> str:
    return _generic_contract("export", data, fields=("exported", "path"))


def _r_import(data: dict) -> str:
    ok = data.get("ok")
    fields = ("name", "root") if ok else ("reason",)
    return _generic_contract(f"import: {'ok' if ok else 'failed'}", data, fields=fields)


def _r_pull(data: dict) -> str:
    return _generic_contract(f"pull: {data.get('name', '?')}", data, fields=("root",))


def _r_pack(data: dict) -> str:
    return _generic_contract("pack: sealed", data, fields=("root",))


# -- agents / surface verbs: hooks, assess, init -----------------------------


def _r_hooks(data: dict) -> str:
    return _generic_contract(f"hooks: {data.get('status', '?')}", data, fields=("wired",))


def _r_assess(data: dict) -> str:
    return _generic_contract("assess", data, fields=(
        "rate", "killed", "measured", "not_measured", "not_applicable", "survivors"))


def _r_init(data: dict) -> str:
    return _generic_contract(f"init: {data.get('status', 'initialized')}", data,
                              fields=("path",))


def _t_init(data: dict) -> str:
    """The one-line form of `_r_init`."""
    return f"init: {data.get('status', 'initialized')}"
