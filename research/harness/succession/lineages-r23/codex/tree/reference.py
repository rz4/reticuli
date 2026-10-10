"""Independent, standard-library implementation of claim identity.

Run ``python -m reticuli.reference root DIRECTORY`` (or ``digest``) to
check an implementation against the published conformance vectors.
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
    """A recipe or declared file cannot be used to form an identity."""


def _json(value: object) -> str:
    try:
        return json.dumps(value, sort_keys=True)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ClaimError(f"recipe has no canonical JSON form: {exc}") from exc


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _path(directory: str | os.PathLike[str], name: object) -> Path:
    if not isinstance(name, str) or not name or os.path.isabs(name):
        raise ClaimError(f"invalid claim path: {name!r}")
    components = name.replace("\\", "/").split("/")
    if any(component in ("", ".", "..") for component in components):
        raise ClaimError(f"invalid claim path: {name!r}")
    base = Path(directory).resolve()
    result = base
    for component in components:
        result = result / component
        if result.is_symlink():
            raise ClaimError(f"symlink in claim path: {name!r}")
    if not result.resolve().is_relative_to(base):
        raise ClaimError(f"claim path escapes directory: {name!r}")
    return result


def _file_digest(path: Path) -> str:
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ClaimError(f"not a regular singly linked file: {path}")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
    except OSError as exc:
        raise ClaimError(f"cannot hash {path}: {exc}") from exc


def _recipe_file(directory: str | os.PathLike[str]) -> Path:
    for name in ("reticuli.toml", "claim.toml"):
        path = _path(directory, name)
        if path.exists() or path.is_symlink():
            _file_digest(path)
            return path
    raise ClaimError(f"no reticuli.toml or claim.toml in {directory}")


def _manifest_entries(directory: str | os.PathLike[str], name: str) -> list[str]:
    path = _path(directory, name)
    _file_digest(path)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise ClaimError(f"cannot read inputs manifest {name!r}: {exc}") from exc
    entries = []
    for number, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([0-9a-fA-F]{64})  (.+)", line)
        expected, entry = match.groups() if match else (None, line)
        path = _path(directory, entry)
        if expected is not None and _file_digest(path) != expected.lower():
            raise ClaimError(f"inputs manifest digest mismatch for {entry!r} at line {number}")
        entries.append(entry)
    return entries


def _load(directory: str | os.PathLike[str]) -> dict:
    path = _recipe_file(directory)
    try:
        with path.open("rb") as stream:
            recipe = tomllib.load(stream)
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ClaimError(f"invalid recipe {path}: {exc}") from exc
    claim = recipe.get("claim")
    if not isinstance(claim, dict):
        raise ClaimError("recipe needs a [claim] table")
    if not isinstance(claim.get("name"), str) or not claim["name"]:
        raise ClaimError("claim name must be a nonempty string")
    version = claim.get("format", 1)
    if type(version) is not int or version < 1 or version > 4:
        raise ClaimError(f"unsupported claim format: {version!r}")
    inputs = claim.get("inputs", [])
    if not isinstance(inputs, list) or any(not isinstance(item, str) for item in inputs):
        raise ClaimError("claim inputs must be a list of paths")
    for name in inputs:
        _path(directory, name)
    for key in ("inputs_manifest", "environment"):
        if key in claim:
            _path(directory, claim[key])
    if "inputs_manifest" in claim:
        if version < 2:
            raise ClaimError("inputs_manifest requires claim format 2")
        _manifest_entries(directory, claim["inputs_manifest"])
    steps = recipe.get("step", [])
    if not isinstance(steps, list):
        raise ClaimError("recipe steps must be an array")
    for number, step in enumerate(steps, 1):
        if not isinstance(step, dict) or step.get("kind") not in ("produce", "gate"):
            raise ClaimError(f"step {number} has invalid kind")
        _path(directory, step.get("output"))
        if step["kind"] == "gate" and (not isinstance(step.get("run"), str) or not step["run"]):
            raise ClaimError(f"gate step {number} needs a run command")
        klass = step.get("class", "generated" if step["kind"] == "produce" else "pinned")
        if klass not in ("generated", "pinned", "validated"):
            raise ClaimError(f"step {number} has invalid class")
        for key in ("guidance", "request"):
            if key in step and not isinstance(step[key], str):
                raise ClaimError(f"step {number} {key} must be a string")
        if "from" in step and (not isinstance(step["from"], str) or not step["from"]):
            raise ClaimError(f"step {number} from must be a name")
    return recipe


def _inputs(recipe: dict, directory: str | os.PathLike[str]) -> list[str]:
    claim = recipe["claim"]
    names = list(claim.get("inputs", []))
    if "inputs_manifest" in claim:
        name = claim["inputs_manifest"]
        names.append(name)
        names.extend(_manifest_entries(directory, name))
    if "environment" in claim:
        names.append(claim["environment"])
    return list(dict.fromkeys(names))


def _identity_recipe(recipe: dict) -> dict:
    value = copy.deepcopy(recipe)
    version = value["claim"].get("format", 1)
    if version >= 3:
        for step in value.get("step", []):
            step.pop("guidance", None)
            step.pop("request", None)
    if version >= 4 and "step" in value:
        value["step"].sort(key=_json)
    return value


def root(directory: str | os.PathLike[str]) -> str:
    """Return the root of a claim directory."""
    recipe = _load(directory)
    parts = {"digest": "sha256", "recipe": _json(_identity_recipe(recipe))}
    for name in _inputs(recipe, directory):
        parts["input:" + name] = _file_digest(_path(directory, name))
    for step in recipe.get("step", []):
        klass = step.get("class", "generated" if step["kind"] == "produce" else "pinned")
        if klass != "generated":
            name = step["output"]
            parts["pinned:" + name] = _file_digest(_path(directory, name))
    return _sha(_json(parts).encode("utf-8"))


def build_digest(directory: str | os.PathLike[str]) -> str:
    """Return the digest of present local generated outputs."""
    recipe = _load(directory)
    generated = []
    for step in recipe.get("step", []):
        klass = step.get("class", "generated" if step["kind"] == "produce" else "pinned")
        if klass != "generated" or "from" in step:
            continue
        name = step["output"]
        path = _path(directory, name)
        if path.exists():
            generated.append([name, _file_digest(path)])
    generated.sort(key=lambda item: item[0])
    return _sha(_json(generated).encode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="independent Reticuli identity implementation")
    parser.add_argument("action", choices=("root", "digest", "build-digest"))
    parser.add_argument("directory")
    args = parser.parse_args()
    print(root(args.directory) if args.action == "root" else build_digest(args.directory))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
