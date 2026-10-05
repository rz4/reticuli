"""Small, standalone reference implementation of claim identity.

The recipe is parsed as TOML, but its canonical JSON representation (rather
than the TOML bytes) participates in the root.  This module deliberately
does not call the kernel's identity implementation.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tomllib


class ClaimError(ValueError):
    """The supplied claim cannot be given a well-defined identity."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ClaimError(f"cannot serialize recipe: {exc}") from exc


def _file(directory: Path, name: str) -> Path:
    if not isinstance(name, str) or not name or os.path.isabs(name):
        raise ClaimError(f"invalid claim path: {name!r}")
    components = name.replace("\\", "/").split("/")
    if any(part in ("", ".", "..") for part in components):
        raise ClaimError(f"invalid claim path: {name!r}")
    base = directory.resolve()
    path = base
    for part in components:
        path = path / part
        if path.is_symlink():
            raise ClaimError(f"symlink in claim path: {name!r}")
    if os.path.commonpath((str(base), str(path.resolve()))) != str(base):
        raise ClaimError(f"claim path escapes directory: {name!r}")
    return path


def _hash_file(path: Path) -> str:
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ClaimError(f"not an unaliased regular file: {path}")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
    except OSError as exc:
        raise ClaimError(f"cannot hash {path}: {exc}") from exc


def _recipe(directory: Path) -> dict:
    for filename in ("reticuli.toml", "claim.toml"):
        path = _file(directory, filename)
        if path.is_file():
            break
    else:
        raise ClaimError(f"no recipe in {directory}")
    try:
        with path.open("rb") as stream:
            recipe = tomllib.load(stream)
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ClaimError(f"cannot read recipe {path}: {exc}") from exc
    claim = recipe.get("claim")
    if not isinstance(claim, dict) or not isinstance(claim.get("name"), str):
        raise ClaimError("recipe requires a string [claim] name")
    version = claim.get("format", 1)
    if type(version) is not int or version < 1 or version > 3:
        raise ClaimError(f"unsupported claim format: {version!r}")
    steps = recipe.get("step", [])
    if not isinstance(steps, list):
        raise ClaimError("recipe steps must be an array")
    for step in steps:
        if not isinstance(step, dict) or step.get("kind") not in ("produce", "gate"):
            raise ClaimError("step kind must be produce or gate")
        _file(directory, step.get("output"))
        if step["kind"] == "gate" and not isinstance(step.get("run"), str):
            raise ClaimError("gate step requires a run command")
    return recipe


def _inputs(recipe: dict, directory: Path) -> list[str]:
    claim = recipe["claim"]
    names = list(claim.get("inputs", []))
    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        names.append(manifest)
        try:
            lines = _file(directory, manifest).read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            raise ClaimError(f"cannot read inputs manifest: {exc}") from exc
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            match = re.fullmatch(r"[0-9a-f]{64}  (.+)", line)
            if match:
                line = match.group(1)
            elif re.match(r"[0-9a-f]{64}\s", line):
                raise ClaimError("malformed inputs manifest line")
            names.append(line)
    environment = claim.get("environment")
    if environment is not None and environment not in names:
        names.append(environment)
    return names


def root(directory: os.PathLike[str] | str) -> str:
    """Compute the content address of a claim directory."""
    directory = Path(directory)
    recipe = _recipe(directory)
    preimage_recipe = recipe
    if recipe["claim"].get("format", 1) >= 3:
        preimage_recipe = copy.deepcopy(recipe)
        for step in preimage_recipe.get("step", []):
            step.pop("guidance", None)
            step.pop("request", None)
    parts = {"digest": "sha256", "recipe": _canonical(preimage_recipe).decode("ascii")}
    for name in _inputs(recipe, directory):
        parts["input:" + name] = _hash_file(_file(directory, name))
    for step in recipe.get("step", []):
        default = "generated" if step["kind"] == "produce" else "pinned"
        if step.get("class", default) != "generated":
            name = step["output"]
            parts["pinned:" + name] = _hash_file(_file(directory, name))
    return hashlib.sha256(_canonical(parts)).hexdigest()


def build_digest(directory: os.PathLike[str] | str) -> str:
    """Digest the present outputs produced locally by this realization."""
    directory = Path(directory)
    recipe = _recipe(directory)
    files = []
    for step in recipe.get("step", []):
        if (step["kind"] != "produce" or
                step.get("class", "generated") != "generated" or
                "from" in step):
            continue
        name = step["output"]
        path = _file(directory, name)
        if path.exists():
            files.append([name, _hash_file(path)])
    return hashlib.sha256(_canonical(sorted(files))).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Reference claim identity")
    parser.add_argument("action", choices=("root", "build-digest"))
    parser.add_argument("directory")
    args = parser.parse_args()
    print(root(args.directory) if args.action == "root" else build_digest(args.directory))


if __name__ == "__main__":
    main()
