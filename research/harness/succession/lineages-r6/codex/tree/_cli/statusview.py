"""Text views of claim and workspace state."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from reticuli import kernel
from reticuli.render import short
from .report import _row, _value


_DECLARED_ROLE = {
    "generated": "generated",
    "free": "generated",
    "pinned": "pinned",
    "exact": "pinned",
    "validated": "validated",
}


def _t_status_claim(view: Mapping[str, Any]) -> str:
    """One line suitable for a list of claims."""
    root = short(view["root"]) if view.get("root") else "unsealed"
    return f"{view.get('name', '?')} {root} {view.get('phase', 'draft')}"


def _ledger_status_claim(view: Mapping[str, Any]) -> str:
    """Summarize the stored evidence without running a gate."""
    lines = [_t_status_claim(view)]
    for key in ("verdict", "next", "gate_ok", "proof", "signatures"):
        if key in view:
            lines.append(_row(key.replace("_", " "), view[key]))
    return "\n".join(lines)


def _v_status_claim(view: Mapping[str, Any]) -> str:
    """Verbose status including identity and the next action."""
    lines = [_ledger_status_claim(view)]
    if "verified" in view:
        lines.append(_row("identity verified", view["verified"]))
    return "\n".join(lines)


def _files_claim(directory: str) -> str:
    """List the recipe's declared files and their roles."""
    recipe = kernel.load_recipe(directory)
    lines = []
    for name in recipe["claim"].get("inputs", []):
        lines.append(f"input      {name}")
    for step in recipe.get("step", []):
        default = "generated" if step["kind"] == "produce" else "pinned"
        role = _DECLARED_ROLE.get(step.get("class", default), default)
        lines.append(f"{role:<10} {step['output']}")
    return "\n".join(lines)


def _r_status_draft(view: Mapping[str, Any]) -> str:
    return f"{view.get('name', '?')}: draft\nnext: seal"


def _r_claims(result: Any) -> str:
    rows = result.get("claims", []) if isinstance(result, Mapping) else result
    return "\n".join(_t_status_claim(row) for row in rows)


def _r_deps(result: Any) -> str:
    rows = result.get("claims", []) if isinstance(result, Mapping) else result
    lines = []
    for row in rows:
        lines.append(_t_status_claim(row))
        for link in row.get("depends_on", []):
            lines.append(f"  {link.get('component', '?')} {short(link.get('root', '?'))} {link.get('status', 'unresolved')}")
    return "\n".join(lines)


def _r_structure(result: Any) -> str:
    return _r_deps(result)


def _r_tree(result: Any) -> str:
    return _r_deps(result)
