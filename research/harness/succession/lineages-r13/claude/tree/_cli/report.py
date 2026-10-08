"""The action-verb renderers: the `-v` detail block each verb's result
expands into (spec/layers.md's surface layer). Every `_r_<verb>` here takes
exactly the dict its lower-layer call already returned -- `kernel.verify`,
`attest.sign`, `transfer.export`, and so on -- and turns it into the lines a
human reads with `-v`; none of them fetch anything themselves, so none of
them import `reticuli.kernel`. `_generic_contract` is the fallback for a verb
with no renderer of its own: every verb's result is at minimum a plain dict,
and that alone is enough to show a row per field.

`_row` and `_when` are the two helpers every renderer below is built from: a
single "label: value" line, and a human "<n> <unit> ago" rendering of a
timestamp -- either a ledger event's raw UNIX `ts` or a record/attestation's
ISO `when` stamp (`_util.stamp`'s own format).
"""
import calendar
import time

from .. import render


def _row(label: str, value) -> str:
    """One "label: value" line of a verbose render block."""
    return f"{label}: {value}"


def _when(ts) -> str:
    """A human "<n> <unit> ago" rendering of `ts` -- a float UNIX timestamp
    (as the ledger stores) or the ISO `YYYY-MM-DDTHH:MM:SSZ` stamp
    (`_util.stamp`) a record or attestation carries as `when`."""
    if isinstance(ts, str):
        try:
            parsed = time.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            return ts
        ts = calendar.timegm(parsed)
    if isinstance(ts, bool) or not isinstance(ts, (int, float)):
        return str(ts)
    return render.ago(float(ts))


def _generic_contract(verb: str, data: dict) -> str:
    """The fallback render for a verb with no renderer of its own: a plain
    row per field of its result, shown the same way regardless of which
    verb produced it."""
    data = data or {}
    lines = [f"{verb}:"]
    for key in sorted(data):
        lines.append("  " + _row(key, data[key]))
    return "\n".join(lines)


def _r_verify(result: dict) -> str:
    """`kernel.verify`'s result: the sealed root against what the bytes
    present recompute to."""
    lines = ["verify:",
              "  " + _row("ok", result.get("ok")),
              "  " + _row("root", render.short(result.get("root") or "", 16)),
              "  " + _row("recomputed", render.short(result.get("recomputed") or "", 16))]
    return "\n".join(lines)


def _r_audit(result: dict) -> str:
    """`kernel.audit`'s result: the verdict, and each gate's own status."""
    lines = ["audit:",
              "  " + _row("verdict", result.get("verdict")),
              "  " + _row("root", render.short(result.get("root") or "", 16))]
    for g in result.get("gates") or []:
        lines.append(f"    {g.get('output')}: {g.get('status')} (quarantine={g.get('quarantine')})")
    missing = result.get("environment") or []
    if missing:
        lines.append("  " + _row("environment missing", ", ".join(missing)))
    return "\n".join(lines)


def _r_assess(result: dict) -> str:
    """`assess.assess`'s result: a mutation-testing budget bucketed into
    what the tests actually proved."""
    lines = ["assess:"]
    for key in ("mutants", "rate", "measured", "not_measured", "not_applicable"):
        if key in result:
            lines.append("  " + _row(key, result[key]))
    return "\n".join(lines)


def _r_rebuild(result: dict) -> str:
    """`kernel.rebuild`'s result: the regrown root, and each gate it
    re-earned on the way there."""
    lines = ["rebuild:",
              "  " + _row("root", render.short(result.get("root") or "", 16)),
              "  " + _row("status", result.get("status")),
              "  " + _row("quarantine", result.get("quarantine"))]
    for g in result.get("gates") or []:
        lines.append(f"    {g.get('output')}: {g.get('status')}")
    return "\n".join(lines)


def _r_seal(manifest: dict) -> str:
    """`kernel.seal`'s manifest: the name and root a workspace just froze
    into."""
    parts = manifest.get("parts") or {}
    lines = ["seal:",
              "  " + _row("name", manifest.get("name")),
              "  " + _row("root", render.short(manifest.get("root") or "", 16)),
              "  " + _row("parts", len(parts))]
    return "\n".join(lines)


def _r_crosscheck(result: dict) -> str:
    """`kernel.crosscheck`'s result: the three-machine verdict, one root
    per leg, and whatever it rejected or could not decide."""
    lines = ["crosscheck:", "  " + _row("verdict", result.get("verdict"))]
    for leg in sorted(result.get("roots") or {}):
        lines.append(f"    {leg}: {render.short(result['roots'][leg] or '', 16)}")
    lines.append("  " + _row("equivalence", result.get("equivalence")))
    lines.append("  " + _row("reuse", result.get("reuse")))
    rejected = result.get("rejected") or []
    if rejected:
        lines.append("  " + _row("rejected", ", ".join(rejected)))
    incomplete = result.get("incomplete") or []
    if incomplete:
        lines.append("  " + _row("incomplete", ", ".join(incomplete)))
    return "\n".join(lines)


