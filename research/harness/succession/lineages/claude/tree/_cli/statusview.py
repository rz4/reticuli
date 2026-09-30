"""reticuli._cli.statusview -- the status / draft / tree family.

Where `report.py` renders one verb's outcome, this module reads a claim
(or a whole workspace's store) and renders what it *is*, right now:
`_t_status_claim` / `_v_status_claim` are the terse and verbose views
`views._claim_view` is built from, `_files_claim` names every file a
claim's recipe declares against `_DECLARED_ROLE` (its role) and whether
it is present, and `_r_tree` / `_r_structure` / `_r_claims` / `_r_deps`
are the workspace-scope renderers over `reticuli.registry`. `_r_status_draft`
is the `status` verb itself: the terse render by default, the verbose one
under `-v`, ending through the same shared envelope `report.py` uses.

Stdlib only. Never the network.
"""
import os

from . import output
from . import report as _report
from . import views
from .. import _util
from .. import kernel
from .. import registry as _registry
from .. import render

_DECLARED_ROLE = {
    "pinned": "pinned input",
    "generated": "generated (regrowable)",
    "validated": "validated gate output",
}


def _claim_dir(args) -> str:
    claim = getattr(args, "claim", None)
    return claim if claim else os.getcwd()


# ---------------------------------------------------------------------------
# Per-claim views
# ---------------------------------------------------------------------------
def _files_claim(d: str) -> list:
    """One row per file the recipe declares -- `name`, its declared role
    (`_DECLARED_ROLE`), and whether it is present on disk right now."""
    recipe = kernel.load_recipe(d)
    rows = []
    seen = set()
    for name in _util.declared_inputs(d):
        rows.append({"name": name, "role": _DECLARED_ROLE["pinned"],
                     "present": os.path.isfile(os.path.join(d, name))})
        seen.add(name)
    for step in recipe.get("step", []):
        name = step.get("output")
        if not name or name in seen:
            continue
        seen.add(name)
        if step.get("kind") == "gate":
            role = _DECLARED_ROLE["validated"]
        else:
            cls = step.get("class") or "generated"
            role = _DECLARED_ROLE.get(cls, cls)
        rows.append({"name": name, "role": role,
                     "present": os.path.isfile(os.path.join(d, name))})
    return rows


def _ledger_status_claim(d: str) -> str:
    """A short table of the claim's ledger cost totals, or a plain
    sentence when nothing was measured."""
    totals = kernel.cost(d)
    if not totals:
        return "no ledger cost recorded"
    return render.table(sorted(totals.items()), headers=("unit", "total"))


def _t_status_claim(d: str) -> str:
    """The terse, one-line status render: name, short root, phase,
    verdict."""
    view = views._claim_view(d)
    root = render.short(view["root"]) if view["root"] else "-"
    return f"{view['name']}  {root}  {view['phase']}  {view['verdict']}"


def _v_status_claim(d: str) -> str:
    """The verbose (`-v`) status render: every field `views._claim_view`
    reports, one `report._row` line each."""
    view = views._claim_view(d)
    lines = [
        _report._row("name", view["name"]),
        _report._row("phase", view["phase"]),
        _report._row("verdict", view["verdict"]),
        _report._row("root", view["root"] or "(unsealed)"),
    ]
    for gate in view["gates"]:
        lines.append(_report._row(f"gate {gate['output']}", gate["deciding"]))
    for sig in view["signatures"]:
        lines.append(_report._row("signature", sig.get("identity") or "(unknown)"))
    lines.append(_report._row("ledger", _ledger_status_claim(d)))
    lines.append(_report._row("next", view["next"]))
    return "\n".join(lines)


def _r_status_draft(args) -> int:
    """The `status` verb: the terse render by default, the verbose one
    under `args.verbose`, then the shared envelope."""
    d = _claim_dir(args)
    try:
        view = views._claim_view(d)
    except kernel.ClaimError as exc:
        output._err("status", str(exc))
        return 1
    if not getattr(args, "json", False):
        text = _v_status_claim(d) if getattr(args, "verbose", False) else _t_status_claim(d)
        output._line(text, args)
    ok = view["verdict"] != "broken"
    return output._finish("status", view, ok, view["verdict"], args)


def _r_tree(args) -> int:
    """The `tree` verb: the claim's declared files as an indented tree,
    each leaf's declared role and presence."""
    d = _claim_dir(args)
    try:
        files = _files_claim(d)
    except kernel.ClaimError as exc:
        output._err("tree", str(exc))
        return 1
    node = {f["name"]: {"role": f["role"], "present": str(f["present"])} for f in files}
    if not getattr(args, "json", False):
        output._line(render.tree(node), args)
    return output._finish("tree", {"files": files}, True, "ok", args)


# ---------------------------------------------------------------------------
# Workspace-scope views (the claim store)
# ---------------------------------------------------------------------------
def _r_structure(args) -> int:
    """The workspace's store as claims and their component edges
    (`registry.structure`)."""
    ws = _claim_dir(args)
    data = _registry.structure(ws)
    if not getattr(args, "json", False):
        rows = [(c["name"], render.short(c["root"]), str(len(c["depends_on"])))
                for c in data["claims"]]
        text = render.table(rows, headers=("name", "root", "deps")) or "no claims in store"
        output._line(text, args)
    return output._finish("structure", data, True, "ok", args)


def _r_claims(args) -> int:
    """The `claims` verb: one row per claim sealed in the workspace's
    store (`registry.claims`)."""
    ws = _claim_dir(args)
    rows = _registry.claims(ws)
    if not getattr(args, "json", False):
        table_rows = [(r["name"], render.short(r["root"]), r["phase"]) for r in rows]
        text = render.table(table_rows, headers=("name", "root", "phase")) or "no claims in store"
        output._line(text, args)
    return output._finish("claims", {"claims": rows}, True, "ok", args)


def _r_deps(args) -> int:
    """The `deps` verb: the workspace's store as a dependency graph, one
    claim per line, its component edges indented beneath it."""
    ws = _claim_dir(args)
    data = _registry.deps(ws)
    if not getattr(args, "json", False):
        lines = []
        for c in data["claims"]:
            lines.append(f"{c['name']}  {render.short(c['root'])}")
            for dep in c["depends_on"]:
                lines.append(f"  -> {dep['component']}  [{dep['status']}]")
        output._line("\n".join(lines) or "no claims in store", args)
    return output._finish("deps", data, True, "ok", args)
