"""The status family: the one view, in its several lenses.

`status` reads and reports.  It never executes, so every lens is instant,
and what it shows about execution is a dated RECEIPT rather than a fact
established now — the difference between "these gates pass" and "these gates
passed here, then".

Three lenses, one state dict behind them: the claim lens (identity, the
receipt, the ladder), the session lens (the authoring triad — observed,
declared, unresolved), and the tree lens (what a claim is made of, and the
layers beneath it).

The class IS the colour where colour is on, and the label WORD returns where
colour is off: information never lives only in a hue.
"""
import os

from .. import render
from .output import _line, _rel, _wants_color

#: What each step class means to a reader, in the words the views use.
#: `generated` is FREE — outside the root, regrowable; everything else is
#: fixed, because its bytes are what the root is computed from.
_DECLARED_ROLE = {
    "input": "criterion",
    "generated": "free",
    "pinned": "fixed",
    "validated": "verdict",
    "carried": "shipped",
}

#: The tree lens labels by what the root covers, not by the step's class
#: name: a reader wants to know whether these bytes are identity.
_TREE_LABEL = {"input": "input", "generated": "free"}


def _row(label: str, value, width: int = 12) -> None:
    print(_line(label, value, width))


# -- the claim lens ---------------------------------------------------------


def _receipt_words(view: dict) -> str:
    receipt = view.get("audited")
    if not receipt:
        return "never on this machine"
    host = receipt.get("host") or {}
    where = host.get("platform") or "this machine"
    return (f"{receipt.get('verdict')}, {receipt.get('when')}, "
            f"on this machine ({where})")


def _discovery_words(view: dict):
    cost = view.get("cost") or {}
    discovery = cost.get("discovery")
    if not discovery:
        return None
    parts = ", ".join(f"{unit}={value}"
                      for unit, value in sorted(discovery.items()))
    return f"{parts} (what finding it cost: testimony, never the band)"


def _t_status_claim(view: dict, args) -> None:
    """The terse claim block: identity, what was earned, and the next rung."""
    from . import views as _views
    color = _wants_color(args)
    print(f"{render.paint(view.get('phase') or 'draft', view.get('phase') or 'draft', color)}"
          f"  {view.get('name')}")
    _row("identity", f"{render.paint(view['status'], view['status'], color)}"
                     f"  {render.short(view.get('recomputed'), 16)}"
         + ("  (" + ", ".join(view.get("changed") or []) + " moved)"
            if not view.get("ok") and view.get("changed") else ""))
    _row("audited", _receipt_words(view))
    _row("deciding", _views._deciding_words(view))
    discovery = _discovery_words(view)
    if discovery:
        _row("discovery", discovery)
    _row("proof", "recorded" if view.get("proof") else "none")
    signatures = view.get("signatures") or {}
    _row("signed", f"{signatures.get('total', 0)} statement(s)"
         if signatures.get("total") else "none")
    _row("next", view.get("next"))


def _v_status_claim(view: dict, args) -> None:
    """The explanatory claim block: full hashes, every declared file."""
    print("[status]")
    _row("name", view.get("name"))
    print(f'root = "{view.get("root")}"')
    print(f'recomputed = "{view.get("recomputed")}"')
    _row("phase", view.get("phase"))
    _row("format", view.get("format"))
    _row("components", len(view.get("components") or []))
    _t_status_claim(view, args)


def _files_claim(view: dict, args) -> None:
    """Every declared file by role, hiding none."""
    rows = []
    for entry in view.get("files") or []:
        cls = entry.get("class")
        rows.append([entry.get("path"), cls,
                     _DECLARED_ROLE.get(cls, "fixed"),
                     entry.get("from") or ""])
    print(render.table(rows, headers=["path", "class", "role", "from"]))
    _row("next", view.get("next"))