def _r_record(doc: dict) -> str:
    """`record.emit`'s version-2 record: name, root, when it was earned,
    and each gate's sandboxed status."""
    lines = ["record:",
              "  " + _row("name", doc.get("name")),
              "  " + _row("root", render.short(doc.get("root") or "", 16)),
              "  " + _row("when", _when(doc.get("when")))]
    for g in doc.get("gates") or []:
        lines.append(f"    {g.get('output')}: {g.get('status')} (sandbox={g.get('sandbox')})")
    return "\n".join(lines)


def _r_sign(result: dict) -> str:
    """`attest.sign`'s ceremony result: the chain root signed, and where
    the statement and packet landed."""
    lines = ["sign:",
              "  " + _row("root", render.short(result.get("root") or "", 16)),
              "  " + _row("sign_root", render.short(result.get("sign_root") or "", 16)),
              "  " + _row("statement", result.get("statement")),
              "  " + _row("signature", result.get("signature"))]
    return "\n".join(lines)


def _r_export(result: dict) -> str:
    """`transfer.export`'s result."""
    return "export:\n  " + _row("ok", result.get("ok"))


def _r_pack(result: dict) -> str:
    """`pack.pack`'s result: the root a project directory just became."""
    lines = ["pack:",
              "  " + _row("ok", result.get("ok")),
              "  " + _row("root", render.short(result.get("root") or "", 16))]
    return "\n".join(lines)


def _r_attest(result: dict) -> str:
    """`attest.attest`'s result: the cold-audited build a keyholder just
    signed."""
    lines = ["attest:",
              "  " + _row("root", render.short(result.get("root") or "", 16)),
              "  " + _row("build_digest", render.short(result.get("build_digest") or "", 16)),
              "  " + _row("statement", result.get("statement"))]
    return "\n".join(lines)


def _r_attest_check(result: dict) -> str:
    """`attest.check`'s result: whether each stored attestation still names
    the current build."""
    lines = ["attest check:", "  " + _row("ok", result.get("ok"))]
    for a in result.get("attestations") or []:
        lines.append(f"    {a.get('statement')}: {a.get('verdict')} (principal={a.get('principal')})")
    return "\n".join(lines)


def _r_sign_check(result: dict) -> str:
    """`attest.sign_check`'s result: the ceremony's own paperwork."""
    lines = ["sign check:", "  " + _row("ok", result.get("ok"))]
    for a in result.get("authorizations") or []:
        lines.append(f"    {a.get('statement')}: {a.get('verdict')} (packet_holds={a.get('packet_holds')})")
    return "\n".join(lines)


def _r_hooks(result: dict) -> str:
    """`hooks.install`'s result: whether the agent handshake got wired."""
    lines = ["hooks:", "  " + _row("status", result.get("status"))]
    wired = result.get("wired") or []
    if wired:
        lines.append("  " + _row("wired", ", ".join(wired)))
    return "\n".join(lines)


def _r_import(result: dict) -> str:
    """`transfer.import_`'s result: the root recomputed from received
    bytes."""
    lines = ["import:",
              "  " + _row("ok", result.get("ok")),
              "  " + _row("root", render.short(result.get("root") or "", 16))]
    return "\n".join(lines)


def _r_init(result: dict) -> str:
    """A freshly scaffolded claim's own name and where it landed."""
    lines = ["init:",
              "  " + _row("name", result.get("name")),
              "  " + _row("path", result.get("path"))]
    return "\n".join(lines)


def _t_init(result: dict) -> str:
    """`init`'s terse one-line form."""
    return f"init: {result.get('name')} ({result.get('path')})"


def _r_pull(result: dict) -> str:
    """`registry.pull`'s result: a dependency materialized into a
    workspace."""
    lines = ["pull:",
              "  " + _row("materialized", result.get("materialized")),
              "  " + _row("root", render.short(result.get("root") or "", 16))]
    return "\n".join(lines)


def _r_review(result: dict) -> str:
    """`attest.review_packet`'s result: what a keyholder sees before
    signing."""
    audit = result.get("audit") or {}
    lines = ["review:",
              "  " + _row("root", render.short(result.get("root") or "", 16)),
              "  " + _row("sign_root", render.short(result.get("sign_root") or "", 16)),
              "  " + _row("audit", f"{audit.get('verdict')} (ok={audit.get('ok')})"),
              "  " + _row("proof", bool(result.get("proof")))]
    return "\n".join(lines)
