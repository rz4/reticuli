"""Statusview: rendering reads -- status, draft, and the workspace's shape
(spec/layers.md, "surface").

Everything here renders a *read*: `views._claim_view`'s state dict, a
draft session's `feedback.advise`, or the workspace's own inventory
(`registry.claims`/`registry.deps`). Nothing here runs a gate or seals
anything -- a status is a report of what is already true on disk, never
a verdict freshly earned. `_DECLARED_ROLE` is the phase vocabulary's
human sentence, alongside `views._LADDER`'s "what closes the gap".
"""
from . import output
from . import report
from . import views
from .. import _util
from .. import feedback
from .. import kernel
from .. import registry
from .. import render

_DECLARED_ROLE = {
    "draft": "a drafted session -- no root computed yet",
    "sealed": "sealed -- its root is computed, not yet crosschecked or signed",
    "signed": "signed and proven -- a recorded crosscheck under a trusted signature",
}


# -- claim inventory: the declared files of one claim ------------------------


def _files_claim(d):
    """Every file a claim at `d` declares: its recipe, its pinned inputs,
    and every step's output -- read for display only, no gate, no root
    check.
    """
    parsed = kernel.load_recipe(d)
    names = {_util.recipe_name(d)}
    names.update(_util.declared_inputs(parsed))
    for step in parsed.get("step", []):
        names.add(step["output"])
    return sorted(names)


# -- status: terse, verbose, ledger ------------------------------------------


def _t_status_claim(d, args):
    """One-line terse status: name, shortened root, overall verdict."""
    view = views._claim_view(d)
    root_disp = render.short(view["root"]) if view.get("root") else "-"
    output._line(
        f"{view.get('name')}  {root_disp}  {view['verdict']}",
        color="green" if view.get("verified") else "yellow", args=args,
    )
    return 0 if view.get("verified") else 1


def _v_status_claim(d, args):
    """Verbose status: every fact `views._claim_view` read, one row each."""
    view = views._claim_view(d)
    output._line(report._row("name", view.get("name")), args=args)
    output._line(report._row("root", view.get("root")), args=args)
    output._line(report._row("phase", view.get("phase")), args=args)
    output._line(
        report._row("role", _DECLARED_ROLE.get(view.get("phase"), "unknown")), args=args,
    )
    output._line(report._row("verified", view.get("verified")), args=args)
    for gate in view.get("gates", []):
        output._line(report._row(f"gate:{gate['output']}", gate["decided_by"]), args=args)
    for sig in view.get("signatures", []):
        output._line(report._row("signature", sig), args=args)
    for unit, total in sorted((view.get("cost") or {}).items()):
        output._line(report._row(f"cost:{unit}", total), args=args)
    output._line(report._row("next", view.get("next")), args=args)
    return 0 if view.get("verified") else 1


def _ledger_status_claim(d, args):
    """A claim's raw cost-ledger events (`kernel.ledger_events`), oldest
    first -- the history behind `_v_status_claim`'s cost totals.
    """
    events = kernel.ledger_events(d)
    if not events:
        output._line("ledger: empty", args=args)
        return 0
    for event in events:
        output._line(report._row(event.get("event", "?"), event), args=args)
    return 0


# -- draft: a traced-but-unsealed session ------------------------------------


def _r_status_draft(ws, args):
    """A traced session's draft status: whether `feedback.advise` reads
    it as sealable yet, and why.
    """
    sense = feedback.advise(ws)
    ok = sense.get("sealable", False)
    for reason in sense.get("reasons", []):
        output._line(report._row("reason", reason), args=args)
    output._line(
        f"status-draft: {'sealable' if ok else 'not yet sealable'}",
        color="green" if ok else "yellow", args=args,
    )
    return 0 if ok else 1


# -- the workspace's shape: claims, deps, structure, tree --------------------


def _r_claims(ws, args):
    """The workspace's claim inventory (`registry.claims`), full roots."""
    rows = registry.claims(ws)
    if getattr(args, "json", False):
        output._finish("claims", rows, True, "ok", args, None)
    else:
        text = render.table(rows, headers=["name", "root", "phase"])
        output._line(text if text else "claims: none", args=args)
    return 0


def _r_deps(ws, args):
    """The workspace's dependency graph (`registry.deps`), raw: one row
    per claim/component edge.
    """
    graph = registry.deps(ws)
    if getattr(args, "json", False):
        output._finish("deps", graph, True, "ok", args, None)
        return 0
    for claim in graph.get("claims", []):
        if not claim.get("depends_on"):
            output._line(report._row(claim["name"], "no declared components"), args=args)
            continue
        for edge in claim["depends_on"]:
            output._line(
                report._row(f"{claim['name']} -> {edge['component']}", edge["status"]),
                args=args,
            )
    return 0


def _r_structure(ws, args):
    """The workspace's claim inventory as a table: name, shortened root,
    phase -- the flat anatomy of what is sealed here.
    """
    rows = [
        {"name": c["name"], "root": render.short(c["root"]) if c.get("root") else "-",
         "phase": c["phase"]}
        for c in registry.claims(ws)
    ]
    text = render.table(rows, headers=["name", "root", "phase"])
    output._line(text if text else "structure: no sealed claims in this workspace", args=args)
    return 0


def _r_tree(ws, args):
    """The workspace's dependency graph as an indented tree: one branch
    per claim, one leaf per declared component and its link status.
    """
    graph = registry.deps(ws)
    forest = [
        (claim["name"], [
            f"{edge['component']} ({edge['status']})" for edge in claim.get("depends_on", [])
        ])
        for claim in graph.get("claims", [])
    ]
    text = render.tree(forest)
    output._line(text if text else "tree: no claims in this workspace", args=args)
    return 0
