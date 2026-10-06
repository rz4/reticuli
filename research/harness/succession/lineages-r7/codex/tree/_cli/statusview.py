"""Human-readable views of claim, draft, and dependency state."""

from __future__ import annotations

from collections.abc import Mapping

from .. import kernel, render
from . import views
from .report import _row


_DECLARED_ROLE = {
    "generated": "generated",
    "pinned": "pinned",
    "validated": "validated",
}


def _t_status_claim(view: Mapping) -> str:
    """One-line claim status for the default CLI view."""
    return " ".join(str(part) for part in (
        view.get("name", "claim"), view.get("status", view.get("phase", "unknown")),
        render.short(view["root"]) if view.get("root") else "unsealed") if part)


def _ledger_status_claim(view: Mapping) -> str:
    """Summarize measured production cost without guessing missing units."""
    cost = view.get("cost")
    if not isinstance(cost, Mapping) or not cost:
        return "cost: unmeasured"
    return _row("cost", cost)


def _v_status_claim(view: Mapping) -> str:
    """Expanded status with identity, proof, cost, and next action."""
    return "\n".join((
        _t_status_claim(view),
        _row("root", view.get("root")),
        _row("verified", view.get("verified")),
        _row("proof recorded", bool(view.get("proof"))),
        _ledger_status_claim(view),
        _row("next", view.get("next")),
    ))


def _files_claim(directory: str, claim_recipe: Mapping | None = None) -> str:
    """List files the recipe declares, in recipe order."""
    claim_recipe = claim_recipe or kernel.load_recipe(directory)
    rows = []
    for name in claim_recipe.get("claim", {}).get("inputs", []):
        rows.append(f"input  {name}")
    for step in claim_recipe.get("step", []):
        default = "generated" if step.get("kind") == "produce" else "pinned"
        role = _DECLARED_ROLE.get(step.get("class", default), default)
        rows.append(f"{role}  {step['output']}")
    return "\n".join(rows)


def _r_status_draft(view: Mapping) -> str:
    return "\n".join((_t_status_claim(view), _row("next", view.get("next", "seal"))))


def _r_tree(tree: Mapping | list) -> str:
    return render.tree(tree)


def _r_structure(structure: Mapping) -> str:
    lines = [_row("name", structure.get("name")),
             _row("root", structure.get("root")),
             _row("phase", structure.get("phase"))]
    for component in structure.get("components", []):
        lines.append(_row(component.get("component", "component"), component.get("root")))
    return "\n".join(lines)


def _r_claims(claims: list[Mapping]) -> str:
    return "\n".join(_t_status_claim(item) for item in claims)


def _r_deps(dependencies: Mapping | list) -> str:
    claims = dependencies.get("claims", []) if isinstance(dependencies, Mapping) else dependencies
    lines = []
    for item in claims:
        lines.append(_t_status_claim(item))
        for link in item.get("depends_on", []):
            lines.append("  " + _row(link.get("component", "component"), link.get("status")))
    return "\n".join(lines)
