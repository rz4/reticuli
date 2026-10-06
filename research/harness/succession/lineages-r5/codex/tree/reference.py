"""Small, independent reference for claim identity and build digests.

Both digests use Python's default, sorted JSON serialization.  The recipe is
serialized once as a string inside the root's parts map, then serialized a
second time with that map.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import tomllib


class ClaimError(Exception):
    """A claim cannot be represented or safely read."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ClaimError(f"cannot serialize claim as JSON: {exc}") from exc


def _path(directory: str, name: str) -> str:
    if not isinstance(name, str) or not name or os.path.isabs(name):
        raise ClaimError(f"unsafe claim path: {name!r}")
    components = name.replace("\\", "/").split("/")
    if any(component in ("", ".", "..") for component in components):
        raise ClaimError(f"unsafe claim path: {name!r}")
    base = os.path.realpath(directory)
    current = base
    for component in components:
        if os.path.isdir(current):
            entries = os.listdir(current)
            if component not in entries and any(
                entry.casefold() == component.casefold() for entry in entries
            ):
                raise ClaimError(f"claim path case does not match directory entry: {name!r}")
        current = os.path.join(current, component)
        if os.path.islink(current):
            raise ClaimError(f"symlink in claim path: {name!r}")
    if os.path.commonpath((base, os.path.realpath(current))) != base:
        raise ClaimError(f"claim path escapes directory: {name!r}")
    return current


def _file_hash(path: str) -> str:
    try:
        info = os.lstat(path)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ClaimError(f"not a regular single-link file: {path}")
        digest = hashlib.sha256()
        with open(path, "rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
    except OSError as exc:
        raise ClaimError(f"cannot hash {path}: {exc}") from exc


def _recipe_path(directory: str) -> str:
    for name in ("reticuli.toml", "claim.toml"):
        path = _path(directory, name)
        if os.path.lexists(path):
            return path
    raise ClaimError(f"no recipe in {directory}")


def _manifest_inputs(directory: str, name: str) -> list[str]:
    path = _path(directory, name)
    try:
        with open(path, encoding="utf-8") as stream:
            lines = stream.readlines()
    except (OSError, UnicodeError) as exc:
        raise ClaimError(f"cannot read inputs manifest {name!r}: {exc}") from exc
    result = []
    for number, line in enumerate(lines, 1):
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", entry)
        digest, item = match.groups() if match else (None, entry)
        path = _path(directory, item)
        if digest is not None and _file_hash(path) != digest:
            raise ClaimError(f"inputs manifest hash mismatch on line {number}: {item!r}")
        result.append(item)
    return result


def _inputs(recipe: dict, directory: str) -> list[str]:
    claim = recipe["claim"]
    names = list(claim.get("inputs", []))
    if "inputs_manifest" in claim:
        names.append(claim["inputs_manifest"])
        names.extend(_manifest_inputs(directory, claim["inputs_manifest"]))
    if "environment" in claim:
        names.append(claim["environment"])
    return list(dict.fromkeys(names))


def load_recipe(directory: str) -> dict:
    """Parse and validate the recipe, including both supported filenames."""
    source = _recipe_path(directory)
    try:
        with open(source, "rb") as stream:
            recipe = tomllib.load(stream)
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ClaimError(f"cannot read recipe {source}: {exc}") from exc
    if not isinstance(recipe.get("claim"), dict):
        raise ClaimError("recipe needs a [claim] table")
    claim = recipe["claim"]
    if not isinstance(claim.get("name"), str):
        raise ClaimError("[claim] name must be a string")
    version = claim.get("format", 1)
    if type(version) is not int or version < 1 or version > 3:
        raise ClaimError(f"unsupported claim format: {version!r}")
    if "inputs" in claim and (
        not isinstance(claim["inputs"], list)
        or any(not isinstance(item, str) for item in claim["inputs"])
    ):
        raise ClaimError("[claim] inputs must be an array of paths")
    for key in ("inputs_manifest", "environment"):
        if key in claim and not isinstance(claim[key], str):
            raise ClaimError(f"[claim] {key} must be a path string")
    for name in _inputs(recipe, directory):
        _path(directory, name)
    steps = recipe.get("step", [])
    if not isinstance(steps, list):
        raise ClaimError("[[step]] must be an array of tables")
    seen = set()
    for number, step in enumerate(steps, 1):
        if not isinstance(step, dict) or step.get("kind") not in ("produce", "gate"):
            raise ClaimError(f"step {number} has invalid kind")
        name = step.get("output")
        _path(directory, name)
        if name in seen:
            raise ClaimError(f"duplicate step output: {name!r}")
        seen.add(name)
        if step["kind"] == "gate" and not isinstance(step.get("run"), str):
            raise ClaimError(f"gate step {number} needs a run command")
        default = "generated" if step["kind"] == "produce" else "pinned"
        if step.get("class", default) not in ("generated", "pinned", "validated"):
            raise ClaimError(f"step {number} has invalid class")
        if "from" in step and (
            step["kind"] != "produce" or not isinstance(step["from"], str)
        ):
            raise ClaimError(f"step {number} has invalid from value")
        for key in ("guidance", "request"):
            if key in step and not isinstance(step[key], str):
                raise ClaimError(f"step {number} {key} must be a string")
    return recipe


def _identity_recipe(recipe: dict) -> dict:
    if recipe["claim"].get("format", 1) < 3:
        return recipe
    result = dict(recipe)
    if "step" in result:
        result["step"] = [
            {key: value for key, value in step.items()
             if step["kind"] != "produce" or key not in ("guidance", "request")}
            for step in result["step"]
        ]
    return result


def root(directory: str) -> str:
    """Return the SHA-256 identity of a claim's pinned criteria and verdicts."""
    recipe = load_recipe(directory)
    parts = {"digest": "sha256", "recipe": _canonical(_identity_recipe(recipe)).decode("utf-8")}
    for name in _inputs(recipe, directory):
        parts["input:" + name] = _file_hash(_path(directory, name))
    for step in recipe.get("step", []):
        default = "generated" if step["kind"] == "produce" else "pinned"
        if step.get("class", default) != "generated":
            name = step["output"]
            parts["pinned:" + name] = _file_hash(_path(directory, name))
    return hashlib.sha256(_canonical(parts)).hexdigest()


def build_digest(directory: str) -> str:
    """Hash present local generated outputs as sorted path/hash pairs."""
    recipe = load_recipe(directory)
    entries = []
    for step in recipe.get("step", []):
        if step["kind"] != "produce" or step.get("class", "generated") != "generated" or "from" in step:
            continue
        name = step["output"]
        path = _path(directory, name)
        if os.path.lexists(path):
            entries.append([name, _file_hash(path)])
    entries.sort(key=lambda entry: entry[0])
    return hashlib.sha256(_canonical(entries)).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reference claim identity computation")
    parser.add_argument("operation", choices=("root", "digest", "build-digest"))
    parser.add_argument("directory")
    args = parser.parse_args(argv)
    try:
        answer = root(args.directory) if args.operation == "root" else build_digest(args.directory)
    except ClaimError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(answer)
    return 0


if __name__ == "__main__":
    sys.exit(main())
