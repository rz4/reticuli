"""Kernel seal: freeze a claim's identity onto its manifest, and verify it.

* ``seal(d)``            -- compute the root (spec/identity.md) and write
                            ``.reticuli/manifest.json`` as ``{name, root}``.
* ``verify(d)``          -- recompute the root from the bytes present and
                            compare it with the sealed value. Identity only:
                            no gate is executed (spec/verification.md).
* ``read_manifest(d)``   -- the manifest as ``{name, root}``; malformed bytes
                            are refused with ``ClaimError``.
* ``_changed_parts(old, new)`` -- the ``parts`` keys whose values differ,
                            were added, or were removed; used to say which
                            pinned bytes moved a root.

The root is a function of the recipe and the pinned bytes only, so editing a
generated output keeps it, while editing a pinned input moves it. Stdlib only.
"""
import json
import os
import re
import stat

from reticuli._kernel import core, identity, recipe

_HEX64 = re.compile(r"[0-9a-f]{64}")


def _manifest_path(d: str) -> str:
    return os.path.join(d, core.MANIFEST)


def _claim_name(parsed: dict) -> str:
    return parsed["claim"]["name"]


def read_manifest(d: str) -> dict:
    """The sealed manifest of claim ``d``: ``{name, root}``.

    Refuses, with a reason, a missing manifest, a manifest that is not a
    regular file, bytes that are not a JSON object, a missing or non-string
    ``name``, and a ``root`` that is not 64 lowercase hex characters.
    """
    path = _manifest_path(d)
    if not os.path.lexists(path):
        raise core.ClaimError(f"no manifest in {d}: the claim is not sealed")
    st = os.lstat(path)
    if not stat.S_ISREG(st.st_mode):
        raise core.ClaimError(f"manifest is not a regular file (refused): {path}")
    try:
        with open(path, "rb") as f:
            doc = json.loads(f.read().decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as e:
        raise core.ClaimError(f"manifest is malformed: {e}")
    if not isinstance(doc, dict):
        raise core.ClaimError("manifest is not a JSON object")
    name = doc.get("name")
    if not isinstance(name, str):
        raise core.ClaimError("manifest name must be a string")
    root = doc.get("root")
    if not isinstance(root, str) or not _HEX64.fullmatch(root):
        raise core.ClaimError("manifest root must be 64 lowercase hex characters")
    return {"name": name, "root": root}


def _changed_parts(old: dict, new: dict) -> list:
    """Sorted keys of the ``parts`` maps that differ between ``old`` and ``new``.

    A key present on one side only counts as changed.
    """
    keys = set(old) | set(new)
    return sorted(k for k in keys if old.get(k) != new.get(k))


def seal(d: str) -> dict:
    """Compute the root of claim ``d`` and write it to the manifest.

    Returns the manifest written, ``{name, root}``.
    """
    parsed = recipe.load_recipe(d)
    manifest = {
        "name": _claim_name(parsed),
        "root": identity.root(parsed, d),
    }
    core._write_json(_manifest_path(d), manifest)
    return manifest


def verify(d: str) -> dict:
    """Recompute the root of claim ``d`` and compare it with the sealed one.

    Returns a dict:

    * ``ok``         -- True iff the claim is sealed and the bytes present
                        still hash to the sealed root;
    * ``root``       -- the root recomputed from the bytes present;
    * ``recomputed`` -- the same value, stated under its own name;
    * ``sealed``     -- the manifest's root, or None if the claim is unsealed.

    A recipe that cannot be loaded is refused with ``ClaimError``.
    """
    parsed = recipe.load_recipe(d)
    recomputed = identity.root(parsed, d)
    sealed = None
    if os.path.lexists(_manifest_path(d)):
        sealed = read_manifest(d)["root"]
    return {
        "ok": sealed is not None and sealed == recomputed,
        "root": recomputed,
        "recomputed": recomputed,
        "sealed": sealed,
    }
