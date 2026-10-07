"""Text views of claims, drafts, dependencies, and directory structure."""

from __future__ import annotations

from collections.abc import Mapping

from reticuli import render


_DECLARED_ROLE = {
    "generated": "generated",
    "free": "generated",
    "pinned": "pinned",
    "exact": "pinned",
    "validated": "validated",
}


def _t_status_claim(view):
    """One-line status for a claim."""
    name = view.get("name", "claim")
    phase = view.get("phase", "draft")
    root = view.get("root")
    return f"{name}: {phase}" + (f" {render.short(root)}" if root else "")


def _ledger_status_claim(view):
    """Show recorded cost without mistaking missing values for zero."""
    cost = view.get("cost") or {}
    if not cost:
        return "cost: unmeasured"
    return "cost: " + ", ".join(f"{unit}={value}" for unit, value in cost.items())


def _files_claim(recipe):
    """List declared inputs and outputs with their roles."""
    claim = recipe.get("claim", {})
    rows = [(path, "input") for path in claim.get("inputs", [])]
    for step in recipe.get("step", []):
        role = step.get("class", "generated" if step.get("kind") == "produce" else "pinned")
        rows.append((step.get("output", ""), _DECLARED_ROLE.get(role, role)))
    return "\n".join(f"{role}: {path}" for path, role in rows)


def _v_status_claim(view):
    """Expanded claim status."""
    lines = [_t_status_claim(view)]
    for key in ("verified", "proof_recorded", "next"):
        if key in view:
            lines.append(f"  {key}: {view[key]}")
    lines.append("  " + _ledger_status_claim(view))
    return "\n".join(lines)


def _r_status_draft(view, verbose=False):
    line = _t_status_claim(view)
    return _v_status_claim(view) if verbose else line


def _r_tree(value):
    return render.tree(value)


def _r_structure(value):
    return render.tree(value)


def _r_claims(claims):
    if isinstance(claims, Mapping):
        claims = claims.values()
    return "\n".join(_t_status_claim(claim) for claim in claims)


def _r_deps(dependencies):
    return render.tree(dependencies)
