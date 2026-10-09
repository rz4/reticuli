"""Text views of claim status, files, and dependency structure."""

from __future__ import annotations

from typing import Any

from .report import _generic_contract, _row


_DECLARED_ROLE = {
    "generated": "generated",
    "pinned": "pinned",
    "validated": "validated",
}


def _t_status_claim(view: dict[str, Any]) -> str:
    """One line suitable for a terse claims listing."""
    name = view.get("name", "claim")
    phase = view.get("phase", "draft")
    root = view.get("root")
    return f"{name} {phase}" + (f" {root[:12]}" if root else "")


def _ledger_status_claim(view: dict[str, Any]) -> str:
    return _generic_contract("ledger", view.get("ledger") or view.get("cost"))


def _v_status_claim(view: dict[str, Any]) -> str:
    """Expanded local evidence for one claim."""
    return _generic_contract("status", view)


def _files_claim(view: dict[str, Any]) -> str:
    files = view.get("files", [])
    if isinstance(files, dict):
        return "\n".join(_row(name, role) for name, role in files.items())
    return "\n".join(map(str, files))


def _r_status_draft(view: dict[str, Any]) -> str:
    return _generic_contract("draft", view)


def _r_tree(result: Any = None) -> str:
    return _generic_contract("tree", result)


def _r_structure(result: Any = None) -> str:
    return _generic_contract("structure", result)


def _r_claims(result: Any = None) -> str:
    return _generic_contract("claims", result)


def _r_deps(result: Any = None) -> str:
    return _generic_contract("deps", result)
