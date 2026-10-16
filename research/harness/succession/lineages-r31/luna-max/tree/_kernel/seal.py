"""Sealing and checking the identity recorded for a claim.

A manifest stores the claim's human-readable name and its root digest.  The
root itself is computed by :mod:`reticuli._kernel.identity`; generated output
bytes are consequently not part of :func:`verify`'s comparison.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from typing import Any

from . import core, identity, recipe


_ROOT_RE = re.compile(r"^[0-9a-f]{64}$")
_MISSING = object()


def _changed_parts(before: Mapping[str, Any], after: Mapping[str, Any]) -> list[str]:
    """Return the sorted keys whose values differ between two part maps.

    Identity preimages are maps of named parts.  Comparing their entries is a
    useful diagnostic when two preimages are available; the manifest itself
    intentionally stores only the final root, not a snapshot of those parts.
    """
    if not isinstance(before, Mapping) or not isinstance(after, Mapping):
        raise core.ClaimError("identity parts must be mappings")
    try:
        keys = set(before) | set(after)
        return sorted(
            key for key in keys
            if before.get(key, _MISSING) != after.get(key, _MISSING)
        )
    except (TypeError, ValueError) as exc:
        raise core.ClaimError(f"invalid identity parts: {exc}") from exc


def _manifest_path(directory: os.PathLike[str] | str) -> str:
    """Resolve the manifest without allowing a symlinked store path."""
    return core._safe(directory, core.MANIFEST)


def read_manifest(directory: os.PathLike[str] | str) -> dict[str, Any]:
    """Read and minimally validate ``.reticuli/manifest.json``.

    Optional manifest residue (such as a recorded proof or component links) is
    preserved and returned, but the identity-bearing ``name`` and ``root``
    members must always be present and well-formed.
    """
    path = _manifest_path(directory)
    try:
        with open(path, "rb") as stream:
            raw = stream.read()
        document = json.loads(raw.decode("utf-8"))
    except core.ClaimError:
        raise
    except Exception as exc:
        raise core.ClaimError(f"cannot read manifest {path!r}: {exc}") from exc

    if not isinstance(document, dict):
        raise core.ClaimError("manifest must be a JSON object")
    if not isinstance(document.get("name"), str):
        raise core.ClaimError("manifest 'name' must be a string")
    root = document.get("root")
    if not isinstance(root, str) or _ROOT_RE.fullmatch(root) is None:
        raise core.ClaimError(
            "manifest 'root' must be a 64-character lowercase SHA-256 digest"
        )
    return document


def seal(directory: os.PathLike[str] | str) -> dict[str, str]:
    """Compute a claim's root and write its identity manifest.

    Recipe parsing and all file hashing are delegated to the kernel's shared
    recipe and identity implementations so sealing uses exactly the same
    canonical preimage as every other identity operation.
    """
    parsed = recipe.load_recipe(directory)
    claim = recipe._claim_table(parsed)
    root = identity.root(parsed, directory)
    manifest = {"name": claim["name"], "root": root}

    # Resolve before writing so a pre-existing symlink anywhere in the store
    # path is refused rather than followed.
    path = _manifest_path(directory)
    core._write_json(path, manifest)
    return manifest


def verify(directory: os.PathLike[str] | str) -> dict[str, Any]:
    """Recompute the claim identity and compare it with its sealed root.

    Verification is deliberately an identity check only: it hashes declared
    pinned files but does not execute gates.  The returned ``root`` is the
    value carried by the manifest; ``recomputed`` is the value derived from
    the recipe and bytes currently present.
    """
    manifest = read_manifest(directory)
    parsed = recipe.load_recipe(directory)
    recomputed = identity.root(parsed, directory)
    sealed_root = manifest["root"]
    return {
        "ok": recomputed == sealed_root,
        "root": sealed_root,
        "recomputed": recomputed,
    }
