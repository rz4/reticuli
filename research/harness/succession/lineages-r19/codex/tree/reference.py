"""Small, independent implementation of claim identity and build digests.

The preimage uses Python's default JSON separators and ASCII escaping.  In
particular, the recipe is a JSON *string* inside the outer parts object.
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


class ReferenceError(ValueError):
    """The claim cannot be represented as a content address."""


def _json(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ReferenceError(f"no canonical JSON form: {exc}") from exc


def _declared_path(directory: Path, name: str) -> Path:
    if (not isinstance(name, str) or not name or os.path.isabs(name)
            or any(part in ("", ".", "..") for part in name.split("/"))):
        raise ReferenceError(f"unsafe claim path: {name!r}")
    path = directory
    for part in name.split("/"):
        path = path / part
        if path.is_symlink():
            raise ReferenceError(f"symlink in claim path: {name!r}")
    return path


def _file_hash(path: Path) -> str:
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ReferenceError(f"not a regular singly linked file: {path}")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
    except OSError as exc:
        raise ReferenceError(f"cannot hash {path}: {exc}") from exc


def _recipe(directory: Path) -> dict:
    canonical = _declared_path(directory, "reticuli.toml")
    legacy = _declared_path(directory, "claim.toml")
    path = canonical if canonical.exists() else legacy
    try:
        with path.open("rb") as stream:
            recipe = tomllib.load(stream)
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ReferenceError(f"cannot read recipe {path}: {exc}") from exc
    claim = recipe.get("claim")
    if not isinstance(claim, dict) or not isinstance(claim.get("name"), str):
        raise ReferenceError("recipe needs [claim] with a string name")
    version = claim.get("format", 1)
    if type(version) is not int or not 1 <= version <= 4:
        raise ReferenceError(f"unsupported claim format: {version!r}")
    if not isinstance(claim.get("inputs", []), list):
        raise ReferenceError("claim inputs must be a list")
    steps = recipe.get("step", [])
    if not isinstance(steps, list):
        raise ReferenceError("recipe step must be an array")
    for step in steps:
        if not isinstance(step, dict) or step.get("kind") not in ("produce", "gate"):
            raise ReferenceError("invalid step kind")
        _declared_path(directory, step.get("output"))
        if step.get("class", "generated" if step["kind"] == "produce" else "pinned") not in (
                "generated", "pinned", "validated"):
            raise ReferenceError("invalid step class")
        if step["kind"] == "gate" and not isinstance(step.get("run"), str):
            raise ReferenceError("gate needs a run command")
    return recipe


def _inputs(directory: Path, claim: dict) -> list[str]:
    names = list(claim.get("inputs", []))
    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        path = _declared_path(directory, manifest)
        names.append(manifest)
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            raise ReferenceError(f"cannot read inputs manifest {path}: {exc}") from exc
        for raw in lines:
            line = raw.strip()
            if line and not line.startswith("#"):
                match = re.fullmatch(r"[0-9a-f]{64}  (.+)", line)
                names.append(match.group(1) if match else line)
    environment = claim.get("environment")
    if environment is not None:
        names.append(environment)
    return names


def _preimage_recipe(recipe: dict) -> dict:
    version = recipe["claim"].get("format", 1)
    if version < 3:
        return recipe
    result = dict(recipe)
    if "step" in recipe:
        steps = []
        for source in recipe["step"]:
            step = dict(source)
            if step["kind"] == "produce":
                step.pop("guidance", None)
                step.pop("request", None)
            steps.append(step)
        if version >= 4:
            steps.sort(key=_json)
        result["step"] = steps
    return result


def root(directory: os.PathLike[str] | str) -> str:
    """Return the SHA-256 identity of a claim directory."""
    base = Path(directory).resolve()
    recipe = _recipe(base)
    parts = {"digest": "sha256", "recipe": _json(_preimage_recipe(recipe)).decode("utf-8")}
    for name in _inputs(base, recipe["claim"]):
        parts["input:" + name] = _file_hash(_declared_path(base, name))
    for step in recipe.get("step", []):
        category = step.get("class", "generated" if step["kind"] == "produce" else "pinned")
        if category != "generated":
            name = step["output"]
            parts["pinned:" + name] = _file_hash(_declared_path(base, name))
    return hashlib.sha256(_json(parts)).hexdigest()


def build_digest(directory: os.PathLike[str] | str) -> str:
    """Digest present generated outputs owned by this claim."""
    base = Path(directory).resolve()
    recipe = _recipe(base)
    files = []
    for step in recipe.get("step", []):
        if (step["kind"] == "produce" and step.get("class", "generated") == "generated"
                and "from" not in step):
            name = step["output"]
            path = _declared_path(base, name)
            if path.exists():
                files.append((name, _file_hash(path)))
    files.sort()
    return hashlib.sha256(_json(files)).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("root", "digest", "build-digest"))
    parser.add_argument("directory")
    arguments = parser.parse_args(argv)
    try:
        result = root(arguments.directory) if arguments.operation == "root" else build_digest(arguments.directory)
    except ReferenceError as exc:
        parser.exit(1, f"reference: {exc}\n")
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
