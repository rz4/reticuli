"""reticuli._cli.statusview: the status/draft/tree family.

`_t_status_claim` and `_v_status_claim` are the terse and verbose forms
of one claim's status line, both built from `views._claim_view` --
nothing here re-derives what that reader already composed from
`reticuli.kernel`. `_ledger_status_claim` lays the claim's ledger totals
beside that same view. `_files_claim` lists a claim's declared files
against `_DECLARED_ROLE`, the vocabulary status and tree share.
`_r_status_draft` reports on a session that has not sealed yet
(`feedback.advise`, never a gate re-run). `_r_claims` and `_r_deps`
render the exchange layer's registry (`registry.claims`, `registry.deps`);
`_r_structure` and `_r_tree` render a claim's step structure as an
indented tree.

Stdlib only.
"""
import os

from reticuli import feedback, kernel, registry, render
from reticuli._cli import views

_DECLARED_ROLE = {
    "generated": "regrowable implementation -- outside the root",
    "pinned": "must reproduce byte-for-byte -- inside the root",
    "validated": "a gate's verdict, earned by running it -- inside the root",
}


def _t_status_claim(d: str) -> str:
    """One line: name@short-root (phase) -> next rung."""
    view = views._claim_view(d)
    name = view.get("name") or "(draft)"
    root = render.short(view["root"]) if view.get("root") else "-"
    return f"{name}@{root} ({view['phase']}) -> {view['next']}"


def _v_status_claim(d: str) -> str:
    """The verbose status block: every context field `_claim_view`
    carries, beneath the same terse first line."""
    view = views._claim_view(d)
    lines = [_t_status_claim(d)]
    for key in ("verified", "audited", "signatures", "mutation"):
        if key in view:
            lines.append(f"  {key}: {view[key]}")
    return "\n".join(lines)


def _ledger_status_claim(d: str) -> dict:
    """The claim's status view, with its ledger totals laid beside it --
    bookkeeping `kernel.cost`/`kernel.ledger_events` already read, never
    identity-bearing."""
    view = views._claim_view(d)
    view["cost"] = kernel.cost(d)
    view["events"] = len(kernel.ledger_events(d))
    return view


def _files_claim(d: str) -> list:
    """Every file a claim's recipe declares -- pinned inputs and step
    outputs alike -- against its role in `_DECLARED_ROLE` and whether it
    is actually present on disk right now."""
    parsed = kernel.load_recipe(d)
    claim = parsed.get("claim") or {}
    rows = []
    for path in claim.get("inputs", []):
        rows.append({"path": path, "class": "pinned",
                     "role": _DECLARED_ROLE["pinned"],
                     "present": os.path.isfile(os.path.join(d, path))})
    for step in parsed.get("step", []):
        output_path = step.get("output")
        if not output_path:
            continue
        default_class = "generated" if step.get("kind") == "produce" else "pinned"
        cls = step.get("class", default_class)
        rows.append({"path": output_path, "class": cls,
                     "role": _DECLARED_ROLE.get(cls, cls),
                     "present": os.path.isfile(os.path.join(d, output_path))})
    return rows


def _r_status_draft(ws: str) -> dict:
    """Status for a session that has not sealed yet: whatever
    `feedback.advise` can sense from its trace alone, with no gate
    re-run and no filesystem change."""
    sense = feedback.advise(ws)
    return {"path": ws, "phase": "draft", **sense}


def _r_claims(ws: str) -> str:
    """The registry's claim list, one row per sealed claim."""
    entries = registry.claims(ws)
    rows = [(c["name"], render.short(c["root"]), c["phase"]) for c in entries]
    return render.table(rows, headers=("name", "root", "phase"))


def _r_deps(ws: str) -> str:
    """The registry's dependency DAG, one claim per top-level branch,
    each declared component shown with its resolution status."""
    tree_data = {
        c["name"]: [f"{dep['component']} ({dep['status']})" for dep in c["depends_on"]]
        for c in registry.deps(ws)["claims"]
    }
    return render.tree(tree_data)


def _r_structure(d: str) -> dict:
    """The nested structure `_r_tree` renders: a claim's name, its
    pinned inputs, and each step by kind and output."""
    parsed = kernel.load_recipe(d)
    claim = parsed.get("claim") or {}
    return {
        claim.get("name", "(unnamed)"): {
            "inputs": list(claim.get("inputs", [])),
            "step": [f"{s.get('kind')}: {s.get('output')}" for s in parsed.get("step", [])],
        }
    }


def _r_tree(d: str) -> str:
    """A claim's declared structure (inputs, steps) as an indented tree."""
    return render.tree(_r_structure(d))
