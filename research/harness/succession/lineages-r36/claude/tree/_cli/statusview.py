"""The status family: the draft, the claim, the ledger, the tree.

Status is the ONE VIEW, and a view reads. It reports what other verbs
earned, dates it, names whose machine earned it, and ends by naming the
first rung on the ladder this claim has not reached. Nothing here executes
a gate, so every form is instant and no form can change a verdict.

COLOUR IS THE SECOND CHANNEL, NEVER THE ONLY ONE. In the tree, a file's
class is spelled as a word when colour is off and carried by the colour
when it is on -- so information never lives only in a hue, and never says
itself twice.
"""
import os

from .. import render

#: what a step class MEANS to a reader -- the word the file list prints
_DECLARED_ROLE = {"generated": "free", "pinned": "fixed",
                  "validated": "verdict", "carried": "shipped"}
_CLASS_COLOR = {"generated": "cyan", "pinned": "yellow",
                "validated": "green", "carried": "magenta"}
_IDENTITY_COLOR = {"fresh": "green", "broken": "red", "unknown": "yellow"}


def _colored() -> bool:
    return render.paint("x", "green") != "x"


def _cost_words(totals) -> str:
    if not totals:
        return "nothing measured"
    return ", ".join(f"{v} {k}" for k, v in sorted(totals.items())
                     if k != "discovery")


# -- the claim lens --------------------------------------------------------
def _t_status_claim(view: dict) -> str:
    """The terse account of a sealed claim: state, evidence, and next."""
    lines = []
    identity = view.get("identity") or "unknown"
    lines.append(_pair("identity", render.paint(
        identity, _IDENTITY_COLOR.get(identity)) + "    "
        + render.short(view.get("recomputed"))))
    receipt = view.get("audited") or {}
    if receipt.get("when"):
        lines.append(_pair("audited", f"{receipt.get('verdict')}, "
                                      f"{render.ago(receipt['when'])}, "
                                      f"on this machine"))
    else:
        lines.append(_pair("audited", "never on this machine"))
    deciding = view.get("deciding") or []
    lines.append(_pair("deciding", deciding[0] if deciding
                       else "strength unknown: the tests are unmeasured"))
    discovery = view.get("discovery")
    if discovery:
        lines.append(_pair("discovery", ", ".join(
            f"{v} {k}" for k, v in sorted(discovery.items()))
            + "   (testimony, outside the cost band)"))
    lines.append(_pair("proof", "recorded crosscheck" if view.get("proof")
                       else "none"))
    statements = view.get("signatures") or {}
    count = statements.get("count") or 0
    who = ", ".join(statements.get("identities") or []) or "nobody"
    lines.append(_pair("signed", f"{count} statement(s) by {who}; phase "
                                 f"{view.get('phase')}"))
    if view.get("changed"):
        lines.append(_pair("moved", ", ".join(view["changed"])))
    lines.append(_pair("next", view.get("next")))
    return "\n".join(lines)


def _pair(label: str, value) -> str:
    return f"{label.ljust(11)} {value}"


def _v_status_claim(view: dict) -> str:
    """The explanatory account: the same facts, spelled out in full."""
    from . import report
    lines = [report._block("status", [
        report._row("name", view.get("name")),
        report._row("root", view.get("root")),
        report._row("recomputed", view.get("recomputed")),
        report._row("identity", view.get("identity")),
        report._row("phase", view.get("phase")),
        report._row("declared", sorted(view.get("declared") or {})),
        report._row("components",
                    [c.get("component") for c in
                     view.get("components") or []]),
    ])]
    receipt = view.get("audited") or {}
    lines.append(report._block("audited", [
        report._row("when", report._when(receipt.get("when"))),
        report._row("verdict", receipt.get("verdict")),
        report._row("ok", receipt.get("ok")),
    ]))
    lines.append(report._block("cost", [
        report._row("totals", _cost_words(view.get("cost"))),
        report._row("discovery", view.get("discovery") or {}),
    ]))
    lines.append(report._block("next", [
        report._row("next", view.get("next")),
    ]))
    return "\n\n".join(lines)


def _ledger_status_claim(view: dict) -> str:
    """The full account, grouped by what each fact IS.

    FIXED is what the root holds down. DECIDING is what a measurement
    showed about the criteria. FREE is the equivalence class. RECORDED is
    testimony -- dated, and named as testimony, because a receipt is not a
    verdict. UNKNOWN is what nothing here has established.
    """
    files = view.get("files") or []
    groups = {"fixed": [], "free": [], "verdict": [], "shipped": []}
    for entry in files:
        groups.setdefault(entry.get("role"), []).append(entry.get("path"))
    lines = []
    lines.append("fixed       what this root holds down: "
                 + (", ".join(groups.get("fixed") or []) or "nothing")
                 + " | verdicts: "
                 + (", ".join(groups.get("verdict") or []) or "none"))
    deciding = view.get("deciding") or []
    if deciding:
        lines.append("deciding    " + "; ".join(deciding))
    else:
        lines.append("deciding    strength unknown: no measurement applies "
                     "to this root")
    lines.append("free        the equivalence class: "
                 + (", ".join(groups.get("free") or []) or "nothing")
                 + (" | shipped: " + ", ".join(groups["shipped"])
                    if groups.get("shipped") else ""))
    receipt = view.get("audited") or {}
    recorded = []
    if receipt.get("when"):
        recorded.append(f"audit, {receipt['when']}, {receipt.get('verdict')}")
    measured = view.get("measured") or {}
    if measured.get("when"):
        recorded.append(f"assess, {measured['when']}")
    if view.get("proof"):
        recorded.append("crosscheck, recorded as a proof on this manifest")
    for statement in (view.get("signatures") or {}).get("statements") or []:
        recorded.append(f"{statement['kind']}, {statement.get('when')}, "
                        f"{statement.get('identity')}")
    lines.append("recorded    " + ("; ".join(recorded) or "nothing")
                 + "   -- a receipt, not a verdict: only re-running the "
                   "gates earns one")
    unknown = []
    if not measured:
        unknown.append("what the tests prove (nothing measured this root)")
    if not view.get("proof"):
        unknown.append("independent reproduction (no recorded proof)")
    if view.get("phase") != "signed":
        unknown.append("a keyholder's endorsement")
    lines.append("unknown     " + ("; ".join(unknown) or "nothing"))
    lines.append("next        " + str(view.get("next")))
    return "\n".join(lines)


