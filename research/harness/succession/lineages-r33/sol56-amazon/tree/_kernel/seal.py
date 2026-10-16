"""Seal and verify a claim's content-addressed identity.

Verification in this layer is intentionally limited to identity: it compares
freshly computed protocol bytes with the root recorded by :func:`seal`.  Gate
execution belongs to the audit/rebuild layers.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Mapping

from . import core, identity, recipe


_ROOT = re.compile(r"^[0-9a-f]{64}$")


def _manifest_path(d: str | os.PathLike[str]) -> str:
    """Return the safely resolved path of the private identity manifest."""

    return core._safe(d, core.MANIFEST)


def read_manifest(d: str | os.PathLike[str]) -> dict[str, Any]:
    """Read and validate ``.reticuli/manifest.json`` from a claim.

    The store format is private and may contain additional fields, but its
    identity-bearing ``name`` and ``root`` fields are always required.
    Claim-controlled malformed bytes are reported as :class:`ClaimError`.
    """

    try:
        path = _manifest_path(d)
        with open(path, "r", encoding="utf-8") as stream:
            value = json.load(stream)
    except core.ClaimError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise core.ClaimError(f"cannot read claim manifest: {exc}") from None

    if not isinstance(value, dict):
        raise core.ClaimError("claim manifest must be a JSON object")
    if not isinstance(value.get("name"), str):
        raise core.ClaimError("claim manifest name is required and must be a string")
    root = value.get("root")
    if not isinstance(root, str) or _ROOT.fullmatch(root) is None:
        raise core.ClaimError("claim manifest root must be 64 lowercase hex characters")
    return value


def _changed_parts(
    sealed: Mapping[str, str] | None, recomputed: Mapping[str, str] | None
) -> list[str]:
    """Return sorted component names whose identity values differ.

    This small helper is used by fuller verification reports.  A component
    present on only one side is changed as well.  ``None`` is accepted as an
    empty component map, which is useful for old manifests that carry only a
    root and no optional diagnostic component table.
    """

    left = sealed if isinstance(sealed, Mapping) else {}
    right = recomputed if isinstance(recomputed, Mapping) else {}
    return sorted(key for key in set(left) | set(right) if left.get(key) != right.get(key))


def seal(d: str | os.PathLike[str]) -> dict[str, Any]:
    """Compute a claim's root and atomically record its identity manifest."""

    parsed = recipe.load_recipe(d)
    root = identity.root(parsed, d)
    manifest: dict[str, Any] = {
        "name": parsed["claim"]["name"],
        "root": root,
    }

    try:
        store = core._safe(d, core.STORE)
        if os.path.lexists(store) and not os.path.isdir(store):
            raise core.ClaimError(f"claim store is not a directory: {core.STORE}")
        os.makedirs(store, exist_ok=True)
        core._write_json(_manifest_path(d), manifest)
    except core.ClaimError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise core.ClaimError(f"cannot write claim manifest: {exc}") from None
    return manifest


def verify(d: str | os.PathLike[str]) -> dict[str, Any]:
    """Recompute and compare a sealed claim's identity without running gates."""

    manifest = read_manifest(d)
    parsed = recipe.load_recipe(d)
    recomputed = identity.root(parsed, d)
    sealed_root = manifest["root"]

    result: dict[str, Any] = {
        "ok": recomputed == sealed_root,
        "name": manifest["name"],
        "root": sealed_root,
        "recomputed": recomputed,
    }

    # Components are optional private diagnostics.  New minimal manifests do
    # not need them, but retaining this comparison makes older/richer ones
    # useful without making their layout part of the public format.
    components = manifest.get("parts")
    if isinstance(components, dict):
        current = identity._parts(parsed, d)
        result["changed"] = _changed_parts(components, current)
    return result


ClaimError = core.ClaimError

__all__ = ["ClaimError", "_changed_parts", "read_manifest", "seal", "verify"]
