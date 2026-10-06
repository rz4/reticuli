"""Small, independent implementation of the claim identity serialization.

This module intentionally uses only the standard library.  It can also be
invoked by the language-neutral conformance vector runner.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import math
import os
import re
import stat
import tomllib
from pathlib import Path


class ClaimError(ValueError):
    """A recipe or a declared file cannot be used as a claim."""


def _declared_path(directory: os.PathLike[str] | str, name: str) -> Path:
    if not isinstance(name, str) or not name or os.path.isabs(name):
        raise ClaimError(f"unsafe claim path: {name!r}")
    pieces = name.split("/")
    if any(piece in ("", ".", "..") for piece in pieces):
        raise ClaimError(f"unsafe claim path: {name!r}")
    path = Path(directory).resolve()
    for piece in pieces:
        path /= piece
        if path.is_symlink():
            raise ClaimError(f"symlink in claim path: {name!r}")
    return path


def _hash_file(path: Path) -> str:
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ClaimError(f"not a regular single-link file: {path}")
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
    except OSError as error:
        raise ClaimError(f"cannot hash {path}: {error}") from error


def _json_value(value: object) -> None:
    if isinstance(value, (datetime.date, datetime.time)):
        raise ClaimError("TOML date and time values are not supported")
    if isinstance(value, float) and not math.isfinite(value):
        raise ClaimError("non-finite recipe number")
    if isinstance(value, dict):
        for item in value.values():
            _json_value(item)
    elif isinstance(value, list):
        for item in value:
            _json_value(item)


def load_recipe(directory: os.PathLike[str] | str) -> dict:
    """Read either recipe filename, preferring the canonical one."""
    for name in ("reticuli.toml", "claim.toml"):
        path = _declared_path(directory, name)
        if path.exists():
            break
    else:
        raise ClaimError(f"no recipe in {directory}")
    try:
        with path.open("rb") as source:
            recipe = tomllib.load(source)
    except (OSError, tomllib.TOMLDecodeError, UnicodeError) as error:
        raise ClaimError(f"cannot read recipe {path}: {error}") from error
    _json_value(recipe)
    claim = recipe.get("claim")
    if not isinstance(claim, dict) or not isinstance(claim.get("name"), str):
        raise ClaimError("recipe needs [claim] with a string name")
    version = claim.get("format", 1)
    if isinstance(version, bool) or not isinstance(version, int) or version < 1 or version > 3:
        raise ClaimError(f"unsupported claim format: {version!r}")
    if not isinstance(claim.get("inputs", []), list):
        raise ClaimError("claim inputs must be a list")
    for name in claim.get("inputs", []):
        _declared_path(directory, name)
    for key in ("inputs_manifest", "environment"):
        if key in claim:
            _declared_path(directory, claim[key])
    steps = recipe.get("step", [])
    if not isinstance(steps, list):
        raise ClaimError("recipe steps must be a list")
    for step in steps:
        if not isinstance(step, dict) or step.get("kind") not in ("produce", "gate"):
            raise ClaimError("invalid step kind")
        _declared_path(directory, step.get("output"))
        if step["kind"] == "gate" and not isinstance(step.get("run"), str):
            raise ClaimError("gate step needs a run command")
    return recipe


def _inputs(recipe: dict, directory: os.PathLike[str] | str) -> list[str]:
    claim = recipe["claim"]
    names = list(claim.get("inputs", []))
    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        path = _declared_path(directory, manifest)
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as error:
            raise ClaimError(f"cannot read inputs manifest {manifest!r}: {error}") from error
        for number, line in enumerate(lines, 1):
            item = line.strip()
            if not item or item.startswith("#"):
                continue
            match = re.fullmatch(r"([0-9a-f]{64})  (.+)", item)
            if match:
                item = match.group(2)
            elif re.match(r"[0-9a-f]{64}\s", item):
                raise ClaimError(f"malformed inputs manifest line {number}")
            _declared_path(directory, item)
            names.append(item)
        names.append(manifest)
    if claim.get("environment") is not None:
        names.append(claim["environment"])
    return list(dict.fromkeys(names))


def _preimage_recipe(recipe: dict) -> dict:
    if recipe["claim"].get("format", 1) < 3:
        return recipe
    result = dict(recipe)
    result["step"] = [
        {key: value for key, value in step.items()
         if step["kind"] != "produce" or key not in ("guidance", "request")}
        for step in recipe.get("step", [])
    ]
    return result


def root(directory: os.PathLike[str] | str) -> str:
    """Return SHA-256 of the double-serialized, sorted claim preimage."""
    recipe = load_recipe(directory)
    parts = {"digest": "sha256",
             "recipe": json.dumps(_preimage_recipe(recipe), sort_keys=True)}
    for name in _inputs(recipe, directory):
        parts["input:" + name] = _hash_file(_declared_path(directory, name))
    for step in recipe.get("step", []):
        default = "generated" if step["kind"] == "produce" else "pinned"
        if step.get("class", default) != "generated":
            name = step["output"]
            parts["pinned:" + name] = _hash_file(_declared_path(directory, name))
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode("utf-8")).hexdigest()


def build_digest(directory: os.PathLike[str] | str) -> str:
    """Digest present, locally generated outputs as sorted name/hash pairs."""
    recipe = load_recipe(directory)
    generated = []
    for step in recipe.get("step", []):
        if (step["kind"] != "produce" or step.get("class", "generated") != "generated"
                or "from" in step):
            continue
        name = step["output"]
        path = _declared_path(directory, name)
        if path.exists() or path.is_symlink():
            generated.append((name, _hash_file(path)))
    return hashlib.sha256(json.dumps(sorted(generated), sort_keys=True).encode("utf-8")).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="reference claim identity")
    parser.add_argument("operation", choices=("root", "digest", "build-digest"))
    parser.add_argument("directory")
    args = parser.parse_args(argv)
    try:
        print(root(args.directory) if args.operation == "root" else build_digest(args.directory))
    except ClaimError as error:
        parser.exit(1, f"reference: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
