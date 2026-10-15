"""Rendering an action verb's result -- see `spec/layers.md` (surface layer).

Every verb that DOES something (`verify`, `audit`, `rebuild`, `seal`,
`crosscheck`, `sign`, `record`, ...) hands its `data` dict to one `_r_*`
renderer here, which turns it into the multi-line human report the CLI
prints when `--json` is absent. `_generic_contract` is the fallback a verb
with no bespoke renderer gets. `_row` and `_when` are the small shared
helpers every renderer builds its lines from.

Reaches only `reticuli.kernel`'s pinned public surface (through the data
dicts the verbs themselves already built) and `reticuli.render`'s
formatting primitives -- never a `reticuli._kernel` private. Stdlib only.
"""
import calendar
import time

from reticuli import render as _render


def _row(label: str, value) -> str:
    """One `label: value` line; a missing value renders as `-`."""
    if value is None or value == "":
        value = "-"
    return f"{label}: {value}"


def _when(ts) -> str:
    """A recorded stamp (`_util.stamp`'s `YYYY-MM-DDTHH:MM:SSZ`), as how
    long ago it was -- the stamp itself verbatim if it cannot be parsed."""
    if not ts:
        return "-"
    try:
        parsed = time.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, TypeError):
        return str(ts)
    return _render.ago(calendar.timegm(parsed))


def _gate_lines(gates) -> list:
    lines = []
    for g in gates or []:
        quarantine = g.get("quarantine")
        suffix = f" ({quarantine})" if quarantine else ""
        lines.append(f"  gate {g.get('output')}: {g.get('status')}{suffix}")
    return lines


def _generic_contract(data) -> str:
    """The fallback report: every top-level key of `data`, as a `_row` --
    a verb with no bespoke renderer still prints something, never crashes."""
    if not isinstance(data, dict):
        return str(data)
    lines = []
    for key, value in data.items():
        if isinstance(value, (list, dict)):
            value = f"{len(value)} item(s)" if value else "none"
        lines.append(_row(key, value))
    return "\n".join(lines)


# -- identity and verdicts ----------------------------------------------------


def _r_verify(data: dict) -> str:
    lines = [_row("name", data.get("name")), _row("root", data.get("root"))]
    if data.get("ok"):
        lines.append(_row("status", "identity holds"))
    else:
        lines.append(_row("status", "identity broken"))
        lines.append(_row("recomputed", data.get("recomputed")))
        changed = data.get("changed")
        if changed:
            lines.append(_row("changed", ", ".join(changed)))
    return "\n".join(lines)


def _r_audit(data: dict) -> str:
    verdict = data.get("verdict") or ("accept" if data.get("ok") else "reject")
    lines = [_row("verdict", verdict)]
    if data.get("name"):
        lines.append(_row("name", data["name"]))
    if data.get("root"):
        lines.append(_row("root", data["root"]))
    missing = data.get("missing")
    if missing:
        lines.append(_row("missing", ", ".join(missing)))
    reason = data.get("reason")
    if reason:
        lines.append(_row("reason", reason))
    lines.extend(_gate_lines(data.get("gates")))
    return "\n".join(lines)


def _r_assess(data: dict) -> str:
    lines = [_row("mutants", data.get("mutants")), _row("rate", data.get("rate"))]
    for label, key in (("measured", "measured"), ("not measured", "not_measured"),
                        ("not applicable", "not_applicable")):
        outputs = data.get(key) or []
        if outputs:
            lines.append(_row(label, ", ".join(outputs)))
    return "\n".join(lines)


def _r_rebuild(data: dict) -> str:
    lines = [_row("name", data.get("name")), _row("root", data.get("root")),
              _row("quarantine", data.get("quarantine"))]
    lines.extend(_gate_lines(data.get("gates")))
    cost = data.get("cost") or {}
    if cost:
        lines.append(_row("cost", ", ".join(f"{k}={v}" for k, v in sorted(cost.items()))))
    return "\n".join(lines)


