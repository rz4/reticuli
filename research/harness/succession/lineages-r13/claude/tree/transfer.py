"""Transfer: deterministic export, verify-on-import, volatile history
stays home (spec/layers.md's exchange layer).

`export` walks a claim's OWN declared content -- its recipe, its pinned
inputs, its step outputs -- never the working tree, so a stray file never
rides along and two exports of the same claim are byte-identical. A
dependency component always travels blind (its claim, never its generated
bytes) under `.reticuli/deps/<name>/`, regardless of the top claim's own
`blind` flag. `import_` extracts and reseals, so identity is recomputed
from received bytes rather than trusted from the wire.
"""
import os
import tarfile

from . import kernel
from . import registry


def _recipe_filename(d: str) -> str:
    if os.path.isfile(os.path.join(d, "reticuli.toml")):
        return "reticuli.toml"
    if os.path.isfile(os.path.join(d, "claim.toml")):
        return "claim.toml"
    raise kernel.ClaimError(f"no recipe found in {d!r}")


def _declared_inputs(recipe: dict, d: str) -> list:
    claim = recipe.get("claim", {}) or {}
    manifest_name = claim.get("inputs_manifest")
    if manifest_name:
        entries = [manifest_name]
        path = os.path.join(d, manifest_name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError:
            return entries
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            head, _, rest = line.partition(" ")
            rest = rest.strip()
            if rest and len(head) == 64 and all(c in "0123456789abcdef" for c in head):
                entries.append(rest)
            else:
                entries.append(line)
        return entries
    entries = list(claim.get("inputs", []) or [])
    env_file = claim.get("environment")
    if env_file:
        entries.append(env_file)
    return entries


def _collect_export_entries(claim_dir: str, blind: bool, top: bool, prefix: str = ""):
    recipe = kernel.load_recipe(claim_dir)
    recipe_name = _recipe_filename(claim_dir)
    entries = [(prefix + recipe_name, os.path.join(claim_dir, recipe_name))]

    for p in _declared_inputs(recipe, claim_dir):
        full = os.path.join(claim_dir, p)
        if os.path.isfile(full):
            entries.append((prefix + p, full))

    for step in recipe.get("step", []):
        output = step.get("output")
        if not output:
            continue
        if registry._is_generated(step) and (not top or blind):
            continue
        full = os.path.join(claim_dir, output)
        if os.path.isfile(full):
            entries.append((prefix + output, full))

    manifest_path = os.path.join(claim_dir, kernel.MANIFEST)
    if os.path.isfile(manifest_path):
        entries.append((prefix + kernel.MANIFEST, manifest_path))

    if top:
        attest_dir = os.path.join(claim_dir, ".reticuli", "attest")
        if os.path.isdir(attest_dir):
            for root_dir, _, files in os.walk(attest_dir):
                for fn in files:
                    full = os.path.join(root_dir, fn)
                    rel = os.path.relpath(full, claim_dir).replace(os.sep, "/")
                    entries.append((prefix + rel, full))

    try:
        manifest = kernel.read_manifest(claim_dir)
    except kernel.ClaimError:
        manifest = {}
    comp_names = sorted({l["component"] for l in (manifest.get("components") or [])})
    for name in comp_names:
        comp_dir = registry.find_component_dir(claim_dir, None, name)
        if comp_dir is None:
            continue
        sub_prefix = f"{prefix}.reticuli/deps/{name}/"
        entries.extend(_collect_export_entries(comp_dir, True, False, sub_prefix))

    return entries


def _add_deterministic(tar: tarfile.TarFile, abspath: str, arcname: str) -> None:
    info = tar.gettarinfo(abspath, arcname=arcname)
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mode = 0o644
    with open(abspath, "rb") as f:
        tar.addfile(info, f)


def export(claim_dir: str, tar_path: str, blind: bool = False) -> dict:
    """Write a deterministic tar of `claim_dir`'s declared content: the
    recipe, its pinned inputs, its step outputs (generated ones excluded
    when `blind`), its attestations, and every declared component's own
    claim (always blind)."""
    entries = _collect_export_entries(claim_dir, blind, True)
    seen = {}
    for arcname, abspath in entries:
        seen[arcname] = abspath
    with tarfile.open(tar_path, "w") as t:
        for arcname in sorted(seen):
            _add_deterministic(t, seen[arcname], arcname)
    return {"ok": True}


def import_(tar_path: str, target: str) -> dict:
    """Extract a transferred claim and reseal it: identity is recomputed
    from the bytes received, never trusted off the wire."""
    os.makedirs(target, exist_ok=True)
    with tarfile.open(tar_path) as t:
        t.extractall(target)
    registry.seal_with(target)
    verified = kernel.verify(target)
    return {"ok": verified["ok"], "root": verified["root"]}
