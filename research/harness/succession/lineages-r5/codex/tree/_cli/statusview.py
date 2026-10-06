"""Text views of claim status, drafts, and component listings."""

from __future__ import annotations

from .report import _row


_DECLARED_ROLE = {
    "generated": "generated",
    "pinned": "pinned",
    "validated": "validated",
}


def _t_status_claim(view):
    return f"{view.get('name', 'claim')}  {view.get('phase', 'draft')}  {view.get('root') or '-'}"


def _ledger_status_claim(view):
    cost = view.get("cost") or {}
    return "\n".join(_row(unit, amount) for unit, amount in sorted(cost.items())) or "cost: unmeasured"


def _v_status_claim(view):
    lines = [_t_status_claim(view), _row("identity", "verified" if view.get("verified") else "unverified")]
    if view.get("next"):
        lines.append(_row("next", view["next"]))
    return "\n".join(lines)


def _files_claim(view):
    files = view.get("files") or []
    return "\n".join(str(item) for item in files)


def _r_status_draft(view):
    return f"{view.get('name', 'claim')}  draft\nnext: {view.get('next', 'seal')}"


def _r_tree(data):
    if isinstance(data, dict):
        return "\n".join([str(data.get("name", "claim"))] +
                         [f"  {item.get('component', item.get('name', item))}" for item in data.get("components", [])])
    return "\n".join(str(item) for item in data)


def _r_structure(data):
    if not isinstance(data, dict):
        return str(data)
    lines = [_t_status_claim(data)]
    lines.extend(f"  {item.get('component', item.get('name', item))}" for item in data.get("components", []))
    return "\n".join(lines)


def _r_claims(data):
    rows = data.get("claims", []) if isinstance(data, dict) else data
    return "\n".join(_t_status_claim(row) for row in rows)


def _r_deps(data):
    rows = data.get("claims", []) if isinstance(data, dict) else data
    lines = []
    for row in rows:
        lines.append(_t_status_claim(row))
        lines.extend(f"  {link.get('component', '?')}: {link.get('status', 'unknown')}"
                     for link in row.get("depends_on", []))
    return "\n".join(lines)