def _r_seal(data: dict) -> str:
    return "\n".join([_row("name", data.get("name")), _row("root", data.get("root"))])


def _r_crosscheck(data: dict) -> str:
    lines = [_row("verdict", data.get("verdict")), _row("satisfied", data.get("satisfied"))]
    for leg, root in (data.get("roots") or {}).items():
        lines.append(_row(leg, root))
    if data.get("rejected"):
        lines.append(_row("rejected", ", ".join(data["rejected"])))
    if data.get("incomplete"):
        lines.append(_row("incomplete", ", ".join(data["incomplete"])))
    if data.get("reuse") is not None:
        lines.append(_row("reuse", data["reuse"]))
    mscore = data.get("mutation_score")
    if mscore:
        lines.append(_row("mutation score", mscore.get("rate")))
    lines.append(_row("independence", data.get("independence")))
    return "\n".join(lines)


def _r_record(data: dict) -> str:
    lines = [_row("name", data.get("name")), _row("root", data.get("root")),
              _row("build_digest", data.get("build_digest")),
              _row("when", _when(data.get("when")))]
    lines.extend(_gate_lines(data.get("gates")))
    return "\n".join(lines)


# -- signing and the exchange layer --------------------------------------------


def _r_sign(data: dict) -> str:
    return "\n".join([_row("sign_root", data.get("sign_root")),
                        _row("statement", data.get("statement")),
                        _row("signature", data.get("signature"))])


def _r_sign_check(data: dict) -> str:
    lines = [_row("ok", data.get("ok"))]
    for row in data.get("authorizations") or []:
        lines.append(f"  {row.get('identity')}: {row.get('verdict')}"
                      f" (packet {'holds' if row.get('packet_holds') else 'drifted'})")
    return "\n".join(lines)


def _r_attest(data: dict) -> str:
    return "\n".join([_row("statement", data.get("statement")),
                        _row("signature", data.get("signature"))])


def _r_attest_check(data: dict) -> str:
    lines = [_row("ok", data.get("ok"))]
    for row in data.get("attestations") or []:
        lines.append(f"  {row.get('identity')}: {row.get('verdict')}")
    return "\n".join(lines)


def _r_review(data: dict) -> str:
    lines = [_row("root", data.get("root")), _row("sign_root", data.get("sign_root")),
              _row("build_digest", data.get("build_digest"))]
    audit = data.get("audit") or {}
    lines.append(_row("audit ok", audit.get("ok")))
    lines.extend(_gate_lines(audit.get("gates")))
    for layer in audit.get("layers") or []:
        lines.append(f"  layer {layer.get('name')}: {layer.get('status')}")
    lines.append(_row("proof", bool(data.get("proof"))))
    return "\n".join(lines)


def _r_pull(data: dict) -> str:
    return "\n".join([_row("materialized", data.get("materialized")),
                        _row("root", data.get("root"))])


def _r_export(data: dict) -> str:
    lines = [_row("path", data.get("path") or data.get("tar_path"))]
    if "blind" in data:
        lines.append(_row("blind", data["blind"]))
    return "\n".join(lines)


def _r_import(data: dict) -> str:
    return "\n".join([_row("ok", data.get("ok")), _row("root", data.get("root"))])


def _r_pack(data: dict) -> str:
    return "\n".join([_row("name", data.get("name")), _row("root", data.get("root"))])


def _r_hooks(data: dict) -> str:
    wired = data.get("wired") or []
    return "\n".join([_row("status", data.get("status")), _row("wired", ", ".join(wired))])


# -- init: the one verb whose terse view differs from its report --------------


def _r_init(data: dict) -> str:
    return "\n".join([_row("name", data.get("name")), _row("path", data.get("path"))])


def _t_init(data: dict) -> str:
    return f"initialized {data.get('name', '?')} at {data.get('path', '.')}"
