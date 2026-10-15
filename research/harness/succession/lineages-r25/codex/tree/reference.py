"""Small, independent reference implementation of claim identity.

The recipe is hashed as parsed TOML.  File names and JSON spacing are part of
the identity format; generated output bytes are part of the build digest only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import tomllib
from pathlib import Path


class ClaimError(ValueError):
    """A claim cannot be read without ambiguity."""


def _json(value: object) -> str:
    try:
        return json.dumps(value, sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise ClaimError(f"recipe cannot be serialized as canonical JSON: {exc}") from exc


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _path(directory: os.PathLike[str] | str, name: str) -> Path:
    if not isinstance(name, str) or not name or os.path.isabs(name):
        raise ClaimError(f"unsafe claim path: {name!r}")
    if any(part in ("", ".", "..") for part in name.split("/")):
        raise ClaimError(f"unsafe claim path: {name!r}")
    base = Path(directory).resolve()
    current = base
    for part in name.split("/"):
        current = current / part
        if current.is_symlink():
            raise ClaimError(f"symlink in claim path: {name!r}")
    if not current.resolve().is_relative_to(base):
        raise ClaimError(f"path escapes claim: {name!r}")
    return current


def _file_hash(path: Path) -> str:
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


def _recipe(directory: os.PathLike[str] | str) -> dict:
    for name in ("reticuli.toml", "claim.toml"):
        path = _path(directory, name)
        if path.exists() or path.is_symlink():
            _file_hash(path)
            try:
                with path.open("rb") as stream:
                    recipe = tomllib.load(stream)
            except (OSError, ValueError) as exc:
                raise ClaimError(f"cannot parse recipe {path}: {exc}") from exc
            break
    else:
        raise ClaimError(f"no recipe in {directory}")
    claim = recipe.get("claim")
    if not isinstance(claim, dict) or not isinstance(claim.get("name"), str):
        raise ClaimError("recipe needs [claim] with a string name")
    version = claim.get("format", 1)
    if type(version) is not int or not 1 <= version <= 4:
        raise ClaimError(f"unsupported claim format: {version!r}")
    steps = recipe.get("step", [])
    if not isinstance(steps, list) or any(not isinstance(s, dict) for s in steps):
        raise ClaimError("recipe step must be an array of tables")
    for step in steps:
        if step.get("kind") not in ("produce", "gate"):
            raise ClaimError(f"invalid step kind: {step.get('kind')!r}")
        _path(directory, step.get("output"))
        if step.get("kind") == "gate" and not isinstance(step.get("run"), str):
            raise ClaimError("gate step needs a run command")
    return recipe


def _inputs(recipe: dict, directory: os.PathLike[str] | str) -> list[str]:
    claim = recipe["claim"]
    names = list(claim.get("inputs", []))
    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        manifest_path = _path(directory, manifest)
        _file_hash(manifest_path)
        names.append(manifest)
        for line in manifest_path.read_text(encoding="utf-8").splitlines():
            entry = line.strip()
            if not entry or entry.startswith("#"):
                continue
            match = re.fullmatch(r"([0-9a-f]{64})  (.+)", entry)
            digest, name = (match.group(1), match.group(2)) if match else (None, entry)
            if digest is not None and _file_hash(_path(directory, name)) != digest:
                raise ClaimError(f"inputs manifest digest mismatch for {name}")
            names.append(name)
    environment = claim.get("environment")
    if environment is not None and environment not in names:
        names.append(environment)
    return names


def root(directory: os.PathLike[str] | str) -> str:
    """Return the root of the parsed recipe and its declared pinned files."""
    recipe = _recipe(directory)
    preimage = dict(recipe)
    version = recipe["claim"].get("format", 1)
    if version >= 3 and "step" in preimage:
        steps = [dict(step) for step in preimage["step"]]
        for step in steps:
            step.pop("guidance", None)
            step.pop("request", None)
        if version >= 4:
            steps.sort(key=_json)
        preimage["step"] = steps
    parts = {"digest": "sha256", "recipe": _json(preimage)}
    for name in _inputs(recipe, directory):
        parts["input:" + name] = _file_hash(_path(directory, name))
    for step in recipe.get("step", []):
        default = "generated" if step["kind"] == "produce" else "pinned"
        if step.get("class", default) != "generated":
            name = step["output"]
            parts["pinned:" + name] = _file_hash(_path(directory, name))
    return _sha(_json(parts).encode("utf-8"))


def build_digest(directory: os.PathLike[str] | str) -> str:
    """Hash the sorted names and digests of present, local generated outputs."""
    recipe = _recipe(directory)
    entries = []
    for step in recipe.get("step", []):
        if (step["kind"] == "produce" and step.get("class", "generated") == "generated"
                and "from" not in step):
            name = step["output"]
            path = _path(directory, name)
            if path.exists() or path.is_symlink():
                entries.append((name, _file_hash(path)))
    entries.sort()
    return _sha(_json(entries).encode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Reference claim identity")
    parser.add_argument("operation", choices=("root", "digest", "build-digest"))
    parser.add_argument("directory")
    args = parser.parse_args()
    try:
        print(root(args.directory) if args.operation == "root" else build_digest(args.directory))
    except (ClaimError, UnicodeError) as exc:
        parser.exit(1, f"reference: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
