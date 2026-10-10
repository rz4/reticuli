"""Present the current state and structure of claims."""

from __future__ import annotations

from reticuli import kernel

from . import output, views


_DECLARED_ROLE = {
    "generated": "generated",
    "free": "generated",
    "pinned": "pinned",
    "exact": "pinned",
    "validated": "validated",
}


def _t_status_claim(directory):
    """One terse status line for a claim."""
    view = views._claim_view(directory)
    root = view["root"]
    return f"{view['name']} {root[:12] if root else '-'} {view['phase']}"


def _ledger_status_claim(directory):
    """Read measured costs without running a gate."""
    return kernel.cost(directory)


def _v_status_claim(directory):
    """Detailed status fields for a claim."""
    view = views._claim_view(directory)
    view["cost"] = _ledger_status_claim(directory)
    return view


def _files_claim(directory):
    """List declared files and their identity roles."""
    recipe = kernel.load_recipe(directory)
    files = [{"path": path, "role": "input"}
             for path in recipe["claim"].get("inputs", [])]
    for step in recipe.get("step", []):
        kind = step.get("kind")
        role = _DECLARED_ROLE.get(step.get("class"),
                                  "generated" if kind == "produce" else "pinned")
        files.append({"path": step["output"], "role": role})
    return files


def _r_status_draft(directory, args=None):
    """Display a draft's next authoring action."""
    view = views._claim_view(directory)
    return output._finish("status", view, True, view["phase"], args)


def _r_tree(data, args=None):
    return output._finish("tree", data, True, "ok", args)


def _r_structure(data, args=None):
    return output._finish("structure", data, True, "ok", args)


def _r_claims(data, args=None):
    return output._finish("claims", data, True, "ok", args)


def _r_deps(data, args=None):
    return output._finish("deps", data, True, "ok", args)
