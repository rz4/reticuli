"""Read-only text views of claims, drafts, dependencies, and their files."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from reticuli import render
from . import views


_DECLARED_ROLE = {
    "input": "pinned input",
    "generated": "generated output",
    "pinned": "pinned output",
    "validated": "gate verdict",
}


def _claim(value: Any) -> dict[str, Any]:
    """Accept either an already collected view or a claim directory."""
    if isinstance(value, Mapping):
        return dict(value)
    return views._claim_view(value)


def _t_status_claim(value: Any) -> str:
    """One-line status suitable for a list of claims."""
    claim = _claim(value)
    name = claim.get("name", "claim")
    phase = claim.get("phase", "draft")
    root = claim.get("root")
    return " ".join(str(part) for part in (name, phase, render.short(root) if root else None)
                    if part is not None)


def _ledger_status_claim(value: Any) -> str:
    """Show the measured cost units present in a claim summary."""
    claim = _claim(value)
    cost = claim.get("cost") or claim.get("ledger")
    if not isinstance(cost, Mapping) or not cost:
        return "cost: unmeasured"
    units = ("usd", "tokens", "calls", "seconds")
    return "cost: " + ", ".join(f"{key}={cost[key]}" for key in units if key in cost)


def _v_status_claim(value: Any) -> str:
    """Expanded status with the verifier-relative next action."""
    claim = _claim(value)
    lines = [_t_status_claim(claim)]
    lines.append(f"identity: {'verified' if claim.get('verified') else 'changed'}")
    if claim.get("next"):
        lines.append(f"next: {claim['next']}")
    if claim.get("proof"):
        lines.append("proof: recorded")
    if claim.get("signatures"):
        lines.append(f"signatures: {len(claim['signatures'])}")
    return "\n".join(lines)


def _files_claim(value: Any) -> str:
    """List declared files and their role in the claim."""
    if isinstance(value, Mapping):
        recipe = value
    else:
        from reticuli import kernel
        recipe = kernel.load_recipe(value)
    rows = [(path, _DECLARED_ROLE["input"])
            for path in recipe.get("claim", {}).get("inputs", [])]
    for step in recipe.get("step", []):
        role = _DECLARED_ROLE.get(step.get("class"), step.get("class", "output"))
        rows.append((step.get("output", ""), role))
    return "\n".join(f"{path}  {role}" for path, role in rows)


def _r_status_draft(value: Any) -> str:
    """Explain the state of a workspace that has no seal yet."""
    draft = _claim(value) if not isinstance(value, Mapping) else value
    name = draft.get("name", "claim")
    return f"{name}: draft\nnext: seal"


def _r_tree(value: Any) -> str:
    """Render nested claim structure with the shared tree formatter."""
    return render.tree(value)


def _r_structure(value: Any) -> str:
    """Render a claim's component links."""
    if not isinstance(value, Mapping):
        from reticuli import registry
        value = registry.structure(value)
    return render.tree(value)


def _r_claims(value: Any) -> str:
    """Render rows returned by the claim registry."""
    if not isinstance(value, (list, tuple)):
        from reticuli import registry
        value = registry.claims(value)
    return "\n".join(_t_status_claim(row) for row in value)


def _r_deps(value: Any) -> str:
    """Render the registry's dependency graph."""
    if not isinstance(value, Mapping):
        from reticuli import registry
        value = registry.deps(value)
    return render.tree(value)