def _files_claim(view: dict) -> str:
    """Every declared file, by class and role. Hiding none: a file a reader
    cannot see is a file nobody checks the class of."""
    rows = []
    for entry in view.get("files") or []:
        rows.append([entry.get("path"), entry.get("class"),
                     entry.get("role"),
                     entry.get("from") or ""])
    body = render.table(rows, headers=["path", "class", "role", "from"])
    return body + "\n" + _pair("next", view.get("next"))


# -- the draft lens --------------------------------------------------------
def _r_status_draft(advice: dict, path: str, full: bool = False) -> str:
    """The authoring triad over a session that is not a claim yet.

    Terse, the three COUNTS a reader acts on. Under --all, the table those
    counts summarize -- and no counts, because a number beside the rows it
    came from is the one place a reader could read a total instead of the
    evidence.
    """
    lines = []
    if full:
        lines.append("draft       the authoring triad, file by file")
        rows = [[row["path"], row["observed"], row["declared"],
                 row["evidence"]] for row in advice.get("rows") or []]
        lines.append(render.table(
            rows, headers=["path", "observed", "declared", "evidence"]))
    else:
        lines.append(f"draft       observed={advice['observed']} "
                     f"declared={advice['declared']} "
                     f"unresolved={advice['unresolved']}")
    if advice.get("undeclared"):
        lines.append("undeclared  " + ", ".join(advice["undeclared"])
                     + "   (no gate reaches it, so no claim holds it down)")
    if advice["sealable"]:
        lines.append(f"next        packable: ret pack {path} --accept "
                     f"{' '.join(advice.get('verdicts') or ['OK'])} "
                     f"-o <claim>")
    else:
        lines.append("next        " + (advice["why"][0] if advice.get("why")
                                       else "run the command that decides"))
    return "\n".join(lines)


# -- the tree lens ---------------------------------------------------------
def _r_tree(view: dict) -> str:
    """A claim as a tree: what it is made of, and what it stands on."""
    lines = [f"{view.get('name')}  {render.short(view.get('root'))}  "
             f"{view.get('phase')}",
             f"layers={len(view.get('components') or [])}"]
    for entry in view.get("files") or []:
        klass = entry.get("class")
        path = entry.get("path")
        if _colored():
            lines.append("    " + render.paint(
                str(path), _CLASS_COLOR.get(klass)))
        else:
            label = "free" if klass == "generated" else "pinned"
            lines.append("    " + label.ljust(11) + str(path))
    for link in view.get("components") or []:
        lines.append(f"    layer       {link.get('component')}  "
                     f"{render.short(link.get('root'))}  "
                     f"via {link.get('input')}")
    lines.append(_pair("next", view.get("next")))
    return "\n".join(lines)


def _r_structure(found: dict) -> str:
    """What a claim is made of, as the registry reads it."""
    rows = [[entry.get("path"), entry.get("role"), entry.get("class"),
             entry.get("from") or ""] for entry in found.get("files") or []]
    lines = [f"{found.get('name')}  format={found.get('format')}",
             render.table(rows, headers=["path", "role", "class", "from"])]
    if found.get("layers"):
        lines.append(render.table(
            [[layer.get("name"), render.short(layer.get("root")),
              "resolved" if layer.get("resolved") else "unresolved",
              layer.get("input") or ""] for layer in found["layers"]],
            headers=["layer", "root", "state", "via"]))
    return "\n".join(lines)


def _r_claims(rows) -> str:
    """The claims in a workspace's store."""
    if not rows:
        return "no claims in this workspace's store"
    return render.table(
        [[row.get("name"), render.short(row.get("root")), row.get("phase"),
          os.path.basename(row.get("path") or "")] for row in rows],
        headers=["name", "root", "phase", "where"])


def _r_deps(dag: dict) -> str:
    """The component DAG, as the store can prove it."""
    lines = []
    for entry in dag.get("claims") or []:
        lines.append(f"{entry['name']}  {render.short(entry['root'])}  "
                     f"{entry.get('phase')}")
        for edge in entry.get("depends_on") or []:
            lines.append(f"    {edge.get('component')}  "
                         f"{render.short(edge.get('root'))}  "
                         f"{edge.get('status')}  via {edge.get('input')}")
    return "\n".join(lines) or "no claims in this workspace's store"
