"""Render claim status, draft, dependency, and structure views.

The view layer deliberately accepts ordinary mappings rather than importing a
particular command parser.  Functions return strings and have no terminal side
effects, which keeps terse, verbose, and JSON command paths separable.
"""
from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from typing import Any

from reticuli import kernel
from reticuli.render import short

from .report import _row


# Human explanations for the role a recipe declaration gives to a file.
_DECLARED_ROLE = {
    "recipe": "recipe",
    "input": "pinned input",
    "pinned": "pinned output",
    "validated": "gate verdict",
    "generated": "generated output",
    "free": "generated output",
    "component": "component output",
    "residue": "local residue",
}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _phase(value: Mapping[str, Any]) -> str:
    phase = value.get("phase")
    return str(phase) if phase else "draft"


def _root(value: Mapping[str, Any], width: int = 12) -> str:
    root = value.get("root")
    return short(root, width) if root else "-"


def _t_status_claim(view: Any) -> str:
    """Render one claim as a stable, tab-separated terse status row."""
    value = _mapping(view)
    name = value.get("name") or os.path.basename(os.fspath(value.get("path", ".")))
    return "\t".join((str(name), _root(value), _phase(value)))


def _ledger_status_claim(view: Any) -> str:
    """Render lifecycle facts in a compact ledger-like sentence."""
    value = _mapping(view)
    name = value.get("name", "claim")
    phase = _phase(value)
    root = _root(value)
    deciding = value.get("deciding")
    if isinstance(deciding, Sequence) and not isinstance(deciding, (str, bytes)):
        reason = "; ".join(str(item) for item in deciding)
    else:
        reason = str(deciding) if deciding else phase
    return f"{name} {root} {phase} — {reason}"


def _v_status_claim(view: Any) -> str:
    """Render the complete readable status of one claim."""
    value = _mapping(view)
    rows = [str(value.get("name", "claim"))]
    if value.get("path") is not None:
        rows.append(_row("path", value["path"]))
    rows.extend((_row("phase", _phase(value)), _row("root", value.get("root"))))
    if value.get("error"):
        rows.append(_row("error", value["error"]))
    verification = value.get("verification")
    if isinstance(verification, Mapping):
        rows.append(_row("identity", "holds" if verification.get("ok") else "mismatch"))
        if not verification.get("ok") and verification.get("recomputed"):
            rows.append(_row("recomputed", verification["recomputed"]))
    elif "verified" in value:
        rows.append(_row("identity", "holds" if value.get("verified") else "unverified"))
    audit = value.get("audit")
    if isinstance(audit, Mapping):
        rows.append(_row("audit", audit.get("verdict", "earned" if audit.get("ok") else "broken")))
    proof = value.get("proof")
    rows.append(_row("proof", "recorded" if proof else "none"))
    signatures = value.get("signatures")
    if isinstance(signatures, Mapping):
        if signatures.get("trusted"):
            signature = "trusted"
        elif signatures.get("present"):
            signature = "present, untrusted"
        else:
            signature = "none"
        rows.append(_row("signature", signature))
        if signatures.get("identities"):
            rows.append(_row("signers", signatures["identities"]))
    if value.get("cost") is not None:
        rows.append(_row("cost", value["cost"]))
    if value.get("mutation_score") is not None:
        rows.append(_row("mutation score", value["mutation_score"]))
    if value.get("next"):
        rows.append(_row("next", value["next"]))
    return "\n".join(rows)


