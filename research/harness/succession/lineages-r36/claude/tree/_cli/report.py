"""The explanatory accounts: what each action verb says under `-v`.

The default output is terse because the exit code is the answer. `-v` is for
the reader who wants to see the reasoning, so it spells hashes IN FULL --
an abbreviation is for scanning, never for comparing -- and lays the facts
out in labelled blocks that read like the recipe they came from.

Nothing here decides anything. A renderer that computed something would be
a second implementation of a verdict.
"""
from .. import render

TRUE = {True: "true", False: "false", None: "unknown"}


def _when(value) -> str:
    """A timestamp as a reader wants it: the stamp, and how long ago."""
    if not value:
        return "never"
    return f"{value} ({render.ago(value)})"


def _row(label: str, value) -> str:
    """One labelled fact, written the way the recipe writes one.

    No padding: `root = "<64 hex>"` is a shape a reader (and a grep) can
    rely on, and a column that lined the equals signs up would put a run of
    spaces where that shape should be.
    """
    if isinstance(value, bool) or value is None:
        shown = TRUE[value]
    elif isinstance(value, str):
        shown = f'"{value}"'
    elif isinstance(value, (list, tuple)):
        shown = "[" + ", ".join(str(v) for v in value) + "]"
    elif isinstance(value, dict):
        shown = "{ " + ", ".join(f"{k} = {v}" for k, v in
                                 sorted(value.items())) + " }"
    else:
        shown = str(value)
    return f"{label} = {shown}"


def _block(title: str, rows) -> str:
    lines = [f"[{title}]"]
    lines.extend(row for row in rows if row)
    return "\n".join(lines)


def _generic_contract(command: str, data) -> str:
    """The fallback account: whatever the verb returned, labelled."""
    if not isinstance(data, dict):
        return _block(command, [_row("result", data)])
    rows = []
    for key in sorted(data):
        value = data[key]
        if isinstance(value, (list, dict)) and len(str(value)) > 300:
            rows.append(_row(key, f"<{len(value)} entries>"))
        else:
            rows.append(_row(key, value))
    return _block(command, rows)


# -- verification ----------------------------------------------------------
def _r_verify(data) -> str:
    return _block("verify", [
        _row("name", data.get("name")),
        _row("root", data.get("root")),
        _row("recomputed", data.get("recomputed")),
        _row("ok", data.get("ok")),
        _row("phase", data.get("phase")),
        _row("changed", data.get("changed") or []) if data.get("changed")
        else None,
    ])


def _r_audit(data) -> str:
    parts = [_block("audit", [
        _row("name", data.get("name")),
        _row("root", data.get("root")),
        _row("recomputed", data.get("recomputed")),
        _row("verdict", data.get("verdict")),
        _row("ok", data.get("ok")),
        _row("elapsed", render.duration(data.get("elapsed"))),
        _row("environment", data.get("environment") or []),
    ])]
    rows = []
    for gate in data.get("gates") or []:
        note = "pinned bytes reproduced" if gate.get("status") == "ok" \
            else str(gate.get("detail") or "").strip().splitlines()[-1:] \
            and str(gate.get("detail") or "").strip().splitlines()[-1] \
            or gate.get("status")
        rows.append([gate.get("output"), gate.get("status"),
                     f'quarantine = "{gate.get("quarantine")}"', note])
    if rows:
        parts.append("[gates]\n" + render.table(rows))
    layers = data.get("layers") or []
    if layers:
        parts.append("[layers]\n" + render.table(
            [[r.get("name"), TRUE.get(r.get("ok"), r.get("ok")),
              r.get("status"), ", ".join(r.get("bytes_from") or [])]
             for r in layers]))
    score = data.get("mutation_score")
    if score:
        parts.append(_r_mutation(score))
    return "\n\n".join(parts)


def _r_mutation(score) -> str:
    return _block("mutation_score", [
        _row("mutants", score.get("mutants")),
        _row("killed", score.get("killed")),
        _row("rate", "unmeasured" if score.get("rate") is None
             else f"{score['rate']:.2f}"),
        _row("survivors", len(score.get("survivors") or [])),
        _row("floor", score.get("floor")) if score.get("floor") is not None
        else None,
    ])


