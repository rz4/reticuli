"""Compact and detailed views of claims, drafts, and dependency trees."""

from __future__ import annotations

from typing import Any

from reticuli import render

from .output import _line


_DECLARED_ROLE = {
    "generated": "generated",
    "free": "generated",
    "pinned": "pinned",
    "exact": "pinned",
    "validated": "validated",
}


def _t_status_claim(view: dict, *_, **__) -> str:
    """One line suitable for a list of claims."""
    line = "  ".join(str(part) for part in
                     (view.get("name", "claim"),
                      render.short(view.get("root") or "draft"),
                      view.get("phase", "draft")))
    _line(line)
    return line


def _ledger_status_claim(view: dict, *_, **__) -> Any:
    cost = view.get("cost")
    if isinstance(cost, dict) and cost:
        line = "  ".join(f"{unit}={value}" for unit, value in sorted(cost.items()))
    else:
        line = "cost: unmeasured"
    _line(line)
    return cost


def _files_claim(view: dict, *_, **__) -> list[dict]:
    rows = view.get("generated", [])
    for row in rows:
        _line(f"{row.get('output', '?')}: {'present' if row.get('present') else 'absent'}")
    return rows


def _v_status_claim(view: dict, *_, **__) -> dict:
    """Expand a compact claim view with evidence and the next action."""
    _t_status_claim(view)
    checked = view.get("verified") or {}
    _line(f"identity: {'verified' if checked.get('ok') else checked.get('reason', 'unverified')}")
    _line(f"next: {view.get('next', 'verify')}")
    _ledger_status_claim(view)
    _files_claim(view)
    for gate in view.get("gates", []):
        _line(f"gate: {gate}")
    return view


def _r_status_draft(view: dict, *_, **__) -> dict:
    _line(f"{view.get('name', 'claim')}: draft")
    for gate in view.get("gates", []):
        _line(f"gate: {gate}")
    _line(f"next: {view.get('next', 'seal')}")
    return view


def _r_tree(result: Any, *_, **__) -> Any:
    _line(render.tree(result))
    return result


def _r_structure(result: Any, *_, **__) -> Any:
    _line(render.tree(result))
    return result


def _r_claims(rows: Any, *_, **__) -> Any:
    for row in rows if isinstance(rows, list) else rows.get("claims", []):
        _t_status_claim(row)
    return rows


def _r_deps(result: Any, *_, **__) -> Any:
    _line(render.tree(result))
    return result
