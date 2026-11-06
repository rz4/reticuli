"""The action-verb renderers.

Two registers. TERSE prints only the unknowable -- the root a rebuild landed
on, the name a pack minted -- and says nothing at all when the answer is just
"it held", because the exit code already said that. EXPLANATORY (-v) prints
the account a reader weighs, hashes in full, one `[section]` per topic.
"""
import os

from .. import render
from .._util import read_json
from .output import _line, _rel


def _when(moment) -> str:
    """A timestamp as a reader reads it, with the raw value kept beside it."""
    if not moment:
        return "never"
    return f"{moment} ({render.ago(moment)})"


def _row(label: str, value, width: int = 0) -> str:
    """One `label = value` line of a -v block.

    One space either side of the `=`, always: a reader greps these lines, and
    a hash spelled in full is only findable if the spelling is stable.
    """
    if isinstance(value, bool):
        shown = "true" if value else "false"
    elif value is None:
        shown = "none"
    elif isinstance(value, (list, tuple)):
        shown = ", ".join(str(v) for v in value) or "none"
    elif isinstance(value, str) and len(value) == 64 and \
            all(c in "0123456789abcdef" for c in value):
        shown = f'"{value}"'
    else:
        shown = str(value)
    return f"  {label} = {shown}"


def _generic_contract(command: str, data: dict) -> None:
    """The fallback account: a block, its fields, nothing invented."""
    _line(f"[{command}]")
    for key in sorted(data or {}):
        value = data[key]
        if isinstance(value, (dict, list)) and key not in ("gates", "layers"):
            continue
        _line(_row(key, value))


# --------------------------------------------------------------------------
# verification

def _r_verify(result: dict, args) -> None:
    _line("[verify]")
    _line(_row("name", result.get("name")))
    _line(_row("root", result.get("root")))
    _line(_row("recomputed", result.get("recomputed")))
    _line(_row("phase", result.get("phase")))
    _line(_row("ok", result.get("ok")))
    if result.get("changed"):
        _line(_row("moved", result["changed"]))


def _r_audit(result: dict, args) -> None:
    _line("[audit]")
    _line(_row("name", result.get("name")))
    _line(_row("root", result.get("root")))
    _line(_row("verdict", result.get("verdict")))
    _line(_row("elapsed", render.duration(result.get("elapsed"))))
    _line(_row("environment", result.get("environment") or "complete"))
    rows = []
    for gate in result.get("gates") or []:
        rows.append([gate.get("output"), gate.get("status"),
                     "reproduced" if gate.get("status") == "ok" else "no",
                     gate.get("quarantine") or "none"])
    if rows:
        _line(render.table(rows, ["gate", "status", "pinned bytes",
                                  "quarantine"]))
    for layer in result.get("layers") or []:
        _line(_row(f"layer {layer.get('name')}", layer.get("status")))
    score = result.get("mutation_score")
    if score:
        _line("[mutation_score]")
        _line(_row("mutants", score.get("mutants")))
        _line(_row("killed", score.get("killed")))
        _line(_row("rate", score.get("rate")))
        _line(_row("survivors", score.get("survivors") or "none"))


def _r_assess(result: dict, args) -> None:
    _line("[assess]")
    _line(_row("name", result.get("name")))
    _line(_row("root", result.get("root")))
    _line(_row("measured", result.get("measured") or "none"))
    _line(_row("not_measured", result.get("not_measured") or "none"))
    _line(_row("not_applicable", result.get("not_applicable") or "none"))
    _line(_row("declared", result.get("declared") or "none"))
    _line(_row("mutation_floor", result.get("mutation_floor")))
    score = result.get("mutation_score")
    if score:
        _line("[mutation_score]")
        _line(_row("mutants", score.get("mutants")))
        _line(_row("rate", score.get("rate")))
        _line(_row("survivors", score.get("survivors") or "none"))


def _r_crosscheck(result: dict, args) -> None:
    _line("[crosscheck]")
    _line(_row("verdict", result.get("verdict")))
    _line(_row("satisfied", result.get("satisfied")))
    for machine in ("M1", "M2", "M3"):
        _line(_row(f"root {machine}", (result.get("roots") or {}).get(machine)))
    _line(_row("equivalence", result.get("equivalence")))
    _line(_row("reuse", result.get("reuse")))
    _line(_row("audited", [f"{k}={v}" for k, v in
                           sorted((result.get("audited") or {}).items())]))
    _line(_row("independence", result.get("independence")))
    if result.get("rejected"):
        _line(_row("rejected", result["rejected"]))
    if result.get("incomplete"):
        _line(_row("incomplete", result["incomplete"]))
    cost = result.get("cost") or {}
    _line("[cost]")
    _line(_row("unit", cost.get("unit")))
    _line(_row("ratio", cost.get("ratio")))
    _line(_row("comparable", cost.get("comparable")))
    _line(_row("tolerance", cost.get("tolerance")))
    _line(_row("declared", cost.get("declared_tolerance")))
    _line(_row("M1", _units(cost.get("m1"))))
    _line(_row("M3", _units(cost.get("m3"))))
    _line(_row("discovery", _units(cost.get("discovery"))))
    for unit, bound in sorted((cost.get("envelope") or {}).items()):
        _line(_row(f"envelope {unit}",
                   f"{bound.get('measured')} of {bound.get('ceiling')} "
                   f"(within={bound.get('within')})"))
    score = result.get("mutation_score")
    if score:
        _line("[mutation_score]")
        _line(_row("rate", score.get("rate")))
        _line(_row("floor", score.get("floor")))
        _line(_row("ok", score.get("ok")))


