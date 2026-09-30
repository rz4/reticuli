"""reticuli._cli.report: the action-verb renderers (spec/layers.md, surface layer).

Every `_r_<verb>` below turns one already-computed result dict -- from
`kernel`, `registry`, `attest`, `transfer`, `pack`, `hooks`, `record`, or
`authoring` -- into the lines a command's `--verbose` report prints. A
renderer never re-earns a verdict; it only reads what the layer beneath
already decided. `_generic_contract` is the one piece every verb without a
bespoke status word falls back to: the plain `ok` -> `"ok"`/`"failed"`
reading `output._finish`'s envelope already gives a script, restated here
as the first line of a person's report too, so a newly wired verb never
renders as nothing. `_row`/`_when` are the two shared primitives every
renderer below assembles its body from.
"""
from reticuli import render


def _row(label: str, value) -> str:
    """One indented `label: value` line -- the shape every renderer below
    assembles its body from, so a reader's eye lands in the same column
    no matter which verb produced the line."""
    return f"  {label}: {value}"


def _when(stamp) -> str:
    """A recording's `when` (spec/record.md's `YYYY-MM-DDTHH:MM:SSZ`),
    unchanged -- a signed timestamp is evidence, and a renderer must show
    what was actually signed, never a relative guess that goes stale the
    moment the report is re-read."""
    return stamp if stamp else "unknown"


def _generic_contract(result: dict) -> tuple:
    """The `(ok, status)` pair every plain `{"ok": ...}` result carries --
    the fallback status word for any verb whose report has no bespoke
    vocabulary of its own (`crosscheck`'s `verdict`, `audit`'s per-gate
    classes), so a report is never left without a status line."""
    ok = bool(result.get("ok", True))
    return ok, ("ok" if ok else "failed")


# ---------------------------------------------------------------------------
# kernel-layer verbs
# ---------------------------------------------------------------------------

def _r_verify(result: dict) -> list:
    ok, status = _generic_contract(result)
    lines = [f"verify: {status}",
             _row("name", result.get("name")),
             _row("root", render.short(result.get("root") or ""))]
    if not ok:
        lines.append(_row("recomputed", render.short(result.get("recomputed") or "")))
    return lines


def _r_audit(result: dict) -> list:
    ok, status = _generic_contract(result)
    lines = [f"audit: {status}",
             _row("name", result.get("name")),
             _row("root", render.short(result.get("root") or ""))]
    for reason in result.get("environment") or []:
        lines.append(_row("environment", reason))
    for gate in result.get("gates", []):
        lines.append(_row(f"gate {gate['output']}", gate["status"]))
    for name, sub in (result.get("components") or {}).items():
        lines.append(_row(f"component {name}", "ok" if sub["ok"] else "failed"))
    return lines


def _r_assess(result: dict) -> list:
    score = result.get("mutation_score") or {}
    lines = [_row("mutants killed", f"{score.get('killed', 0)}/{score.get('mutants', 0)}"),
             _row("measured", ", ".join(result.get("measured", [])) or "none"),
             _row("not measured", ", ".join(result.get("not_measured", [])) or "none"),
             _row("not applicable", ", ".join(result.get("not_applicable", [])) or "none")]
    return lines


def _r_rebuild(result: dict) -> list:
    lines = ["rebuild: ok",
             _row("name", result.get("name")),
             _row("root", render.short(result.get("root") or ""))]
    for comp in result.get("rebuilt_components", []):
        lines.append(_row(f"component {comp['component']}", render.short(comp["root"])))
    return lines


def _r_seal(result: dict) -> list:
    return ["seal: ok",
            _row("name", result.get("name")),
            _row("root", render.short(result.get("root") or ""))]


def _r_crosscheck(result: dict) -> list:
    lines = [f"crosscheck: {result.get('verdict', 'incomplete')}"]
    for leg in ("M1", "M2", "M3"):
        root = (result.get("roots") or {}).get(leg)
        if root:
            lines.append(_row(leg, render.short(root)))
    lines.append(_row("equivalence", result.get("equivalence")))
    lines.append(_row("reuse", result.get("reuse")))
    if result.get("rejected"):
        lines.append(_row("rejected", ", ".join(result["rejected"])))
    if result.get("incomplete"):
        lines.append(_row("incomplete", ", ".join(result["incomplete"])))
    lines.append(_row("independence", result.get("independence")))
    return lines


# ---------------------------------------------------------------------------
# exchange-layer verbs
# ---------------------------------------------------------------------------

def _r_export(result: dict) -> list:
    lines = ["export: ok", _row("path", result.get("path"))]
    for member in result.get("members", []):
        lines.append(_row("member", member))
    return lines


def _r_import(result: dict) -> list:
    ok, status = _generic_contract(result)
    return [f"import: {status}",
            _row("name", result.get("name")),
            _row("root", render.short(result.get("root") or ""))]


def _r_pull(result: dict) -> list:
    return ["pull: ok",
            _row("name", result.get("name")),
            _row("root", render.short(result.get("root") or ""))]


def _r_attest(result: dict) -> list:
    return ["attest: ok",
            _row("statement", result.get("statement")),
            _row("signature", result.get("signature"))]


def _r_attest_check(result: dict) -> list:
    ok, status = _generic_contract(result)
    lines = [f"attest-check: {status}"]
    for a in result.get("attestations", []):
        lines.append(_row(a["identity"], a["verdict"]))
    return lines


def _r_sign(result: dict) -> list:
    return ["sign: ok",
            _row("ceremony", result.get("ceremony")),
            _row("statement", result.get("statement")),
            _row("packet", result.get("packet"))]


def _r_sign_check(result: dict) -> list:
    ok, status = _generic_contract(result)
    lines = [f"sign-check: {status}"]
    for a in result.get("authorizations", []):
        lines.append(_row(a["identity"], a["verdict"]))
    return lines


def _r_review(result: dict) -> list:
    audit_result = result.get("audit") or {}
    return ["review packet:",
            _row("root", render.short(result.get("root") or "")),
            _row("build_digest", render.short(result.get("build_digest") or "")),
            _row("sign_root", render.short(result.get("sign_root") or "")),
            _row("audit", "ok" if audit_result.get("ok") else "failed"),
            _row("proof recorded", bool(result.get("proof")))]


# ---------------------------------------------------------------------------
# authoring / agent-layer verbs
# ---------------------------------------------------------------------------

def _r_record(doc: dict) -> list:
    lines = [f"record: format {doc.get('record')}",
             _row("name", doc.get("name")),
             _row("root", render.short(doc.get("root") or "")),
             _row("when", _when(doc.get("when")))]
    for gate in doc.get("gates", []):
        lines.append(_row(f"gate {gate['output']}", f"{gate['status']} ({gate['sandbox']})"))
    if "cost" in doc:
        lines.append(_row("cost", doc["cost"]))
    return lines


def _r_pack(result: dict) -> list:
    return ["pack: ok",
            _row("name", result.get("name")),
            _row("root", render.short(result.get("root") or ""))]


def _r_hooks(result: dict) -> list:
    lines = [f"hooks: {result.get('status')}"]
    for name in result.get("wired", []):
        lines.append(_row("wired", name))
    return lines


def _r_init(result: dict) -> list:
    ok, status = _generic_contract(result)
    lines = [f"init: {status}"]
    for key in ("name", "path"):
        if key in result:
            lines.append(_row(key, result[key]))
    return lines


def _t_init(result: dict) -> str:
    """The terse form of `_r_init`: one line, for a script's own log."""
    ok, status = _generic_contract(result)
    label = result.get("name") or result.get("path") or ""
    return f"init: {status} ({label})"
