"""transfer.py: deterministic tar export/import, verify-on-import.

A claim's declared bytes -- its recipe, pinned inputs, and pinned or
validated step outputs, plus (unless `blind`) its generated outputs --
travel; its ledger and any undeclared residue in its directory never
do (export walks the recipe, never the filesystem). A declared
component always travels blind, under `.reticuli/deps/<name>/`, so
`import_` can re-earn every layer from the bytes it received rather
than carrying a verdict.
"""
import os
import shutil
import tarfile

from . import kernel

DEPS_DIR = kernel.STORE + "/deps"
SEALED_DIR = kernel.STORE + "/sealed"
ATTEST_DIR = kernel.STORE + "/attest"


def _recipe_name(d: str) -> str:
    if os.path.isfile(os.path.join(d, kernel.RECIPE)):
        return kernel.RECIPE
    if os.path.isfile(os.path.join(d, kernel.LEGACY_RECIPE)):
        return kernel.LEGACY_RECIPE
    raise kernel.ClaimError(f"no recipe found in {d!r}")


def _declared_names(d: str, parsed: dict, blind: bool) -> list:
    names = [_recipe_name(d)]
    claim = parsed.get("claim") or {}
    manifest_file = claim.get("inputs_manifest")
    if manifest_file:
        names.append(manifest_file)
    inputs = claim.get("inputs", [])
    if isinstance(inputs, list):
        names.extend(p for p in inputs if isinstance(p, str))

    for step in parsed.get("step", []):
        output = step.get("output")
        if not output:
            continue
        default_class = "generated" if step.get("kind") == "produce" else "pinned"
        cls = step.get("class", default_class)
        if cls == "generated" and blind:
            continue
        if os.path.isfile(os.path.join(d, output)):
            names.append(output)
    return sorted(set(names))


def _add(tar: tarfile.TarFile, src: str, arcname: str) -> None:
    info = tar.gettarinfo(src, arcname=arcname)
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    if info.isfile():
        with open(src, "rb") as f:
            tar.addfile(info, f)
    else:
        tar.addfile(info)


def export(d: str, tar_path: str, *, blind: bool = False) -> None:
    """A deterministic tar of claim `d`'s declared bytes: two exports of
    an unchanged claim are byte-identical. `blind=True` withholds every
    generated output -- the room a rebuilder regrows into."""
    parsed = kernel.load_recipe(d)
    manifest = kernel.read_manifest(d)
    names = _declared_names(d, parsed, blind)

    with tarfile.open(tar_path, "w", format=tarfile.USTAR_FORMAT) as tar:
        for rel in names:
            _add(tar, os.path.join(d, rel), rel)
        _add(tar, os.path.join(d, kernel.MANIFEST), kernel.MANIFEST)

        attest_dir = os.path.join(d, ATTEST_DIR)
        if os.path.isdir(attest_dir):
            for fname in sorted(os.listdir(attest_dir)):
                _add(tar, os.path.join(attest_dir, fname), f"{ATTEST_DIR}/{fname}")

        seen = set()
        for link in manifest.get("components") or []:
            name = link["component"]
            if name in seen:
                continue
            seen.add(name)
            comp_dir = os.path.join(d, SEALED_DIR, name)
            if not os.path.isdir(comp_dir):
                continue
            comp_parsed = kernel.load_recipe(comp_dir)
            comp_names = _declared_names(comp_dir, comp_parsed, blind=True)
            comp_names.append(kernel.MANIFEST)
            for rel in sorted(set(comp_names)):
                _add(tar, os.path.join(comp_dir, rel), f"{DEPS_DIR}/{name}/{rel}")


def import_(tar_path: str, dest: str) -> dict:
    """Extract a tar into a fresh `dest` and verify on import: identity
    and verdicts re-verify from the received bytes alone. A bundled
    dependency's blind claim is promoted into the local registry so a
    deep audit can re-earn it too."""
    if os.path.isdir(dest) and os.listdir(dest):
        raise kernel.ClaimError(f"import target must start empty: {dest!r}")
    os.makedirs(dest, exist_ok=True)
    with tarfile.open(tar_path, "r") as tar:
        try:
            tar.extractall(dest, filter="data")
        except TypeError:
            tar.extractall(dest)

    deps_dir = os.path.join(dest, DEPS_DIR)
    if os.path.isdir(deps_dir):
        for name in sorted(os.listdir(deps_dir)):
            src = os.path.join(deps_dir, name)
            if not os.path.isdir(src):
                continue
            dst = os.path.join(dest, SEALED_DIR, name)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copytree(src, dst, dirs_exist_ok=True)

    vr = kernel.verify(dest)
    return {"ok": vr["ok"], "root": vr["root"]}