def _units(totals) -> str:
    if not totals:
        return "unmeasured"
    return ", ".join(f"{unit} {value}" for unit, value in sorted(
        totals.items()))


# --------------------------------------------------------------------------
# reconstruction and authoring

def _r_rebuild(result: dict, args) -> None:
    _line("[rebuild]")
    _line(_row("root", result.get("root")))
    _line(_row("into", _rel(result.get("into"))))
    _line(_row("calls", result.get("calls")))
    _line(_row("quarantine", result.get("quarantine")))
    for component in result.get("rebuilt_components") or []:
        _line(_row(f"component {component.get('component')}",
                   component.get("root")))


def _r_pack(result: dict, args) -> None:
    _line("[pack]")
    _line(_row("name", result.get("name")))
    _line(_row("root", result.get("root")))
    _line(_row("generated", result.get("generated")))
    _line(_row("inputs", result.get("inputs")))
    _line(_row("component", result.get("component")))


def _r_seal(result: dict, args) -> None:
    """`seal` was folded into pack; the renderer stays for older callers."""
    _r_pack(result, args)


def _t_init(result: dict) -> None:
    _line(f"initialized {_rel(result.get('workspace'))}")


def _r_init(result: dict, args) -> None:
    _line("[init]")
    _line(_row("workspace", _rel(result.get("workspace"))))
    _line(_row("agent", result.get("agent") or "none"))
    _line(_row("wired", result.get("wired") or "none"))


def _r_pull(result: dict, args) -> None:
    _line("[pull]")
    _line(_row("pulled", result.get("pulled")))
    _line(_row("root", result.get("root")))
    _line(_row("closure", result.get("closure") or "none"))
    _line(_row("materialized", result.get("materialized") or "none"))


def _r_export(result: dict, args) -> None:
    _line("[export]")
    _line(_row("path", _rel(result.get("path"))))
    _line(_row("members", result.get("members")))
    _line(_row("blind", result.get("blind")))


def _r_import(result: dict, args) -> None:
    _line("[import]")
    _line(_row("path", _rel(result.get("path"))))
    _line(_row("name", result.get("name")))
    _line(_row("root", result.get("root")))
    _line(_row("ok", result.get("ok")))


# --------------------------------------------------------------------------
# evidence

def _r_record(result: dict, args) -> None:
    document = result.get("record") or {}
    _line("[record]")
    _line(_row("name", document.get("name")))
    _line(_row("root", document.get("root")))
    _line(_row("build_digest", document.get("build_digest")))
    _line(_row("digest", result.get("digest")))
    _line(_row("written", _rel(result.get("path"))))
    _line(_row("signed", result.get("signature") and
               _rel(result["signature"])))
    rows = [[g.get("output"), g.get("status"), g.get("sandbox")]
            for g in document.get("gates") or []]
    if rows:
        _line(render.table(rows, ["gate", "status", "sandbox"]))


def _r_attest(result: dict, args) -> None:
    _line("[attest]")
    _line(_row("identity", result.get("identity")))
    _line(_row("root", result.get("root")))
    _line(_row("build_digest", result.get("build_digest")))
    _line(_row("statement", _rel(result.get("statement"))))


def _r_attest_check(result: dict, args) -> None:
    _line("[attest --check]")
    _line(_row("ok", result.get("ok")))
    _line(_row("anchored", result.get("anchored")))
    rows = [[row.get("identity"), row.get("verdict"),
             "drifted" if row.get("drifted") else "frozen",
             "this root" if row.get("names_this_root") else "another root"]
            for row in result.get("attestations") or []]
    if rows:
        _line(render.table(rows, ["signer", "verdict", "bytes", "names"]))


def _r_review(result: dict, args) -> None:
    _line("[review]")
    _line(_row("name", result.get("name")))
    _line(_row("root", result.get("root")))
    _line(_row("build_digest", result.get("build_digest")))
    _line(_row("sign_root", result.get("sign_root")))
    _line(_row("audit", (result.get("audit") or {}).get("ok")))
    _line(_row("proof", bool(result.get("proof"))))
    _line(_row("composed", result.get("composed") or "none"))


def _r_sign(result: dict, args) -> None:
    _line("[sign]")
    _line(_row("ceremony", result.get("ceremony")))
    _line(_row("identity", result.get("identity")))
    _line(_row("root", result.get("root")))
    _line(_row("sign_root", result.get("sign_root")))
    _line(_row("statement", _rel(result.get("statement"))))
    _line(_row("proof_recorded", result.get("proof_recorded")))


def _r_sign_check(result: dict, args) -> None:
    _line("[sign --check]")
    _line(_row("ok", result.get("ok")))
    _line(_row("anchored", result.get("anchored")))
    rows = [[row.get("identity"), row.get("verdict"),
             row.get("packet_holds"), row.get("proof_recorded"),
             "drifted" if row.get("drifted") else "frozen"]
            for row in result.get("authorizations") or []]
    if rows:
        _line(render.table(rows, ["signer", "verdict", "packet", "proof",
                                  "bytes"]))


def _r_hooks(result: dict, args) -> None:
    _line("[hooks]")
    _line(_row("status", result.get("status")))
    _line(_row("wired", result.get("wired") or "none"))
    _line(_row("settings", _rel(result.get("settings"))))
