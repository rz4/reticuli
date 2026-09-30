"""Terminal views of claims, drafts, and dependency structures."""

from __future__ import annotations

from .report import _row


_DECLARED_ROLE = {
    "generated": "generated output",
    "free": "generated output",
    "pinned": "pinned output",
    "exact": "pinned output",
    "validated": "gate verdict",
}


def _lines(data):
    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        return "\n".join(_row(key, value) for key, value in data.items())
    if isinstance(data, (list, tuple)):
        return "\n".join(str(item) for item in data)
    return str(data)


def _t_status_claim(view):
    """A compact claim status for a normal terminal view."""
    if not isinstance(view, dict):
        return _lines(view)
    name = view.get("name", "claim")
    phase = view.get("phase", "unknown")
    root = view.get("root")
    return " ".join(str(item) for item in (name, phase, root[:12] if root else None)
                    if item is not None)


def _ledger_status_claim(view):
    return _lines(view.get("ledger", {}) if isinstance(view, dict) else view)


def _v_status_claim(view):
    return _lines(view)


def _files_claim(view):
    if not isinstance(view, dict):
        return _lines(view)
    generated = view.get("generated", [])
    missing = set(view.get("missing_generated", []))
    return "\n".join(_row(path, "absent" if path in missing else "present")
                     for path in generated)


def _r_status_draft(view):
    if not isinstance(view, dict):
        return _lines(view)
    return "\n".join((_t_status_claim(view), _row("next", view.get("next", "seal"))))


def _r_tree(tree):
    return _lines(tree)


def _r_structure(structure):
    return _lines(structure)


def _r_claims(claims):
    if isinstance(claims, (list, tuple)):
        return "\n".join(_t_status_claim(claim) for claim in claims)
    return _lines(claims)


def _r_deps(dependencies):
    return _lines(dependencies)
