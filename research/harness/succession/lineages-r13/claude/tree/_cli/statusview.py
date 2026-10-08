"""The status/draft/tree family: the `-v` and terse views `status`,
`claims`, `deps`, and `tree` render (spec/layers.md's surface layer).

`_t_status_claim` and `_v_status_claim` render the dict `views._claim_view`
already reads off a claim's own bytes -- the terse one-liner and the `-v`
block, same shape as `report.py`'s action-verb renderers: formatting only,
no fetch of their own. `_ledger_status_claim` renders the event list
`views._read_residue` already reads. `_files_claim` has no fetcher upstream
to lean on, so it reads the claim's own recipe directly through
`reticuli.kernel` -- never `reticuli._kernel` -- exactly as `views.py` does.

`_DECLARED_ROLE` is the one step class each declared file falls into
(`spec/claim-format.md`): `generated` (regrowable, outside identity),
`pinned` (must reproduce byte for byte), `validated` (a gate verdict pinned
into the root).
"""
import os

from .. import _util
from .. import kernel
from .. import render
from . import report

_DECLARED_ROLE = {
    "generated": "generated -- regrowable, outside identity",
    "pinned": "pinned -- must reproduce byte for byte",
    "validated": "validated -- a gate verdict pinned into the root",
}


def _step_class(step: dict) -> str:
    default = "generated" if step.get("kind") == "produce" else "pinned"
    return step.get("class", default)


def _files_claim(d: str) -> str:
    """Every file the claim at `d` declares -- its pinned inputs and each
    step's own output -- with its step class and whether the byte it names
    is actually present on disk right now."""
    recipe = kernel.load_recipe(d)
    rows = []
    for p in _util.declared_inputs(recipe, d):
        rows.append({"path": p, "role": _DECLARED_ROLE["pinned"],
                     "present": os.path.isfile(os.path.join(d, p))})
    for step in recipe.get("step", []):
        output = step.get("output")
        if not output:
            continue
        role = _DECLARED_ROLE.get(_step_class(step), _step_class(step))
        rows.append({"path": output, "role": role,
                     "present": os.path.isfile(os.path.join(d, output))})
    if not rows:
        return "files: none declared"
    return "files:\n" + render.table(rows, columns=["path", "role", "present"])


def _ledger_status_claim(events: list) -> str:
    """A claim's own cost and gate history -- the ledger events
    `views._read_residue` already reads off disk -- newest first."""
    events = list(events or [])
    if not events:
        return "ledger: empty"
    lines = ["ledger:"]
    for event in reversed(events):
        kind = event.get("event", "cost")
        ts = event.get("when", event.get("ts"))
        when = report._when(ts) if ts is not None else "unknown"
        detail = ", ".join(f"{k}={v}" for k, v in sorted(event.items())
                            if k not in ("event", "when", "ts"))
        lines.append(f"  [{when}] {kind}" + (f" ({detail})" if detail else ""))
    return "\n".join(lines)


def _r_claims(claims: list) -> str:
    """`registry.claims`'s result: every sealed claim in a workspace's
    registry."""
    claims = list(claims or [])
    if not claims:
        return "claims: none"
    rows = [{"name": c.get("name"), "root": render.short(c.get("root") or "", 12),
             "phase": c.get("phase")} for c in claims]
    return "claims:\n" + render.table(rows, columns=["name", "root", "phase"])


def _r_deps(deps: dict) -> str:
    """`registry.deps`'s result: the dependency graph, and whether each
    declared component currently resolves."""
    nodes = (deps or {}).get("claims") or []
    if not nodes:
        return "deps: none"
    lines = ["deps:"]
    for node in nodes:
        lines.append(f"  {node.get('name')}")
        for link in node.get("depends_on") or []:
            lines.append(f"    -> {link.get('component')} ({link.get('status')}) "
                         f"via {link.get('input')}")
    return "\n".join(lines)


def _r_status_draft(advice: dict) -> str:
    """`feedback.advise`'s result: whether a draft session looks sealable
    yet."""
    advice = advice or {}
    lines = ["draft:", "  " + report._row("sealable", advice.get("sealable"))]
    present = advice.get("present") or []
    if present:
        lines.append("  " + report._row("candidate gate output", ", ".join(present)))
    return "\n".join(lines)


def _r_structure(view: dict) -> str:
    """A claim's composition: how many of its declared steps fall into each
    class, and which components it is built from."""
    view = view or {}
    lines = ["structure:"]
    counts = view.get("classes") or {}
    for cls in ("generated", "pinned", "validated"):
        if cls in counts:
            lines.append(f"  {cls}: {counts[cls]}")
    components = view.get("components") or []
    if components:
        lines.append("  components:")
        for link in components:
            lines.append(f"    {link.get('component')} <- {link.get('input')}")
    return "\n".join(lines)


def _r_tree(node: dict) -> str:
    """A dependency DAG or component chain, indented."""
    return render.tree(node)


def _t_status_claim(view: dict) -> str:
    """`views._claim_view`'s terse one-line form."""
    view = view or {}
    root = render.short(view["root"], 12) if view.get("root") else "-"
    return f"{view.get('name') or '(unnamed)'}  {root}  {view.get('phase')}"


def _v_status_claim(view: dict) -> str:
    """`views._claim_view`'s `-v` block."""
    view = view or {}
    lines = ["status:",
              "  " + report._row("name", view.get("name")),
              "  " + report._row("root", view.get("root")),
              "  " + report._row("phase", view.get("phase")),
              "  " + report._row("verified", view.get("verified")),
              "  " + report._row("next", view.get("next"))]
    signatures = view.get("signatures") or []
    if signatures:
        lines.append("  " + report._row("signatures", ", ".join(signatures)))
    if view.get("error"):
        lines.append("  " + report._row("error", view.get("error")))
    return "\n".join(lines)
