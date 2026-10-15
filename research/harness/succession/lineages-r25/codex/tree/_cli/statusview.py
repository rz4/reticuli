"""Text views of draft, sealed, and composed claims."""

from __future__ import annotations

import os

from . import views
from .report import _row


_DECLARED_ROLE = {
    "generated": "generated",
    "pinned": "pinned",
    "validated": "validated",
}


def _t_status_claim(view):
    """One line suitable for a list of claims."""
    root = view.get("root") or "draft"
    return f"{view.get('name', 'claim')}  {views.short(root)}  {view.get('phase', 'draft')}"


def _ledger_status_claim(view):
    residue = view.get("residue") or {}
    events = residue.get("ledger") or []
    return _row("ledger events", len(events))


def _files_claim(view):
    return "\n".join(_row("generated", name) for name in view.get("generated", []))


def _v_status_claim(view):
    lines = [_t_status_claim(view)]
    for key in ("verified", "materialized", "audit_ok", "next"):
        if key in view:
            lines.append(_row(key.replace("_", " "), view[key]))
    files = _files_claim(view)
    if files:
        lines.append(files)
    lines.append(_ledger_status_claim(view))
    return "\n".join(lines)


def _r_status_draft(view):
    return "\n".join((_t_status_claim(view), _row("next", view.get("next", "seal"))))


def _r_claims(rows):
    if isinstance(rows, dict):
        rows = rows.get("claims", [])
    return "\n".join(_t_status_claim(row) for row in rows)


def _r_deps(graph):
    if isinstance(graph, dict):
        graph = graph.get("claims", [])
    lines = []
    for claim in graph:
        lines.append(_t_status_claim(claim))
        for edge in claim.get("depends_on", []):
            lines.append("  " + _row(edge.get("component", edge.get("input", "dependency")), edge.get("status", "unknown")))
    return "\n".join(lines)


def _r_tree(graph):
    return _r_deps(graph)


def _r_structure(structure):
    if isinstance(structure, dict) and "claims" in structure:
        return _r_deps(structure)
    if isinstance(structure, dict):
        return "\n".join(_row(key, structure[key]) for key in sorted(structure))
    return str(structure)