def _ledger_status_claim(view: dict, args) -> None:
    """The whole ledger of what this claim fixes, frees, and leaves unknown."""
    from . import views as _views
    fixed, free, deciding = [], [], []
    for entry in view.get("files") or []:
        if entry.get("class") == "generated":
            free.append(entry.get("path"))
        else:
            fixed.append(entry.get("path"))
        if entry.get("class") == "validated":
            deciding.append(entry.get("path"))
    _row("fixed", ", ".join(fixed) or "nothing")
    _row("deciding", ", ".join(deciding) or "nothing")
    _row("free", ", ".join(free) or "nothing")

    recorded = []
    receipt = view.get("audited")
    if receipt:
        recorded.append(f"audit, {receipt.get('when')}")
    measured = view.get("deciding")
    if measured:
        recorded.append(f"assess, {measured.get('when')}")
    _row("recorded", (", ".join(recorded) + " - a receipt, not a verdict")
         if recorded else "nothing - a receipt, not a verdict")
    unknown = list((measured or {}).get("not_measured") or [])
    if not measured:
        unknown = ["strength unknown: nothing has measured these criteria"]
    _row("unknown", ", ".join(unknown) or "nothing")
    discovery = _discovery_words(view)
    if discovery:
        _row("discovery", discovery)
    _row("next", view.get("next"))


# -- the session lens -------------------------------------------------------


def _r_status_draft(advice: dict, args) -> None:
    """The authoring triad: observed, declared, unresolved.

    The counts and the account are separate lenses, not one printed twice:
    `--all` is the file-by-file table, and a tally restated above it would
    only invite a reader to compare two renderings of the same fact.
    """
    if getattr(args, "all", False):
        rows = [[row["path"], row["observed"], row["declared"],
                 row["evidence"]] for row in advice.get("files") or []]
        print(render.table(rows, headers=["path", "observed", "declared",
                                          "evidence"]))
    else:
        print(f"draft  observed={advice.get('observed', 0)} "
              f"declared={advice.get('declared', 0)} "
              f"unresolved={advice.get('unresolved', 0)}")
        if advice.get("undeclared"):
            _row("undeclared", ", ".join(advice["undeclared"]))
        else:
            _row("packable", "ret pack <path> --accept <verdict> -o <claim>"
                 if advice.get("sealable") else
                 "not yet: no gate has earned a verdict here")
    _row("next", "ret pack <path> --accept <verdict> -o <claim>"
         if advice.get("sealable") else
         "run the gate that decides this work, then ret pack")


# -- the tree lens ----------------------------------------------------------


def _r_tree(payload: dict, args) -> None:
    """What a claim is made of, and the layers beneath it."""
    color = _wants_color(args)
    print(f"{payload.get('name')}  {render.short(payload.get('root'), 16)}  "
          f"layers={len(payload.get('layers') or [])}")
    for entry in payload.get("files") or []:
        cls = entry.get("class")
        label = _TREE_LABEL.get(cls, "pinned")
        path = entry.get("path")
        if color:
            # On colour, the class IS the colour: the label word yields.
            print(f"    {render.paint(path, cls, True)}")
        else:
            print(f"    {label:<10} {path}")
    for layer in payload.get("layers") or []:
        _row("layer", f"{layer.get('name')}  "
                      f"{render.short(layer.get('root'), 16)}  "
                      f"{'resolved' if layer.get('resolved') else 'unresolved'}")


def _r_structure(payload: dict, args) -> None:
    """The anatomy, as a nested shape."""
    children = [{"label": f"{entry.get('class')}  {entry.get('path')}"}
                for entry in payload.get("files") or []]
    children += [{"label": f"layer  {layer.get('name')}"}
                 for layer in payload.get("layers") or []]
    print(render.tree({"label": f"{payload.get('name')}  "
                                f"{render.short(payload.get('root'), 16)}",
                       "children": children}))


def _r_claims(rows: list, args) -> None:
    """The claim store, as the workspace can see it."""
    table = [[row.get("name"), render.short(row.get("root"), 16),
              row.get("phase"), "fresh" if row.get("ok") else "broken"]
             for row in rows or []]
    if not table:
        print("no claims in this workspace")
        return
    print(render.table(table, headers=["name", "root", "phase", "identity"]))


def _r_deps(payload: dict, args) -> None:
    """The component DAG, edge by edge."""
    rows = []
    for claim in payload.get("claims") or []:
        if not claim.get("depends_on"):
            rows.append([claim.get("name"), "-", "-"])
        for edge in claim.get("depends_on") or []:
            rows.append([claim.get("name"), edge.get("component"),
                         edge.get("status")])
    print(render.table(rows, headers=["claim", "depends on", "status"]))
