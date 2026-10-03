"""Small, independent implementation of claim identity for conformance vectors.

The preimage uses Python's default JSON separators and ASCII escaping.  In
particular, the canonical recipe is a *string* inside the outer parts map.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tomllib


def _json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True).encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _path(directory: Path, name: str) -> Path:
    if not isinstance(name, str) or not name or name.startswith("/"):
        raise ValueError(f"unsafe claim path: {name!r}")
    parts = name.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError(f"unsafe claim path: {name!r}")
    path = directory
    for part in parts:
        path = path / part
        if path.is_symlink():
            raise ValueError(f"symlink in claim path: {name!r}")
    return path


def _file_hash(path: Path) -> str:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError(f"not a regular singly linked file: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _recipe(directory: Path) -> dict:
    for name in ("reticuli.toml", "claim.toml"):
        path = _path(directory, name)
        if path.exists():
            _file_hash(path)
            with path.open("rb") as stream:
                return tomllib.load(stream)
    raise ValueError(f"no recipe in {directory}")


def _inputs(recipe: dict, directory: Path) -> list[str]:
    claim = recipe["claim"]
    names = list(claim.get("inputs", []))
    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        names.append(manifest)
        lines = _path(directory, manifest).read_text(encoding="utf-8").splitlines()
        for raw in lines:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            matched = re.fullmatch(r"[0-9a-f]{64}  (.+)", line)
            names.append(matched.group(1) if matched else line)
    if claim.get("environment") is not None:
        names.append(claim["environment"])
    return names


def root(directory: os.PathLike[str] | str) -> str:
    """Compute a claim's root from its recipe and pinned file bytes."""
    base = Path(directory)
    recipe = _recipe(base)
    preimage_recipe = recipe
    if recipe["claim"].get("format", 1) >= 3:
        preimage_recipe = dict(recipe)
        if "step" in recipe:
            preimage_recipe["step"] = [
                {key: value for key, value in step.items()
                 if key not in ("guidance", "request")}
                for step in recipe["step"]
            ]
    parts = {"digest": "sha256", "recipe": _json(preimage_recipe).decode("utf-8")}
    for name in _inputs(recipe, base):
        parts["input:" + name] = _file_hash(_path(base, name))
    for step in recipe.get("step", []):
        default_class = "generated" if step["kind"] == "produce" else "pinned"
        if step.get("class", default_class) not in ("generated", "free"):
            name = step["output"]
            parts["pinned:" + name] = _file_hash(_path(base, name))
    return _sha(_json(parts))


def build_digest(directory: os.PathLike[str] | str) -> str:
    """Hash present, local generated outputs as sorted path/hash pairs."""
    base = Path(directory)
    recipe = _recipe(base)
    names = sorted(step["output"] for step in recipe.get("step", [])
                   if step["kind"] == "produce"
                   and step.get("class", "generated") in ("generated", "free")
                   and "from" not in step)
    present = []
    for name in names:
        path = _path(base, name)
        if path.exists():
            present.append([name, _file_hash(path)])
    return _sha(_json(present))


def main() -> int:
    parser = argparse.ArgumentParser(description="Reference claim identity")
    parser.add_argument("operation", choices=("root", "digest", "build-digest"))
    parser.add_argument("directory")
    args = parser.parse_args()
    print(root(args.directory) if args.operation == "root" else build_digest(args.directory))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
