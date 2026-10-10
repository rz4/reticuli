"""Render claim state, draft state, and structure for the command line."""

from __future__ import annotations

from .output import _finish, _rel


_DECLARED_ROLE = {
    "generated": "generated",
    "free": "generated",
    "pinned": "pinned",
    "exact": "pinned",
    "validated": "validated",
}


def _t_status_claim(view, args=None):
    """Render the short claim status."""
    return _finish("status", view, view.get("verified", {}).get("ok", False),
                   view.get("status", view.get("phase", "unknown")), args,
                   root=view.get("root"))


def _ledger_status_claim(view, args=None):
    """Render the claim status with its recorded proof."""
    return _t_status_claim(view, args)


def _v_status_claim(view, args=None):
    """Render the verbose claim status."""
    return _t_status_claim(view, args)


def _files_claim(recipe):
    """List paths declared by the recipe, with their roles."""
    files = [(name, "input") for name in recipe.get("claim", {}).get("inputs", [])]
    for step in recipe.get("step", []):
        if "output" in step:
            role = step.get("class", "generated" if step.get("kind") == "produce" else "pinned")
            files.append((step["output"], _DECLARED_ROLE.get(role, role)))
    return files


def _r_status_draft(view, args=None):
    return _finish("status", view, True, "draft", args)


def _r_tree(data, args=None):
    return _finish("tree", data, True, "ok", args)


def _r_structure(data, args=None):
    return _finish("structure", data, True, "ok", args)


def _r_claims(data, args=None):
    return _finish("claims", data, True, "ok", args)


def _r_deps(data, args=None):
    return _finish("deps", data, True, "ok", args)
