"""Small, independent implementation of claim content identities.

The recipe is parsed as TOML; its formatting and filename are outside the
identity.  File contents, including verdict files, are hashed byte for byte.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import stat
import tomllib


class ReferenceError(ValueError):
    """A claim cannot be identified from its declared files."""


def _file(directory: str | os.PathLike[str], name: str) -> Path:
    if not isinstance(name, str) or not name or os.path.isabs(name):
        raise ReferenceError(f"unsafe claim path: {name!r}")
    parts = Path(name).parts
    if ".." in parts:
        raise ReferenceError(f"unsafe claim path: {name!r}")
    base = Path(directory).resolve()
    path = base
    for part in parts:
        path = path / part
        if path.is_symlink():
            raise ReferenceError(f"symlink in claim path: {name!r}")
    if path == base or not path.is_relative_to(base):
        raise ReferenceError(f"unsafe claim path: {name!r}")
    return path


def _hash_file(path: Path) -> str:
    info = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ReferenceError(f"not an ordinary single-link file: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _recipe(directory: str | os.PathLike[str]) -> dict:
    for name in ("reticuli.toml", "claim.toml"):
        path = _file(directory, name)
        if path.is_file():
            with path.open("rb") as source:
                data = tomllib.load(source)
            break
    else:
        raise ReferenceError(f"recipe not found in {directory}")
    if not isinstance(data.get("claim"), dict) or not isinstance(data["claim"].get("name"), str):
        raise ReferenceError("claim requires a name")
    if not isinstance(data.get("step", []), list):
        raise ReferenceError("steps must be tables")
    return data


def _inputs(data: dict, directory: str | os.PathLike[str]) -> list[str]:
    claim = data["claim"]
    names = list(claim.get("inputs", []))
    for key in ("environment", "inputs_manifest"):
        if key in claim and claim[key] not in names:
            names.append(claim[key])
    if "inputs_manifest" in claim:
        with _file(directory, claim["inputs_manifest"]).open(encoding="utf-8") as source:
            for line in source:
                line = line.strip()
                if line and not line.startswith("#"):
                    digest, separator, path = line.partition("  ")
                    names.append(path if separator and len(digest) == 64 else line)
    return names


def root(directory: str | os.PathLike[str]) -> str:
    """Return the SHA-256 root of a claim directory."""
    data = _recipe(directory)
    preimage_recipe = copy.deepcopy(data)
    if data["claim"].get("format", 1) >= 3:
        for step in preimage_recipe.get("step", []):
            if step.get("kind") == "produce":
                step.pop("guidance", None)
                step.pop("request", None)
    parts = {"digest": "sha256", "recipe": json.dumps(preimage_recipe, sort_keys=True)}
    for name in _inputs(data, directory):
        parts["input:" + name] = _hash_file(_file(directory, name))
    for step in data.get("step", []):
        if step.get("class") not in ("generated", "free"):
            name = step["output"]
            parts["pinned:" + name] = _hash_file(_file(directory, name))
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode("utf-8")).hexdigest()


def build_digest(directory: str | os.PathLike[str]) -> str:
    """Return the digest of present, locally produced generated files."""
    data = _recipe(directory)
    outputs = []
    for step in data.get("step", []):
        if step.get("kind") == "produce" and step.get("class") == "generated" and "from" not in step:
            name = step["output"]
            path = _file(directory, name)
            if path.exists() or path.is_symlink():
                outputs.append([name, _hash_file(path)])
    return hashlib.sha256(json.dumps(sorted(outputs), sort_keys=True).encode("utf-8")).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute Reticuli claim identities")
    parser.add_argument("action", choices=("root", "digest", "build-digest"))
    parser.add_argument("directory")
    args = parser.parse_args()
    print(root(args.directory) if args.action == "root" else build_digest(args.directory))


if __name__ == "__main__":
    main()