def _r_assess(data) -> str:
    parts = [_block("assess", [
        _row("name", data.get("name")),
        _row("root", data.get("root")),
        _row("declared", sorted(data.get("declared") or {})),
    ])]
    for bucket in ("measured", "not_measured", "not_applicable"):
        lines = data.get(bucket) or []
        parts.append(f"[{bucket}]\n" +
                     ("\n".join(f"  {line}" for line in lines)
                      or "  (nothing)"))
    score = data.get("mutation_score")
    if score:
        parts.append(_r_mutation(score))
    return "\n\n".join(parts)


# -- reconstruction --------------------------------------------------------
def _r_rebuild(data) -> str:
    return _block("rebuild", [
        _row("name", data.get("name")),
        _row("root", data.get("root")),
        _row("quarantine", data.get("quarantine")),
        _row("calls", data.get("calls")),
        _row("rebuilt_components",
             [c.get("component") for c in data.get("rebuilt_components")
              or []]),
    ])


def _r_crosscheck(data) -> str:
    cost = data.get("cost") or {}
    parts = [_block("crosscheck", [
        _row("satisfied", data.get("satisfied")),
        _row("verdict", data.get("verdict")),
        _row("equivalence", data.get("equivalence")),
        _row("reuse", data.get("reuse")),
        _row("rejected", data.get("rejected") or []),
        _row("incomplete", data.get("incomplete") or []),
        _row("independence", data.get("independence")),
    ])]
    roots = data.get("roots") or {}
    parts.append("[roots]\n" + "\n".join(
        _row(name, roots[name]) for name in sorted(roots)))
    audited = data.get("audited") or {}
    parts.append("[audited]\n" + "\n".join(
        _row(name, audited[name]) for name in sorted(audited)))
    rows = [
        _row("comparable", cost.get("comparable")),
        _row("unit", cost.get("unit")),
        _row("ratio", None if cost.get("ratio") is None
             else round(cost["ratio"], 4)),
        _row("tolerance", cost.get("tolerance")),
        _row("declared_tolerance", cost.get("declared_tolerance")),
        _row("tightened", cost.get("tightened")),
        _row("c1", cost.get("c1")),
        _row("c3", cost.get("c3")),
    ]
    discovery = cost.get("discovery")
    if discovery:
        bill = ", ".join(f"{k} = {v}" for k, v in sorted(discovery.items()))
        rows.append(_row("discovery", f"{{ {bill} }} testimony, reported "
                                      f"beside the band and never inside it"))
    else:
        rows.append(_row("discovery", "none reported"))
    for unit, found in sorted((cost.get("envelope") or {}).items()):
        rows.append(_row(f"envelope {unit}",
                         f"ceiling {found.get('ceiling')}, paid "
                         f"{found.get('paid')}, within "
                         f"{TRUE.get(found.get('within'), 'unknown')}"))
    parts.append(_block("cost", rows))
    score = data.get("mutation_score")
    if score:
        parts.append(_r_mutation(score))
    composed = data.get("composed") or {}
    if any(composed.values()):
        parts.append("[composed]\n" + "\n".join(
            _row(name, (found or {}).get("ok"))
            for name, found in sorted(composed.items())))
    return "\n\n".join(parts)


# -- authoring -------------------------------------------------------------
def _t_init(data) -> str:
    """The terse line init prints: what was made, and whether an agent was
    wired by the same act."""
    where = data.get("path")
    agent = data.get("agent")
    tail = f", {agent} hooks wired" if agent else ""
    return f"initialized {where}{tail}"


def _r_init(data) -> str:
    return _block("init", [
        _row("path", data.get("path")),
        _row("store", data.get("store")),
        _row("gitignore", data.get("gitignore")),
        _row("agent", data.get("agent")),
        _row("wired", data.get("wired") or []),
    ])


def _r_pack(data) -> str:
    return _block("pack", [
        _row("name", data.get("name")),
        _row("root", data.get("root")),
        _row("format", data.get("format")),
        _row("generated", data.get("generated")),
        _row("inputs", data.get("inputs")),
        _row("component", data.get("component")),
        _row("verdicts", data.get("verdicts") or []),
    ])


