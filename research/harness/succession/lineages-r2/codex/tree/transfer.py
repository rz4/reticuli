"""Deterministic, criteria-scoped claim transfer."""
from __future__ import annotations

import io
import os
import tarfile

from . import kernel, registry
from ._util import declared_inputs, safe_path


def _files(directory, prefix="", blind=False, seen=None):
    seen = set() if seen is None else seen
    directory = os.path.realpath(directory)
    if directory in seen:
        raise kernel.ClaimError("component cycle")
    seen.add(directory)
    try:
        parsed = kernel.load_recipe(directory)
        recipe = "reticuli.toml" if os.path.isfile(os.path.join(directory, "reticuli.toml")) else "claim.toml"
        names = {recipe, *declared_inputs(directory, parsed)}
        for step in parsed.get("step", []):
            generated = step.get("kind") == "produce" and step.get("class", "generated") in ("generated", "free")
            if not (blind and generated):
                names.add(step["output"])
        names.add(registry.MANIFEST)
        for relative in sorted(names):
            path = safe_path(directory, relative)
            if os.path.isfile(path):
                kernel._hash_file(path)
                yield prefix + relative, path
        for group in ("attest", "mint"):
            store = os.path.join(directory, ".reticuli", group)
            if os.path.isdir(store):
                for root, _, files in os.walk(store):
                    for name in sorted(files):
                        path = os.path.join(root, name)
                        kernel._hash_file(path)
                        yield prefix + os.path.relpath(path, directory).replace(os.sep, "/"), path
        for link in kernel.read_manifest(directory).get("components", []):
            child = registry._component(directory, link)
            child_prefix = prefix + ".reticuli/deps/" + link["component"] + "/"
            yield from _files(child, child_prefix, True, seen)
    finally:
        seen.remove(directory)


def export(directory, path, *, blind=False):
    if not kernel.verify(directory)["ok"]:
        raise kernel.ClaimError("claim identity mismatch")
    files = dict(_files(directory, blind=blind))
    with tarfile.open(path, "w", format=tarfile.USTAR_FORMAT) as archive:
        for name, source in sorted(files.items()):
            with open(source, "rb") as stream:
                data = stream.read()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o644
            info.mtime = 0
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            archive.addfile(info, io.BytesIO(data))
    return {"path": path, "root": kernel.verify(directory)["root"]}


def import_(path, into):
    target = os.path.realpath(into)
    if os.path.exists(target) and os.listdir(target):
        raise kernel.ClaimError("import target holds bytes")
    os.makedirs(target, exist_ok=True)
    with tarfile.open(path, "r") as archive:
        for member in archive:
            if not member.isfile():
                raise kernel.ClaimError("archive contains non-file")
            name = member.name
            destination = safe_path(target, name)
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            stream = archive.extractfile(member)
            if stream is None:
                raise kernel.ClaimError("archive member unreadable")
            with open(destination, "wb") as output:
                output.write(stream.read())
    result = kernel.verify(target)
    if not result["ok"]:
        raise kernel.ClaimError("imported claim identity mismatch")
    return result
