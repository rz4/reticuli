"""Status, draft, dependency, and file views for the command line."""

from __future__ import annotations

import os
from typing import Any

from .report import _row


_DECLARED_ROLE = {
    "generated": "generated",
    "pinned": "pinned",
    "validated": "validated",
    "free": "generated",
    "exact": "pinned",
}


def _t_status_claim(view: dict[str, Any]) -> str:
    """One-line claim status suitable for a list."""
    return " ".join(str(value) for value in
                    (view.get("phase", "draft"), view.get("name", "?"),
                     str(view.get("root") or "-")[:12]))


def _ledger_status_claim(value: Any) -> str:
    if isinstance(value, dict):
        return "\n".join(_row(key, value[key]) for key in sorted(value))
    if isinstance(value, list):
        return "\n".join(_ledger_status_claim(item) for item in value)
    return _row("ledger", value)


def _v_status_claim(view: dict[str, Any]) -> str:
    lines = [_t_status_claim(view)]
    for key in ("path", "verified", "verdict", "proof", "signatures", "next"):
        if key in view:
            lines.append(_row(key, view[key]))
    return "\n".join(lines)


def _files_claim(recipe: dict[str, Any], directory: str | os.PathLike[str] | None = None) -> str:
    """List declared files and their roles, including missing outputs."""
    lines = []
    claim = recipe.get("claim", {})
    for name in claim.get("inputs", []):
        lines.append(_row(name, "input"))
    for key in ("inputs_manifest", "environment"):
        if key in claim:
            lines.append(_row(claim[key], key))
    for step in recipe.get("step", []):
        name = step.get("output", "?")
        role = step.get("class", "generated" if step.get("kind") == "produce" else "pinned")
        role = _DECLARED_ROLE.get(role, role)
        if directory is not None and not os.path.isfile(os.path.join(directory, name)):
            role += " (absent)"
        lines.append(_row(name, role))
    return "\n".join(lines)


def _r_status_draft(view: dict[str, Any]) -> str:
    return "\n".join((_t_status_claim(view), _row("next", view.get("next", "seal the claim"))))


def _r_tree(data: Any) -> str:
    if isinstance(data, dict):
        if "claims" in data:
            return "\n".join(_r_tree(row) for row in data["claims"])
        title = str(data.get("name", data.get("component", data.get("root", "claim"))))
        children = data.get("components", data.get("depends_on", []))
        return "\n".join([title, *("  " + line for child in children
                                   for line in _r_tree(child).splitlines())])
    if isinstance(data, list):
        return "\n".join(_r_tree(row) for row in data)
    return str(data)


def _r_structure(data: dict[str, Any]) -> str:
    lines = [_row("root", data.get("root")), _row("phase", data.get("phase"))]
    lines.extend(_r_tree(child) for child in data.get("components", []))
    return "\n".join(lines)


def _r_claims(data: Any) -> str:
    rows = data.get("claims", []) if isinstance(data, dict) else data
    return "\n".join(_t_status_claim(row) for row in rows)


def _r_deps(data: Any) -> str:
    return _r_tree(data)
