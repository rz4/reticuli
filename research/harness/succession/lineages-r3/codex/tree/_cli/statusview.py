"""Human-readable status, dependency, and structure views."""

from __future__ import annotations

import os

from .report import _row


_DECLARED_ROLE = {
    "generated": "generated",
    "free": "generated",
    "pinned": "pinned",
    "exact": "pinned",
    "validated": "validated",
}


def _files_claim(recipe):
    """List files named by the recipe and the role of each declaration."""
    if not isinstance(recipe, dict):
        return []
    files = [{"path": name, "role": "input"} for name in recipe.get("claim", {}).get("inputs", [])]
    for step in recipe.get("step", []):
        default = "generated" if step.get("kind") == "produce" else "pinned"
        files.append({"path": step.get("output"),
                      "role": _DECLARED_ROLE.get(step.get("class", default), default)})
    return files


def _ledger_status_claim(events):
    """Summarize producer measurements from ledger events."""
    if not isinstance(events, list):
        return "unmeasured"
    totals = {}
    for event in events:
        if not isinstance(event, dict):
            continue
        for unit in ("usd", "tokens", "calls", "seconds"):
            value = event.get(unit)
            if type(value) in (int, float):
                totals[unit] = totals.get(unit, 0) + value
    return ", ".join(f"{unit}={totals[unit]}" for unit in ("usd", "tokens", "calls", "seconds")
                     if unit in totals) or "unmeasured"


def _t_status_claim(view):
    """One-line status for a claim view."""
    if not isinstance(view, dict):
        return str(view)
    return "  ".join(str(view.get(key) or "-") for key in ("name", "phase", "root"))


def _v_status_claim(view):
    """Expanded status for a claim view."""
    if not isinstance(view, dict):
        return str(view)
    keys = ("name", "root", "phase", "verified", "verdict", "proof", "signatures", "next")
    return "\n".join(_row(key, view.get(key)) for key in keys)


def _r_status_draft(view):
    if isinstance(view, dict):
        return "\n".join((_row("phase", "draft"), _row("name", view.get("name")),
                          _row("next", view.get("next", "seal the claim"))))
    return "phase: draft"


def _r_claims(rows):
    if not rows:
        return "no sealed claims"
    return "\n".join(_t_status_claim(row) for row in rows)


def _r_deps(data):
    rows = data.get("claims", []) if isinstance(data, dict) else data
    lines = []
    for row in rows or []:
        lines.append(_t_status_claim(row))
        for edge in row.get("depends_on", []):
            lines.append(f"  {edge.get('component', '?')} -> {edge.get('input', '?')}  {edge.get('status', 'unresolved')}")
    return "\n".join(lines) if lines else "no dependencies"


def _r_structure(data):
    if not isinstance(data, dict):
        return str(data)
    return "\n".join(_row(key, value) for key, value in data.items())


def _r_tree(data):
    if isinstance(data, dict):
        return _r_deps(data) if "claims" in data else _r_structure(data)
    if isinstance(data, list):
        return "\n".join(_r_tree(item) for item in data)
    return os.fspath(data) if isinstance(data, os.PathLike) else str(data)