def _declared_files(recipe: Mapping[str, Any], directory: Any = None) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    recipe_name = kernel.RECIPE
    if directory is not None:
        canonical = os.path.join(os.fspath(directory), kernel.RECIPE)
        recipe_name = kernel.RECIPE if os.path.isfile(canonical) else "claim.toml"
    rows.append({"path": recipe_name, "role": "recipe"})
    claim = recipe.get("claim", {})
    if isinstance(claim, Mapping):
        inputs = claim.get("inputs", [])
        if isinstance(inputs, list):
            rows.extend({"path": str(name), "role": "input"} for name in inputs)
        manifest = claim.get("inputs_manifest")
        if isinstance(manifest, str):
            rows.append({"path": manifest, "role": "input"})
        environment = claim.get("environment")
        if isinstance(environment, str):
            rows.append({"path": environment, "role": "input"})
    steps = recipe.get("step", [])
    if isinstance(steps, list):
        for step in steps:
            if not isinstance(step, Mapping) or not isinstance(step.get("output"), str):
                continue
            if step.get("kind") == "gate":
                role = "validated"
            elif "from" in step:
                role = "component"
            else:
                role = str(step.get("class", "generated"))
            rows.append({"path": step["output"], "role": role})
    # First declaration wins, matching the recipe query helpers.
    unique: dict[str, dict[str, str]] = {}
    for row in rows:
        unique.setdefault(row["path"], row)
    return list(unique.values())


def _files_claim(view: Any, recipe: Any = None, directory: Any = None) -> str:
    """Render declared files, their roles, and optional presence.

    Callers may pass a claim view followed by a recipe, or simply a recipe.
    A view carrying a ``files`` sequence is also accepted.
    """
    first = _mapping(view)
    if recipe is None and "claim" in first:
        parsed = first
        claim_view: Mapping[str, Any] = {}
    else:
        parsed = _mapping(recipe)
        claim_view = first
    directory = directory if directory is not None else claim_view.get("path")
    supplied = claim_view.get("files")
    if isinstance(supplied, Sequence) and not isinstance(supplied, (str, bytes)):
        declared = list(supplied)
    else:
        declared = _declared_files(parsed, directory) if parsed else []
    lines = []
    for item in declared:
        if isinstance(item, Mapping):
            path = str(item.get("path", item.get("name", "?")))
            role = str(item.get("role", item.get("class", "input")))
            present = item.get("present")
        else:
            path, role, present = str(item), "input", None
        if present is None and directory is not None:
            present = os.path.isfile(os.path.join(os.fspath(directory), path))
        state = "present" if present is True else "absent" if present is False else "declared"
        lines.append(f"{path}\t{_DECLARED_ROLE.get(role, role)}\t{state}")
    return "\n".join(lines)


def _r_status_draft(view: Any, verbose: bool = False) -> str:
    """Render an unsealed workspace or authoring proposal."""
    value = _mapping(view)
    name = value.get("name")
    claim = value.get("claim")
    if name is None and isinstance(claim, Mapping):
        name = claim.get("name")
    rows = [f"{name or 'claim'}: draft"]
    if value.get("path"):
        rows.append(_row("path", value["path"]))
    if value.get("error"):
        rows.append(_row("error", value["error"]))
    for key in ("events", "prompts", "gates", "writes"):
        if key in value:
            rows.append(_row(key, value[key]))
    if value.get("sealable") is not None:
        rows.append(_row("sealable", value["sealable"]))
    if value.get("reason"):
        rows.append(_row("reason", value["reason"]))
    if value.get("next"):
        rows.append(_row("next", value["next"]))
    if verbose and value.get("recipe"):
        rows.append(_row("recipe", json.dumps(value["recipe"], sort_keys=True,
                                                ensure_ascii=False)))
    return "\n".join(rows)


def _node_label(node: Mapping[str, Any]) -> str:
    name = node.get("name", node.get("component", "claim"))
    root = node.get("root")
    phase = node.get("phase") or node.get("status")
    bits = [str(name)]
    if root:
        bits.append(short(root, 12))
    if phase:
        bits.append(f"[{phase}]")
    return " ".join(bits)


