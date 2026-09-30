"""Independent, standard-library reference for claim identity.

The root covers the parsed recipe and declared pinned bytes.  The build
digest covers only present, locally generated outputs.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import tomllib


class ClaimError(ValueError):
    """A claim cannot be assigned an identity."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True).encode("utf-8")


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _path(directory: os.PathLike[str] | str, name: str) -> str:
    if not isinstance(name, str) or not name or os.path.isabs(name):
        raise ClaimError(f"invalid claim path: {name!r}")
    parts = Path(name).parts
    if not parts or ".." in parts:
        raise ClaimError(f"claim path escapes directory: {name!r}")
    base = os.path.realpath(directory)
    current = base
    for part in parts:
        current = os.path.join(current, part)
        if os.path.islink(current):
            raise ClaimError(f"symlink in claim path: {name!r}")
    resolved = os.path.realpath(current)
    if os.path.commonpath((base, resolved)) != base or resolved == base:
        raise ClaimError(f"claim path escapes directory: {name!r}")
    return resolved


def _hash_file(path: str) -> str:
    try:
        info = os.lstat(path)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ClaimError(f"not a regular singly linked file: {path}")
        with open(path, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
                raise ClaimError(f"not a regular singly linked file: {path}")
            digest = hashlib.sha256()
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError as exc:
        raise ClaimError(f"cannot hash file {path}: {exc}") from exc


def _json_values(value: object) -> None:
    if isinstance(value, (datetime.date, datetime.time)):
        raise ClaimError("TOML date and time values are not supported")
    if isinstance(value, float) and not math.isfinite(value):
        raise ClaimError("non-finite recipe number")
    if isinstance(value, dict):
        for member in value.values():
            _json_values(member)
    elif isinstance(value, list):
        for member in value:
            _json_values(member)


def _read_recipe(directory: os.PathLike[str] | str) -> dict:
    for name in ("reticuli.toml", "claim.toml"):
        path = _path(directory, name)
        if os.path.exists(path):
            _hash_file(path)
            break
    else:
        raise ClaimError(f"no recipe in {directory}")
    try:
        with open(path, "rb") as stream:
            recipe = tomllib.load(stream)
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ClaimError(f"cannot parse recipe {path}: {exc}") from exc
    claim = recipe.get("claim")
    if not isinstance(claim, dict) or not isinstance(claim.get("name"), str):
        raise ClaimError("recipe requires a string [claim] name")
    version = claim.get("format", 1)
    if type(version) is not int or version < 1 or version > 3:
        raise ClaimError(f"unsupported claim format: {version!r}")
    _json_values(recipe)
    steps = recipe.get("step", [])
    if not isinstance(steps, list) or any(not isinstance(step, dict) for step in steps):
        raise ClaimError("recipe steps must be an array of tables")
    for number, step in enumerate(steps, 1):
        kind = step.get("kind")
        if kind not in ("produce", "gate"):
            raise ClaimError(f"step {number} has invalid kind: {kind!r}")
        _path(directory, step.get("output"))
        if kind == "gate" and not isinstance(step.get("run"), str):
            raise ClaimError(f"gate step {number} requires a run command")
        step_class = step.get("class", "generated" if kind == "produce" else "pinned")
        if step_class not in ("generated", "free", "pinned", "exact", "validated"):
            raise ClaimError(f"step {number} has invalid class: {step_class!r}")
    return recipe


def _inputs(directory: os.PathLike[str] | str, claim: dict) -> list[str]:
    names = claim.get("inputs", [])
    if not isinstance(names, list) or any(not isinstance(name, str) for name in names):
        raise ClaimError("claim inputs must be an array of paths")
    result = list(names)
    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        path = _path(directory, manifest)
        _hash_file(path)
        result.append(manifest)
        try:
            with open(path, encoding="utf-8") as stream:
                lines = stream.readlines()
        except (OSError, UnicodeError) as exc:
            raise ClaimError(f"cannot read inputs manifest {manifest}: {exc}") from exc
        for number, raw in enumerate(lines, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            match = re.fullmatch(r"[0-9a-f]{64}  (.+)", line)
            entry = match.group(1) if match else line
            if not entry or entry != entry.strip():
                raise ClaimError(f"bad inputs manifest entry on line {number}")
            result.append(entry)
    environment = claim.get("environment")
    if environment is not None:
        result.append(environment)
    for name in result:
        _path(directory, name)
    return result


def _preimage_recipe(recipe: dict) -> dict:
    if recipe["claim"].get("format", 1) < 3:
        return recipe
    result = dict(recipe)
    if "step" in recipe:
        result["step"] = [
            {key: value for key, value in step.items()
             if step.get("kind") != "produce" or key not in ("guidance", "request")}
            for step in recipe["step"]
        ]
    return result


def root(directory: os.PathLike[str] | str) -> str:
    """Compute the claim root from the recipe and every pinned file."""
    recipe = _read_recipe(directory)
    parts = {"digest": "sha256", "recipe": _canonical(_preimage_recipe(recipe)).decode("ascii")}
    for name in _inputs(directory, recipe["claim"]):
        parts["input:" + name] = _hash_file(_path(directory, name))
    for step in recipe.get("step", []):
        step_class = step.get("class", "generated" if step["kind"] == "produce" else "pinned")
        if step_class not in ("generated", "free"):
            name = step["output"]
            parts["pinned:" + name] = _hash_file(_path(directory, name))
    return _digest(_canonical(parts))


def build_digest(directory: os.PathLike[str] | str) -> str:
    """Digest present generated output names and byte digests, sorted by name."""
    recipe = _read_recipe(directory)
    files = []
    for step in recipe.get("step", []):
        if step["kind"] != "produce" or step.get("class", "generated") not in ("generated", "free") or "from" in step:
            continue
        name = step["output"]
        path = _path(directory, name)
        if os.path.exists(path):
            files.append([name, _hash_file(path)])
    files.sort(key=lambda item: item[0])
    return _digest(_canonical(files))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reference claim identity calculator")
    parser.add_argument("operation", choices=("root", "digest", "build-digest"))
    parser.add_argument("directory")
    args = parser.parse_args(argv)
    try:
        answer = root(args.directory) if args.operation == "root" else build_digest(args.directory)
    except ClaimError as exc:
        parser.exit(1, f"{exc}\n")
    print(answer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