def _r_seal(data) -> str:
    """The older spelling's account, kept because a root is a root."""
    return _block("seal", [
        _row("name", data.get("name")),
        _row("root", data.get("root")),
    ])


def _r_pull(data) -> str:
    return _block("pull", [
        _row("name", data.get("name")),
        _row("root", data.get("root")),
        _row("path", data.get("path")),
        _row("closure", data.get("closure") or []),
        _row("materialized", len(data.get("materialized") or [])),
    ])


def _r_hooks(data) -> str:
    return _block("hooks", [
        _row("status", data.get("status")),
        _row("wired", data.get("wired") or []),
        _row("settings", data.get("settings")),
    ])


# -- transport -------------------------------------------------------------
def _r_export(data) -> str:
    return _block("export", [
        _row("archive", data.get("archive")),
        _row("blind", data.get("blind")),
        _row("files", len(data.get("files") or [])),
    ])


def _r_import(data) -> str:
    return _block("import", [
        _row("name", data.get("name")),
        _row("root", data.get("root")),
        _row("recomputed", data.get("recomputed")),
        _row("ok", data.get("ok")),
        _row("path", data.get("path")),
    ])


# -- evidence --------------------------------------------------------------
def _r_record(data) -> str:
    doc = data.get("record") or {}
    return "\n\n".join([
        _block("record", [
            _row("digest", data.get("digest")),
            _row("path", data.get("path")),
            _row("signed", data.get("signed")),
            _row("signer", data.get("signer")),
        ]),
        _block("document", [
            _row("record", doc.get("record")),
            _row("name", doc.get("name")),
            _row("root", doc.get("root")),
            _row("build_digest", doc.get("build_digest")),
            _row("claim", doc.get("claim") or {}),
            _row("gates", [f"{g['output']}:{g['status']}"
                           for g in doc.get("gates") or []]),
            _row("cost", doc.get("cost") or {}),
            _row("when", doc.get("when")),
        ]),
    ])


def _r_attest(data) -> str:
    return _block("attest", [
        _row("identity", data.get("identity")),
        _row("root", data.get("root")),
        _row("statement", data.get("statement")),
        _row("signature", data.get("signature")),
    ])


def _r_attest_check(data) -> str:
    rows = [[r.get("statement"), r.get("identity"), r.get("verdict"),
             f"drifted = {TRUE.get(r.get('drifted'), r.get('drifted'))}"]
            for r in data.get("attestations") or []]
    return "\n\n".join([
        _block("attestations", [
            _row("ok", data.get("ok")),
            _row("anchored", data.get("anchored")),
            _row("root", data.get("root")),
        ]),
        render.table(rows) if rows else "(no attestations)",
    ])


def _r_review(data) -> str:
    audit = data.get("audit") or {}
    return _block("review", [
        _row("name", data.get("name")),
        _row("root", data.get("root")),
        _row("build_digest", data.get("build_digest")),
        _row("sign_root", data.get("sign_root")),
        _row("composed", data.get("composed")),
        _row("audit", audit.get("verdict")),
        _row("audit ok", audit.get("ok")),
        _row("proof", "recorded" if data.get("proof") else "none"),
        _row("when", data.get("when")),
    ])


def _r_sign(data) -> str:
    return _block("sign", [
        _row("ceremony", data.get("ceremony")),
        _row("identity", data.get("identity")),
        _row("root", data.get("root")),
        _row("sign_root", data.get("sign_root")),
        _row("statement", data.get("statement")),
        _row("packet", data.get("packet")),
        _row("signature", data.get("signature")),
    ])


def _r_sign_check(data) -> str:
    rows = [[r.get("statement"), r.get("identity"), r.get("verdict"),
             f"packet_holds = {TRUE.get(r.get('packet_holds'), '?')}",
             f"proof_recorded = {TRUE.get(r.get('proof_recorded'), '?')}"]
            for r in data.get("authorizations") or []]
    return "\n\n".join([
        _block("authorizations", [
            _row("ok", data.get("ok")),
            _row("anchored", data.get("anchored")),
            _row("sign_root", data.get("sign_root")),
        ]),
        render.table(rows) if rows else "(no authorizations)",
    ])