def _tree_lines(node: Any, prefix: str = "", last: bool = True,
                root: bool = True, seen: set[Any] | None = None) -> list[str]:
    seen = seen if seen is not None else set()
    if isinstance(node, Mapping):
        marker = node.get("root") or (node.get("name"), node.get("component"))
        label = _node_label(node)
    else:
        marker, label = None, str(node)
    branch = "" if root else ("└── " if last else "├── ")
    lines = [prefix + branch + label]
    if marker is not None and marker in seen:
        lines[-1] += " (already shown)"
        return lines
    if marker is not None:
        seen.add(marker)
    children: list[Any] = []
    if isinstance(node, Mapping):
        for key in ("components", "depends_on", "children", "layers"):
            value = node.get(key)
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                children = list(value)
                break
    child_prefix = prefix if root else prefix + ("    " if last else "│   ")
    for index, child in enumerate(children):
        lines.extend(_tree_lines(child, child_prefix, index == len(children)-1,
                                 False, seen))
    return lines


def _r_tree(value: Any) -> str:
    """Render a claim/component hierarchy using deterministic tree branches."""
    if isinstance(value, Mapping) and isinstance(value.get("claims"), list):
        roots = value["claims"]
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        roots = list(value)
    else:
        roots = [value]
    lines: list[str] = []
    seen: set[Any] = set()
    for index, root in enumerate(roots):
        lines.extend(_tree_lines(root, "", index == len(roots)-1, True, seen))
    return "\n".join(lines)


def _r_structure(value: Any, verbose: bool = False) -> str:
    """Render one claim and its direct component declarations."""
    node = _mapping(value)
    rows = [_node_label(node)]
    components = node.get("components", [])
    if isinstance(components, Sequence) and not isinstance(components, (str, bytes)):
        for component in components:
            if isinstance(component, Mapping):
                label = component.get("component", component.get("name", "component"))
                root = short(component.get("root", "-"), 12)
                relation = []
                if component.get("output"):
                    relation.append(str(component["output"]))
                if component.get("input") and component.get("input") != component.get("output"):
                    relation.append("→ " + str(component["input"]))
                suffix = " " + " ".join(relation) if relation else ""
                rows.append(f"  {label} {root}{suffix}")
                if verbose and component.get("status"):
                    rows.append(_row("status", component["status"], indent=4))
            else:
                rows.append("  " + str(component))
    return "\n".join(rows)


def _r_claims(value: Any, verbose: bool = False) -> str:
    """Render a registry claim listing."""
    if isinstance(value, Mapping):
        claims = value.get("claims", [])
    else:
        claims = value
    if not isinstance(claims, Sequence) or isinstance(claims, (str, bytes)):
        return ""
    rows = []
    for claim in claims:
        if isinstance(claim, Mapping):
            rows.append(_v_status_claim(claim) if verbose else _t_status_claim(claim))
        else:
            rows.append(str(claim))
    return "\n\n".join(rows) if verbose else "\n".join(rows)


def _r_deps(value: Any, verbose: bool = False) -> str:
    """Render dependency edges, preserving registry order."""
    data = _mapping(value)
    claims = data.get("claims", value if isinstance(value, list) else [])
    if not isinstance(claims, Sequence) or isinstance(claims, (str, bytes)):
        return ""
    rows: list[str] = []
    for claim in claims:
        if not isinstance(claim, Mapping):
            continue
        name = claim.get("name", "claim")
        dependencies = claim.get("depends_on", [])
        if not dependencies:
            rows.append(f"{name}\t-")
            continue
        for dependency in dependencies:
            if isinstance(dependency, Mapping):
                target = dependency.get("component", dependency.get("name", "?"))
                status = dependency.get("status", "unknown")
                line = f"{name}\t{target}\t{status}"
                if verbose and dependency.get("root"):
                    line += "\t" + str(dependency["root"])
                rows.append(line)
            else:
                rows.append(f"{name}\t{dependency}")
    return "\n".join(rows)


__all__ = [
    "_DECLARED_ROLE", "_files_claim", "_ledger_status_claim", "_r_claims",
    "_r_deps", "_r_status_draft", "_r_structure", "_r_tree",
    "_t_status_claim", "_v_status_claim",
]
