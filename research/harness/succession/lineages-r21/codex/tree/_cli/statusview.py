"""Human-readable claim, draft, dependency, and structure views."""

from __future__ import annotations

from .. import kernel
from .._util import declared_inputs
from . import report


_DECLARED_ROLE = {
    "generated": "generated",
    "free": "generated",
    "pinned": "pinned",
    "exact": "pinned",
    "validated": "validated",
}


def _t_status_claim(view):
    return f"{view.get('name', 'claim')} {view.get('phase', 'draft')}"


def _ledger_status_claim(view):
    return report._generic_contract("ledger", view.get("ledger", {}))


def _v_status_claim(view):
    return report._generic_contract("status", view)


def _files_claim(directory):
    """List declared files and their role, without including store residue."""
    parsed = kernel.load_recipe(directory)
    names = {"reticuli.toml": "recipe"}
    for name in declared_inputs(parsed, directory):
        names[name] = "input"
    for step in parsed.get("step", []):
        default = "generated" if step.get("kind") == "produce" else "pinned"
        names[step["output"]] = _DECLARED_ROLE.get(step.get("class", default), default)
    return names


def _r_status_draft(view):
    return report._generic_contract("draft", view)


def _r_tree(data):
    return report._generic_contract("tree", data)


def _r_structure(data):
    return report._generic_contract("structure", data)


def _r_claims(data):
    return report._generic_contract("claims", data)


def _r_deps(data):
    return report._generic_contract("deps", data)
