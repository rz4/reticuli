"""The kernel's seal layer: freeze identity onto the manifest, and verify the bytes still hash to it."""
import hashlib
import json
import os

from .core import (
    DIGEST,
    MANIFEST,
    STORE,
    ClaimError,
    _now,
    _write_json,
)
from .identity import (  # noqa: F401
    _parts,
    root,
)
from .recipe import (  # noqa: F401
    gates,
    load_recipe,
)

# -------------------------------------------------------- manifest and seal

def read_manifest(claimdir: str) -> dict:
    """The sealed manifest, or a refusal.  Damaged residue is never data."""
    path = os.path.join(claimdir, MANIFEST)
    if not os.path.isfile(path):
        raise ClaimError(f"no manifest at {path}: the claim is not sealed")
    try:
        with open(path, "rb") as f:
            manifest = json.loads(f.read().decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise ClaimError(f"damaged manifest {path}: {exc}") from None
    if not isinstance(manifest, dict):
        raise ClaimError(f"damaged manifest {path}: not an object")
    if not isinstance(manifest.get("name"), str):
        raise ClaimError(f"damaged manifest {path}: name is not a string")
    stored = manifest.get("root")
    if stored is not None and not isinstance(stored, str):
        raise ClaimError(f"damaged manifest {path}: root is not a string")
    return manifest


def seal(claimdir: str) -> dict:
    """Freeze the claim's identity onto its manifest.

    Sealing computes the root and records it.  It does not run gates: the
    verdicts belong to `audit`, which earns them, and a seal that re-ran the
    gates in place would overwrite the very pinned bytes it is meant to fix.
    """
    recipe = load_recipe(claimdir)
    parts = _parts(recipe, claimdir)
    computed = hashlib.sha256(
        json.dumps(parts, sort_keys=True).encode("utf-8")).hexdigest()
    manifest = {}
    if os.path.isfile(os.path.join(claimdir, MANIFEST)):
        try:
            manifest = read_manifest(claimdir)
        except ClaimError:
            manifest = {}                 # a wreck is replaced, not trusted
    manifest.update({
        "name": recipe["claim"]["name"],
        "digest": DIGEST,
        "root": computed,
        "sealed": _now(),
    })
    _write_json(os.path.join(claimdir, MANIFEST), manifest)
    # RESIDUE, never identity: the preimage parts, so a later broken verify
    # can NAME which pinned file moved instead of shrugging two hex strings.
    # Untrusted on read -- verify uses it only after re-deriving the sealed
    # root from it, so a stale or tampered copy is ignored, not believed.
    _write_json(os.path.join(claimdir, STORE, "parts.json"), parts)
    return manifest


def verify(claimdir: str) -> dict:
    """Does the claim still hash to what was sealed?

    This is the shallow check -- identity, not verdict.  `root` is the sealed
    identity, `recomputed` is what the bytes on disk say now.  A generated
    rebuild keeps them equal; an edited input moves them apart.
    """
    recipe = load_recipe(claimdir)
    manifest = read_manifest(claimdir)
    now_parts = _parts(recipe, claimdir)
    recomputed = hashlib.sha256(
        json.dumps(now_parts, sort_keys=True).encode("utf-8")).hexdigest()
    stored = manifest.get("root")
    out = {
        "ok": isinstance(stored, str) and stored == recomputed,
        "root": stored,
        "recomputed": recomputed,
        "name": manifest.get("name"),
        "claim": os.path.abspath(claimdir),
    }
    if not out["ok"]:
        out["changed"] = _changed_parts(claimdir, stored, now_parts)
    return out


def _changed_parts(claimdir: str, sealed_root, now_parts: dict) -> list | None:
    """Which preimage parts moved, by name -- or None when it cannot be said.

    The parts residue written at seal time is UNTRUSTED: it is used only if
    hashing it reproduces the sealed root exactly, so a stale or edited copy
    names nothing. With a valid copy, the diff of sealed parts against the
    parts recomputed now is precisely the set of moved criteria."""
    try:
        with open(os.path.join(claimdir, STORE, "parts.json"),
                  encoding="utf-8") as f:
            sealed = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(sealed, dict):
        return None
    derived = hashlib.sha256(
        json.dumps(sealed, sort_keys=True).encode("utf-8")).hexdigest()
    if derived != sealed_root:
        return None                       # stale or tampered: name nothing
    moved = sorted(set(sealed) ^ set(now_parts)
                   | {k for k in set(sealed) & set(now_parts)
                      if sealed[k] != now_parts[k]})
    names = []
    for key in moved:
        if key == "recipe":
            names.append("reticuli.toml (the recipe)")
        elif key.startswith(("input:", "pinned:")):
            names.append(key.split(":", 1)[1])
        else:
            names.append(key)
    return sorted(names)
