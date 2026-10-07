"""Independent, standard-library implementation of claim identity.

This module intentionally does not call the kernel's identity implementation.
It can also be used by the language-neutral vector runner::

    python -m reticuli.reference root CLAIM_DIRECTORY
    python -m reticuli.reference digest CLAIM_DIRECTORY
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import stat
import tomllib
from pathlib import Path


class ClaimError(Exception):
    """A recipe or declared file cannot be used to compute an identity."""


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True)


def _digest(value: object) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _safe(directory: os.PathLike[str] | str, name: str) -> Path:
    if not isinstance(name, str) or not name or os.path.isabs(name):
        raise ClaimError(f"unsafe claim path: {name!r}")
    parts = name.replace("\\", "/").split("/")
    if ".." in parts or "" in parts:
        raise ClaimError(f"unsafe claim path: {name!r}")
    base = Path(directory).resolve()
    current = base
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise ClaimError(f"symlink in claim path: {name!r}")
    path = (base / name).resolve()
    if path == base or not path.is_relative_to(base):
        raise ClaimError(f"claim path escapes directory: {name!r}")
    return path


def _hash_file(path: Path) -> str:
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ClaimError(f"not a single-link regular file: {path}")
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError as exc:
        raise ClaimError(f"cannot hash {path}: {exc}") from exc


def _json_compatible(value: object) -> bool:
    if isinstance(value, (datetime.date, datetime.time)):
        return False
    if isinstance(value, dict):
        return all(isinstance(key, str) and _json_compatible(item)
                   for key, item in value.items())
    if isinstance(value, list):
        return all(_json_compatible(item) for item in value)
    return value is None or isinstance(value, (str, int, float, bool))


def load_recipe(directory: os.PathLike[str] | str) -> dict:
    """Read either recipe name, preferring the canonical name."""
    path = next((candidate for name in ("reticuli.toml", "claim.toml")
                 if (candidate := _safe(directory, name)).is_file()), None)
    if path is None:
        raise ClaimError(f"no reticuli.toml or claim.toml in {directory}")
    try:
        with path.open("rb") as source:
            recipe = tomllib.load(source)
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ClaimError(f"cannot read recipe {path}: {exc}") from exc
    if not _json_compatible(recipe):
        raise ClaimError("recipe contains unsupported values")
    claim = recipe.get("claim")
    if not isinstance(claim, dict) or not isinstance(claim.get("name"), str):
        raise ClaimError("recipe needs [claim] with a string name")
    version = claim.get("format", 1)
    if type(version) is not int or version < 1 or version > 4:
        raise ClaimError(f"unsupported claim format: {version!r}")
    inputs = claim.get("inputs", [])
    if not isinstance(inputs, list):
        raise ClaimError("claim inputs must be a list")
    for name in inputs:
        _safe(directory, name)
    for field in ("inputs_manifest", "environment"):
        if field in claim:
            _safe(directory, claim[field])
    steps = recipe.get("step", [])
    if not isinstance(steps, list):
        raise ClaimError("recipe steps must be a list")
    for step in steps:
        if not isinstance(step, dict) or step.get("kind") not in ("produce", "gate"):
            raise ClaimError("unknown step kind")
        _safe(directory, step.get("output"))
        if step["kind"] == "gate" and not isinstance(step.get("run"), str):
            raise ClaimError("gate step needs a run command")
        classification = step.get("class", "generated" if step["kind"] == "produce" else "pinned")
        if classification not in ("generated", "pinned", "validated"):
            raise ClaimError(f"unknown step class: {classification!r}")
        if "from" in step and not isinstance(step["from"], str):
            raise ClaimError("step from must be a string")
    return recipe


def _manifest_inputs(directory: os.PathLike[str] | str, name: str) -> list[str]:
    try:
        lines = _safe(directory, name).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise ClaimError(f"cannot read inputs manifest {name}: {exc}") from exc
    names = []
    for number, line in enumerate(lines, 1):
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        if re.match(r"^[0-9a-f]{64}  ", entry):
            entry = entry[66:]
        if not entry or entry != entry.strip():
            raise ClaimError(f"bad inputs manifest entry on line {number}")
        _safe(directory, entry)
        names.append(entry)
    return names


def _inputs(recipe: dict, directory: os.PathLike[str] | str) -> list[str]:
    claim = recipe["claim"]
    names = list(claim.get("inputs", []))
    if "inputs_manifest" in claim:
        name = claim["inputs_manifest"]
        names.extend((name, *_manifest_inputs(directory, name)))
    if "environment" in claim:
        names.append(claim["environment"])
    return list(dict.fromkeys(names))


def _preimage_recipe(recipe: dict) -> dict:
    version = recipe["claim"].get("format", 1)
    if version < 3 or "step" not in recipe:
        return recipe
    result = dict(recipe)
    steps = [{key: value for key, value in step.items()
              if key not in ("guidance", "request")}
             for step in recipe["step"]]
    if version >= 4:
        steps.sort(key=_json)
    result["step"] = steps
    return result


def root(directory: os.PathLike[str] | str) -> str:
    """Compute the content address of a claim directory."""
    recipe = load_recipe(directory)
    parts = {"digest": "sha256", "recipe": _json(_preimage_recipe(recipe))}
    for name in _inputs(recipe, directory):
        parts["input:" + name] = _hash_file(_safe(directory, name))
    for step in recipe.get("step", []):
        classification = step.get("class", "generated" if step["kind"] == "produce" else "pinned")
        if classification != "generated":
            name = step["output"]
            parts["pinned:" + name] = _hash_file(_safe(directory, name))
    return _digest(parts)


def build_digest(directory: os.PathLike[str] | str) -> str:
    """Digest present generated outputs, excluding outputs supplied by a component."""
    recipe = load_recipe(directory)
    files = []
    for step in recipe.get("step", []):
        if (step["kind"] == "produce" and step.get("class", "generated") == "generated"
                and "from" not in step):
            name = step["output"]
            path = _safe(directory, name)
            if path.exists():
                files.append([name, _hash_file(path)])
    files.sort(key=lambda item: item[0])
    return _digest(files)


def main() -> int:
    parser = argparse.ArgumentParser(description="independent claim identity calculator")
    parser.add_argument("operation", choices=("root", "digest", "build-digest"))
    parser.add_argument("directory")
    args = parser.parse_args()
    try:
        print(root(args.directory) if args.operation == "root" else build_digest(args.directory))
    except ClaimError as exc:
        parser.exit(1, f"{exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
