"""Status, draft, dependency, and tree views for the command line."""

from __future__ import annotations

import os

from reticuli import kernel, registry, render
from reticuli._util import declared_inputs

from . import views
from .output import _finish


_DECLARED_ROLE = {
    "recipe": "recipe",
    "input": "pinned input",
    "generated": "generated output",
    "pinned": "pinned output",
    "validated": "gate verdict",
}


def _files_claim(directory):
    """List recipe-declared files and whether each is present."""
    recipe = kernel.load_recipe(directory)
    rows = []
    recipe_path = "reticuli.toml" if os.path.isfile(os.path.join(directory, "reticuli.toml")) else "claim.toml"
    names = [(recipe_path, "recipe")]
    names.extend((name, "input") for name in declared_inputs(directory))
    for step in recipe.get("step", []):
        role = step.get("class", "generated" if step["kind"] == "produce" else "pinned")
        names.append((step["output"], role))
    for name, role in dict(names).items():
        rows.append({"path": name, "role": _DECLARED_ROLE.get(role, role),
                     "present": os.path.isfile(os.path.join(directory, name))})
    return rows


def _ledger_status_claim(directory):
    """Report measured production cost without inventing missing units."""
    return {"events": kernel.ledger_events(directory), "cost": kernel.cost(directory)}


def _t_status_claim(directory):
    """Compact summary of a sealed claim."""
    view = views._claim_view(directory)
    return f"{view['name']} {view['phase']} {view.get('root') or '-'}"


def _v_status_claim(directory):
    """Structured status with declared files and recorded residue."""
    view = views._claim_view(directory)
    view["files"] = _files_claim(directory)
    view["ledger"] = _ledger_status_claim(directory)
    return view


def _r_status_draft(directory, args=None):
    """Render the status of an unsealed claim."""
    recipe = kernel.load_recipe(directory)
    data = {"name": recipe["claim"]["name"], "phase": "draft",
            "root": None, "files": _files_claim(directory), "next": "seal"}
    if args is None:
        return data
    return _finish("status", data, True, "draft", args)


def _r_tree(data, args=None):
    """Render tree rows supplied by the caller."""
    if args is None:
        return render.tree(data)
    return _finish("tree", {"rows": data}, True, "ok", args)


def _r_structure(data, args=None):
    """Render a component structure result."""
    if args is None:
        return data
    return _finish("structure", data, True, "ok", args)


def _r_claims(workspace, args=None):
    rows = registry.claims(workspace)
    if args is None:
        return rows
    return _finish("claims", {"claims": rows}, True, "ok", args)


def _r_deps(workspace, args=None):
    data = registry.deps(workspace)
    if args is None:
        return data
    return _finish("deps", data, True, "ok", args)
