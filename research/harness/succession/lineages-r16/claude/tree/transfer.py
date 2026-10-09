"""Transfer: deterministic tar, verify-on-import, volatile history stays home.

`export` walks a claim's RECIPE -- never its directory tree -- so an
undeclared file dropped beside a claim never rides along, and the result
is byte-identical across repeated calls on unchanged content (sorted
entries, normalized tar metadata). The event ledger never travels: it is
local history, not part of what a claim is. A declared component's own
claim (recipe, pinned inputs, manifest) travels nested under
`.reticuli/deps/<name>/` -- always blind, since a dependency's generated
bytes are exactly what an importer's own deep audit must re-earn, never
inherit. `blind=True` withholds the TOP claim's generated outputs too: the
rebuilder's room, identity whole, implementation withheld. Attestations
(`.reticuli/attest/`) are residue ABOUT the claim and travel regardless.

`import_` extracts into an empty directory, mirrors each `deps/<name>`
into the canonical `.reticuli/sealed/<name>` the registry expects, and
verifies identity on the received bytes alone.
"""
import os
import shutil
import tarfile

from reticuli import kernel


def _recipe_filename(d: str) -> str:
    for name in (kernel.RECIPE, kernel.LEGACY_RECIPE):
        if os.path.isfile(os.path.join(d, name)):
            return name
    raise kernel.ClaimError(f"no recipe found in {d!r}")


def _claim_entries(d: str, prefix: str, blind: bool) -> list:
    """(arcname, abspath) pairs for one claim layer; nested components are
    always blind regardless of `blind`, which applies only at `prefix=''`."""
    effective_blind = True if prefix else blind
    recipe = kernel.load_recipe(d)
    entries = []

    rp = _recipe_filename(d)
    entries.append((prefix + rp, os.path.join(d, rp)))

    manifest_path = os.path.join(d, kernel.MANIFEST)
    if os.path.isfile(manifest_path):
        entries.append((prefix + kernel.MANIFEST, manifest_path))

    claim = recipe.get("claim", {})
    for inp in claim.get("inputs", []):
        full = os.path.join(d, inp)
        if os.path.isfile(full):
            entries.append((prefix + inp, full))

    for step in recipe.get("step", []):
        output = step["output"]
        default = "generated" if step["kind"] == "produce" else "pinned"
        cls = step.get("class", default)
        if cls == "generated" and effective_blind:
            continue
        full = os.path.join(d, output)
        if os.path.isfile(full):
            entries.append((prefix + output, full))

    if os.path.isfile(manifest_path):
        try:
            manifest = kernel.read_manifest(d)
        except kernel.ClaimError:
            manifest = {}
        for link in manifest.get("components") or []:
            comp_name = link["component"]
            comp_dir = os.path.join(d, kernel.STORE, "sealed", comp_name)
            if os.path.isdir(comp_dir):
                entries.extend(_claim_entries(
                    comp_dir, f"{prefix}{kernel.STORE}/deps/{comp_name}/", True))

    return entries


def _attest_entries(d: str) -> list:
    attest_dir = os.path.join(d, kernel.STORE, "attest")
    entries = []
    if not os.path.isdir(attest_dir):
        return entries
    for root_dir, dirs, files in os.walk(attest_dir):
        dirs.sort()
        for fname in sorted(files):
            full = os.path.join(root_dir, fname)
            entries.append((os.path.relpath(full, d), full))
    return entries


def _normalize(tarinfo: tarfile.TarInfo) -> tarfile.TarInfo:
    tarinfo.mtime = 0
    tarinfo.uid = 0
    tarinfo.gid = 0
    tarinfo.uname = ""
    tarinfo.gname = ""
    if tarinfo.isfile():
        tarinfo.mode = 0o644
    return tarinfo


def export(d: str, tar_path: str, *, blind: bool = False) -> None:
    """Write a deterministic tar of `d`'s declared content at `tar_path`."""
    entries = _claim_entries(d, "", blind) + _attest_entries(d)

    seen, unique = set(), []
    for arc, full in entries:
        if arc in seen:
            continue
        seen.add(arc)
        unique.append((arc, full))
    unique.sort(key=lambda pair: pair[0])

    directory = os.path.dirname(tar_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with tarfile.open(tar_path, "w") as tar:
        for arc, full in unique:
            tar.add(full, arcname=arc, recursive=False, filter=_normalize)


def import_(tar_path: str, dest: str) -> dict:
    """Extract `tar_path` into the empty directory `dest`, mirror its
    declared components into the registry's canonical location, and
    verify identity on the received bytes alone."""
    if os.path.exists(dest) and os.listdir(dest):
        raise kernel.ClaimError(f"refused non-empty import target: {dest!r}")
    os.makedirs(dest, exist_ok=True)
    with tarfile.open(tar_path, "r") as tar:
        try:
            tar.extractall(dest, filter="data")
        except TypeError:
            tar.extractall(dest)

    deps_root = os.path.join(dest, kernel.STORE, "deps")
    if os.path.isdir(deps_root):
        for name in sorted(os.listdir(deps_root)):
            src = os.path.join(deps_root, name)
            dst = os.path.join(dest, kernel.STORE, "sealed", name)
            if os.path.isdir(src) and not os.path.exists(dst):
                shutil.copytree(src, dst)

    try:
        v = kernel.verify(dest)
        return {"ok": v["ok"], "root": v["root"], "recomputed": v["recomputed"]}
    except kernel.ClaimError as e:
        return {"ok": False, "root": None, "error": str(e)}
