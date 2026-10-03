"""Sealing and verifying a claim's identity (spec/identity.md,
spec/verification.md).

`seal` computes the root from the bytes present and writes it onto
`.reticuli/manifest.json`. `verify` recomputes the root from the bytes
present now and compares it with the sealed manifest -- identity only, no
gate is executed (spec/verification.md: the `verify`/`audit` division).
`read_manifest` reads that file back, refusing malformed bytes rather than
crashing. `_changed_parts` is the diagnostic behind a failed verify: which
named preimage part (the recipe, a pinned input, a pinned output) differs
from what was sealed.
"""
import hashlib
import json
import os

from . import core
from . import identity
from . import recipe as _recipe
from .core import ClaimError


def seal(d: str) -> dict:
    """Freeze `d` into a claim: compute the root from its pinned bytes and
    write `.reticuli/manifest.json`. The manifest carries `name` and `root`
    (spec/claim-format.md, "The store"), plus the preimage `parts` as
    residue so a later `verify` can name exactly what changed.
    """
    parsed = _recipe.load_recipe(d)
    parts = identity._parts(parsed, d)
    root = hashlib.sha256(identity._canonical_json(parts).encode("utf-8")).hexdigest()

    manifest = {"name": parsed["claim"]["name"], "root": root, "parts": parts}
    os.makedirs(os.path.join(d, core.STORE), exist_ok=True)
    core._write_json(_manifest_path(d), manifest)
    return manifest


def verify(d: str) -> dict:
    """Recompute the root from the bytes present now and compare it with
    the sealed manifest. Never runs a gate. `ok` is the identity
    comparison; `root` is the sealed value, `recomputed` the fresh one --
    equal when `ok`, different (or `None`, on a refusal while recomputing)
    when not.
    """
    manifest = read_manifest(d)
    try:
        parsed = _recipe.load_recipe(d)
        recomputed = identity.root(parsed, d)
    except ClaimError:
        recomputed = None

    ok = recomputed is not None and recomputed == manifest["root"]
    return {
        "ok": ok,
        "name": manifest.get("name"),
        "root": manifest["root"],
        "recomputed": recomputed,
    }


def read_manifest(d: str) -> dict:
    """Read `.reticuli/manifest.json` back. Refuses, with a reason, bytes
    that are not a JSON object, or that lack a string `name` or a 64-lowercase-hex
    `root` (the manifest is untrusted-on-disk state, like the recipe).
    """
    path = _manifest_path(d)
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError as exc:
        raise ClaimError(f"no sealed manifest in {d!r}: {exc}") from exc

    try:
        manifest = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ClaimError(f"malformed manifest {path!r}: {exc}") from exc

    if not isinstance(manifest, dict):
        raise ClaimError(f"malformed manifest {path!r}: not an object")

    name = manifest.get("name")
    if not isinstance(name, str):
        raise ClaimError(f"manifest {path!r}: name must be a string")

    root = manifest.get("root")
    if (
        not isinstance(root, str)
        or len(root) != 64
        or any(c not in "0123456789abcdef" for c in root)
    ):
        raise ClaimError(f"manifest {path!r}: root must be 64 lowercase hex characters")

    return manifest


def _changed_parts(d: str) -> dict:
    """Which named preimage parts (`spec/identity.md`: `digest`, `recipe`,
    `input:<path>`, `pinned:<path>`) differ between the sealed manifest and
    the bytes present now -- the diagnostic behind a failed `verify`, never
    itself used to decide pass or fail. A key present only at one end
    (an input added or removed) maps to `None` on the missing side; a
    manifest sealed without a `parts` snapshot reports every current part
    as changed, since nothing is known about what was sealed.
    """
    manifest = read_manifest(d)
    sealed = manifest.get("parts", {})

    parsed = _recipe.load_recipe(d)
    current = identity._parts(parsed, d)

    changed = {}
    for key in sorted(set(sealed) | set(current)):
        was = sealed.get(key)
        now = current.get(key)
        if was != now:
            changed[key] = {"was": was, "now": now}
    return changed


def _manifest_path(d: str) -> str:
    return os.path.join(d, core.MANIFEST)
