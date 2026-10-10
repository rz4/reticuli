"""Small, independent reference for the claim identity serialization.

Only declared files enter a root.  Generated output bytes enter the separate
build digest, so rebuilding them cannot rename a claim.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import tomllib


class ClaimError(ValueError):
    """The claim cannot be represented by the identity format."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ClaimError(f"no canonical JSON form: {exc}") from exc


def _file(directory: str | os.PathLike[str], name: str) -> str:
    if (not isinstance(name, str) or not name or os.path.isabs(name)
            or any(part in ("", ".", "..") for part in name.split("/"))):
        raise ClaimError(f"invalid claim path: {name!r}")
    base = os.path.realpath(directory)
    path = base
    for part in name.split("/"):
        path = os.path.join(path, part)
        if os.path.islink(path):
            raise ClaimError(f"symlink in claim path: {name!r}")
    if os.path.commonpath((base, os.path.realpath(path))) != base:
        raise ClaimError(f"claim path escapes directory: {name!r}")
    return path


def _hash_file(path: str) -> str:
    try:
        info = os.lstat(path)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ClaimError(f"not a singly linked regular file: {path}")
        digest = hashlib.sha256()
        with open(path, "rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
    except OSError as exc:
        raise ClaimError(f"cannot hash {path}: {exc}") from exc


def load_recipe(directory: str | os.PathLike[str]) -> dict:
    """Read either recipe name, preferring the canonical name."""
    for name in ("reticuli.toml", "claim.toml"):
        path = _file(directory, name)
        if os.path.lexists(path):
            break
    else:
        raise ClaimError(f"no recipe in {directory}")
    try:
        with open(path, "rb") as stream:
            parsed = tomllib.load(stream)
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ClaimError(f"cannot parse recipe {path}: {exc}") from exc
    claim = parsed.get("claim")
    if not isinstance(claim, dict) or not isinstance(claim.get("name"), str):
        raise ClaimError("recipe needs [claim] name as a string")
    version = claim.get("format", 1)
    if isinstance(version, bool) or not isinstance(version, int) or not 1 <= version <= 4:
        raise ClaimError(f"unsupported claim format: {version!r}")
    steps = parsed.get("step", [])
    if not isinstance(steps, list) or any(not isinstance(step, dict) for step in steps):
        raise ClaimError("step must be an array of tables")
    for step in steps:
        kind = step.get("kind")
        if kind not in ("produce", "gate"):
            raise ClaimError(f"invalid step kind: {kind!r}")
        _file(directory, step.get("output"))
        if kind == "gate" and not isinstance(step.get("run"), str):
            raise ClaimError("gate step needs a run command")
    return parsed


def _inputs(recipe: dict, directory: str | os.PathLike[str]) -> list[str]:
    claim = recipe["claim"]
    listed = claim.get("inputs", [])
    if not isinstance(listed, list) or any(not isinstance(name, str) for name in listed):
        raise ClaimError("claim inputs must be an array of paths")
    names = list(listed)
    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        path = _file(directory, manifest)
        names.append(manifest)
        with open(path, encoding="utf-8") as stream:
            for raw in stream:
                line = raw.strip()
                if line and not line.startswith("#"):
                    prefix, separator, rest = line.partition("  ")
                    names.append(rest if separator and len(prefix) == 64 and
                                 all(char in "0123456789abcdef" for char in prefix) else line)
    if claim.get("environment") is not None:
        names.append(claim["environment"])
    for name in names:
        _file(directory, name)
    return list(dict.fromkeys(names))


def _preimage_recipe(recipe: dict) -> dict:
    version = recipe["claim"].get("format", 1)
    if version < 3 or "step" not in recipe:
        return recipe
    clean = dict(recipe)
    clean["step"] = [
        {key: value for key, value in step.items() if key not in ("guidance", "request")}
        for step in recipe["step"]
    ]
    if version >= 4:
        clean["step"].sort(key=_canonical)
    return clean


def root(directory: str | os.PathLike[str]) -> str:
    """Return the SHA-256 identity of a claim's criteria and pinned bytes."""
    recipe = load_recipe(directory)
    parts = {"digest": "sha256", "recipe": _canonical(_preimage_recipe(recipe)).decode("utf-8")}
    for name in _inputs(recipe, directory):
        parts["input:" + name] = _hash_file(_file(directory, name))
    for step in recipe.get("step", []):
        kind = step["kind"]
        klass = step.get("class", "generated" if kind == "produce" else "pinned")
        if klass not in ("generated", "free"):
            name = step["output"]
            parts["pinned:" + name] = _hash_file(_file(directory, name))
    return hashlib.sha256(_canonical(parts)).hexdigest()


def build_digest(directory: str | os.PathLike[str]) -> str:
    """Hash the names and digests of present, locally generated outputs."""
    recipe = load_recipe(directory)
    generated = []
    for step in recipe.get("step", []):
        if (step["kind"] == "produce" and "from" not in step
                and step.get("class", "generated") in ("generated", "free")):
            name = step["output"]
            path = _file(directory, name)
            if os.path.lexists(path):
                generated.append([name, _hash_file(path)])
    generated.sort()
    return hashlib.sha256(_canonical(generated)).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Reference claim identity calculator")
    parser.add_argument("operation", choices=("root", "digest", "build-digest"))
    parser.add_argument("directory")
    args = parser.parse_args()
    print(root(args.directory) if args.operation == "root" else build_digest(args.directory))


if __name__ == "__main__":
    main()
