"""Human readable claim, draft, dependency, and tree views."""

from __future__ import annotations

import os
from collections.abc import Mapping

from .. import kernel, render
from .report import _row, _value


_DECLARED_ROLE = {
    "inputs": "pinned input",
    "generated": "generated output",
    "pinned": "pinned output",
    "validated": "gate verdict",
}


def _t_status_claim(view):
    """A terse, single line claim summary."""
    name = view.get("name", "claim")
    root = render.short(view.get("root") or "-", 12)
    return f"{name} {root} {view.get('phase', 'draft')} {view.get('verdict', 'unmeasured')}"


def _ledger_status_claim(view):
    """Show the claim's cost totals if they were measured."""
    cost = view.get("cost") or view.get("ledger")
    if not isinstance(cost, Mapping) or not cost:
        return "cost: unmeasured"
    return "cost: " + ", ".join(f"{unit}={_value(cost[unit])}" for unit in ("usd", "tokens", "calls", "seconds") if unit in cost)


def _v_status_claim(view):
    """A verbose status using the same facts as the terse view."""
    lines = [_t_status_claim(view)]
    for key in ("root", "verified", "proof", "signatures", "gate_ok", "next"):
        if key in view:
            lines.append(_row(key.replace("_", " "), view[key]))
    lines.append(_ledger_status_claim(view))
    return "\n".join(lines)


def _files_claim(directory, parsed=None):
    """List declared files and whether each is present in the claim."""
    parsed = parsed or kernel.load_recipe(directory)
    claim = parsed.get("claim", {})
    names = [(name, "pinned input") for name in claim.get("inputs", [])]
    for name in (claim.get("inputs_manifest"), claim.get("environment")):
        if name:
            names.append((name, "pinned input"))
    for step in parsed.get("step", []):
        kind = step.get("kind")
        role = step.get("class", "generated" if kind == "produce" else "pinned")
        names.append((step["output"], _DECLARED_ROLE.get(role, role)))
    return "\n".join(f"{role}: {name} ({'present' if os.path.isfile(os.path.join(directory, name)) else 'absent'})" for name, role in names)


def _r_status_draft(view):
    """Render a draft's sealability and the next suggested action."""
    if not isinstance(view, Mapping):
        return "draft: " + _value(view)
    lines = ["draft: " + ("sealable" if view.get("sealable") else "unsealed")]
    for key in ("gates", "reason", "next"):
        if key in view:
            lines.append(_row(key, view[key]))
    return "\n".join(lines)


def _r_tree(value):
    return render.tree(value)


def _r_structure(value):
    if not isinstance(value, Mapping):
        return render.tree(value)
    lines = [f"{value.get('name', 'claim')} {render.short(value.get('root', '-'), 12)} {value.get('phase', '')}".rstrip()]
    for link in value.get("depends_on", []):
        lines.append("  " + _value(link.get("component", link)) + " " + render.short(link.get("root", "-"), 12))
    return "\n".join(lines)


def _r_claims(value):
    rows = value.get("claims", []) if isinstance(value, Mapping) else value
    return "\n".join(_t_status_claim(row) for row in rows)


def _r_deps(value):
    rows = value.get("claims", []) if isinstance(value, Mapping) else value
    lines = []
    for row in rows:
        lines.append(_t_status_claim(row))
        for link in row.get("depends_on", []):
            lines.append("  " + _value(link.get("component", "?")) + " " + _value(link.get("status", "declared")))
    return "\n".join(lines)
