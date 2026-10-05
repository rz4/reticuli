"""Text views of draft, sealed, and composed claims."""

from __future__ import annotations

import os
from collections.abc import Mapping

from . import views
from .report import _row, _value


_DECLARED_ROLE = {
    "generated": "generated",
    "pinned": "pinned",
    "validated": "validated",
}


def _view(value):
    return value if isinstance(value, Mapping) else views._claim_view(value)


def _t_status_claim(value):
    """One-line status for a claim."""
    claim = _view(value)
    root = claim.get("root")
    suffix = f" {str(root)[:12]}" if root else ""
    return f"{claim.get('name', 'claim')}: {claim.get('phase', 'draft')} — {claim.get('verdict', 'unknown')}{suffix}"


def _ledger_status_claim(value):
    claim = _view(value)
    return _row("cost", claim.get("cost"))


def _files_claim(value):
    claim = _view(value)
    generated = claim.get("generated") or {}
    lines = []
    for name in generated.get("present", []):
        lines.append(f"present: {name}")
    for name in generated.get("missing", []):
        lines.append(f"missing: {name}")
    return "\n".join(lines) if lines else "generated: none"


def _v_status_claim(value):
    claim = _view(value)
    lines = [_t_status_claim(claim), _row("path", claim.get("path")),
             _row("root", claim.get("root")),
             _row("identity verified", claim.get("verified")),
             _files_claim(claim), _ledger_status_claim(claim),
             _row("next", claim.get("next"))]
    if claim.get("audit") is not None:
        lines.append(_row("audit", claim["audit"].get("verdict") if isinstance(claim["audit"], Mapping) else claim["audit"]))
    if claim.get("proof") is not None:
        lines.append(_row("proof", claim["proof"]))
    if claim.get("signatures"):
        lines.append(_row("signatures", claim["signatures"]))
    return "\n".join(lines)


def _r_status_draft(value):
    """A draft has no sealed root yet."""
    if isinstance(value, Mapping):
        name = value.get("name") or os.path.basename(os.fspath(value.get("path", ".")))
    else:
        name = os.path.basename(os.path.abspath(os.fspath(value)))
    return f"{name}: draft — unsealed\nnext: seal"


def _r_claims(value):
    claims = value.get("claims", []) if isinstance(value, Mapping) else value
    if not claims:
        return "no claims"
    return "\n".join(_t_status_claim(claim) for claim in claims)


def _r_deps(value):
    claims = value.get("claims", []) if isinstance(value, Mapping) else value
    lines = []
    for claim in claims:
        lines.append(_t_status_claim(claim))
        for edge in claim.get("depends_on", []):
            lines.append(f"  {edge.get('component', '?')}: {edge.get('status', 'unknown')}")
    return "\n".join(lines) if lines else "no dependencies"


def _r_tree(value):
    """Render nested component links in a stable, readable order."""
    if isinstance(value, Mapping):
        name = value.get("name", "claim")
        children = value.get("components", value.get("depends_on", []))
        lines = [str(name)]
        for child in children:
            lines.append(f"  {child.get('component', child.get('name', '?'))} {str(child.get('root', ''))[:12]}".rstrip())
        return "\n".join(lines)
    if isinstance(value, (list, tuple)):
        return "\n".join(_r_tree(item) for item in value)
    return str(value)


def _r_structure(value):
    return _r_tree(value)
