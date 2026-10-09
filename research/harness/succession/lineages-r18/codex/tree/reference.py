"""Small, independent implementation of the claim identity format.

Run ``python -m reticuli.reference root DIRECTORY`` to calculate a root, or
use ``digest`` to calculate the digest of present generated outputs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import tomllib


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _path(directory: Path, name: str) -> Path:
    if not isinstance(name, str) or not name or os.path.isabs(name):
        raise ValueError(f"invalid claim path: {name!r}")
    parts = name.split(os.sep)
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError(f"invalid claim path: {name!r}")
    path = directory
    for part in parts:
        path /= part
        if path.is_symlink():
            raise ValueError(f"symbolic link in claim path: {name!r}")
    return path


def _file_digest(path: Path) -> str:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError(f"not a singly linked regular file: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _recipe(directory: Path) -> dict:
    for name in ("reticuli.toml", "claim.toml"):
        path = directory / name
        if path.exists():
            _file_digest(path)
            with path.open("rb") as source:
                return tomllib.load(source)
    raise ValueError(f"no recipe in {directory}")


def _inputs(recipe: dict, directory: Path) -> list[str]:
    claim = recipe["claim"]
    names = list(claim.get("inputs", []))
    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        names.append(manifest)
        manifest_path = _path(directory, manifest)
        _file_digest(manifest_path)
        for raw in manifest_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if len(line) >= 67 and line[64:66] == "  " and all(c in "0123456789abcdef" for c in line[:64]):
                expected, name = line[:64], line[66:]
                if _file_digest(_path(directory, name)) != expected:
                    raise ValueError(f"manifest digest mismatch for {name}")
            else:
                name = line
            names.append(name)
    environment = claim.get("environment")
    if environment is not None:
        names.append(environment)
    if len(names) != len(set(names)):
        raise ValueError("duplicate input path")
    return names


def _preimage_recipe(recipe: dict) -> dict:
    version = recipe["claim"].get("format", 1)
    if version < 3 or "step" not in recipe:
        return recipe
    transformed = dict(recipe)
    steps = []
    for step in recipe["step"]:
        item = {key: value for key, value in step.items()
                if key not in ("guidance", "request")}
        steps.append(item)
    if version >= 4:
        steps.sort(key=_json)
    transformed["step"] = steps
    return transformed


def root(directory: os.PathLike[str] | str) -> str:
    """Return the content address of a claim directory."""
    directory = Path(directory)
    recipe = _recipe(directory)
    parts = {"digest": "sha256", "recipe": _json(_preimage_recipe(recipe))}
    for name in _inputs(recipe, directory):
        parts["input:" + name] = _file_digest(_path(directory, name))
    for step in recipe.get("step", []):
        kind = step["kind"]
        step_class = step.get("class", "generated" if kind == "produce" else "pinned")
        if step_class != "generated":
            name = step["output"]
            parts["pinned:" + name] = _file_digest(_path(directory, name))
    return _sha256(_json(parts).encode("utf-8"))


def build_digest(directory: os.PathLike[str] | str) -> str:
    """Digest the present, locally generated outputs of a claim."""
    directory = Path(directory)
    recipe = _recipe(directory)
    generated = []
    for step in recipe.get("step", []):
        kind = step["kind"]
        step_class = step.get("class", "generated" if kind == "produce" else "pinned")
        if step_class == "generated" and "from" not in step:
            name = step["output"]
            path = _path(directory, name)
            if path.exists():
                generated.append([name, _file_digest(path)])
    generated.sort(key=lambda item: item[0])
    return _sha256(_json(generated).encode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("root", "digest"))
    parser.add_argument("directory")
    args = parser.parse_args(argv)
    print(root(args.directory) if args.operation == "root" else build_digest(args.directory))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
