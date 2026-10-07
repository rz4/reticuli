"""Small, independent reference implementation of claim identity.

The preimage uses the parsed TOML recipe and the digests of declared pinned
files. Generated outputs contribute only to the separate build digest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import tomllib


class ReferenceError(ValueError):
    """A claim cannot be given an unambiguous content address."""


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, allow_nan=False).encode("utf-8")


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _path(directory: Path, name: str) -> Path:
    if not isinstance(name, str) or not name or os.path.isabs(name):
        raise ReferenceError(f"unsafe claim path: {name!r}")
    pieces = name.split("/")
    if any(piece in ("", ".", "..") for piece in pieces):
        raise ReferenceError(f"unsafe claim path: {name!r}")
    result = directory
    for piece in pieces:
        result /= piece
        if result.is_symlink():
            raise ReferenceError(f"symlink in claim path: {name!r}")
    return result


def _file_digest(path: Path) -> str:
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ReferenceError(f"not a regular single-link file: {path}")
        h = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError as exc:
        raise ReferenceError(f"cannot hash {path}: {exc}") from exc


def _recipe(directory: Path) -> dict:
    for name in ("reticuli.toml", "claim.toml"):
        path = _path(directory, name)
        if path.is_file():
            break
    else:
        raise ReferenceError(f"no recipe in {directory}")
    try:
        with path.open("rb") as source:
            recipe = tomllib.load(source)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ReferenceError(f"cannot read recipe {path}: {exc}") from exc
    claim = recipe.get("claim")
    if not isinstance(claim, dict) or not isinstance(claim.get("name"), str):
        raise ReferenceError("recipe needs [claim] with a string name")
    version = claim.get("format", 1)
    if type(version) is not int or not 1 <= version <= 4:
        raise ReferenceError(f"unsupported claim format: {version!r}")
    steps = recipe.get("step", [])
    if not isinstance(steps, list):
        raise ReferenceError("recipe steps must be an array")
    for step in steps:
        if not isinstance(step, dict) or step.get("kind") not in ("produce", "gate"):
            raise ReferenceError("invalid recipe step")
        _path(directory, step.get("output"))
    _json_bytes(recipe)
    return recipe


def _inputs(recipe: dict, directory: Path) -> list[str]:
    claim = recipe["claim"]
    names = list(claim.get("inputs", []))
    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        names.append(manifest)
        try:
            lines = _path(directory, manifest).read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise ReferenceError(f"cannot read inputs manifest: {exc}") from exc
        for line in lines:
            item = line.strip()
            if not item or item.startswith("#"):
                continue
            if len(item) > 66 and item[64:66] == "  " and all(c in "0123456789abcdef" for c in item[:64]):
                expected, item = item[:64], item[66:]
                if _file_digest(_path(directory, item)) != expected:
                    raise ReferenceError(f"inputs manifest digest mismatch: {item}")
            names.append(item)
    environment = claim.get("environment")
    if environment is not None and environment not in names:
        names.append(environment)
    return names


def _preimage_recipe(recipe: dict) -> dict:
    version = recipe["claim"].get("format", 1)
    if version < 3:
        return recipe
    result = dict(recipe)
    if "step" in recipe:
        steps = [{k: v for k, v in step.items() if k not in ("guidance", "request")}
                 for step in recipe["step"]]
        if version >= 4:
            steps.sort(key=_json_bytes)
        result["step"] = steps
    return result


def root(directory: str | os.PathLike[str]) -> str:
    """Compute the claim's SHA-256 root from its acceptance boundary."""
    directory = Path(directory)
    recipe = _recipe(directory)
    parts = {"digest": "sha256", "recipe": _json_bytes(_preimage_recipe(recipe)).decode("utf-8")}
    for name in _inputs(recipe, directory):
        parts["input:" + name] = _file_digest(_path(directory, name))
    for step in recipe.get("step", []):
        classification = step.get("class", "generated" if step["kind"] == "produce" else "pinned")
        if classification not in ("generated", "free"):
            name = step["output"]
            parts["pinned:" + name] = _file_digest(_path(directory, name))
    return _digest(_json_bytes(parts))


def build_digest(directory: str | os.PathLike[str]) -> str:
    """Compute the concrete digest of present, locally generated outputs."""
    directory = Path(directory)
    recipe = _recipe(directory)
    pairs = []
    for step in recipe.get("step", []):
        if step["kind"] != "produce" or "from" in step:
            continue
        if step.get("class", "generated") not in ("generated", "free"):
            continue
        name = step["output"]
        path = _path(directory, name)
        if path.exists():
            pairs.append((name, _file_digest(path)))
    pairs.sort()
    return _digest(_json_bytes(pairs))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reference claim identity calculator")
    parser.add_argument("operation", choices=("root", "digest", "build-digest"))
    parser.add_argument("directory")
    args = parser.parse_args(argv)
    try:
        print(root(args.directory) if args.operation == "root" else build_digest(args.directory))
    except (ReferenceError, TypeError, ValueError) as exc:
        parser.exit(1, f"reference: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
