"""Independent, standard-library implementation of claim identity.

The recipe is serialized twice: first as the value of ``parts['recipe']``,
then as part of the canonical JSON map whose SHA-256 is the root.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
import tomllib
from pathlib import Path


class ReferenceError(ValueError):
    """A claim cannot be interpreted or safely hashed."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True).encode("utf-8")


def _path(directory: str | os.PathLike[str], name: str) -> Path:
    if not isinstance(name, str) or not name or os.path.isabs(name):
        raise ReferenceError(f"unsafe claim path: {name!r}")
    parts = name.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ReferenceError(f"unsafe claim path: {name!r}")
    root = Path(directory).resolve()
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise ReferenceError(f"symlink in claim path: {name!r}")
    if not current.resolve().is_relative_to(root):
        raise ReferenceError(f"claim path escapes directory: {name!r}")
    return current


def _hash_file(path: Path) -> str:
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ReferenceError(f"not a regular, uniquely linked file: {path}")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError as exc:
        raise ReferenceError(f"cannot hash {path}: {exc}") from exc


def _json_compatible(value: object) -> bool:
    if value is None or isinstance(value, (str, bool, int)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_json_compatible(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _json_compatible(item)
                   for key, item in value.items())
    return False


def load_recipe(directory: str | os.PathLike[str]) -> dict:
    """Parse either recipe filename, preferring the canonical spelling."""
    path = None
    for name in ("reticuli.toml", "claim.toml"):
        candidate = _path(directory, name)
        if candidate.exists():
            path = candidate
            break
    if path is None:
        raise ReferenceError(f"no reticuli.toml or claim.toml in {directory}")
    try:
        with path.open("rb") as stream:
            document = tomllib.load(stream)
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ReferenceError(f"cannot read recipe {path}: {exc}") from exc
    if not _json_compatible(document):
        raise ReferenceError("recipe contains values without a canonical JSON form")
    claim = document.get("claim")
    if not isinstance(claim, dict) or not isinstance(claim.get("name"), str):
        raise ReferenceError("recipe needs a [claim] table with a string name")
    version = claim.get("format", 1)
    if type(version) is not int or version < 1 or version > 4:
        raise ReferenceError(f"unsupported claim format: {version!r}")
    steps = document.get("step", [])
    if not isinstance(steps, list) or any(not isinstance(step, dict) for step in steps):
        raise ReferenceError("recipe step must be an array of tables")
    inputs = claim.get("inputs", [])
    if not isinstance(inputs, list) or any(not isinstance(item, str) for item in inputs):
        raise ReferenceError("claim inputs must be an array of paths")
    for name in inputs:
        _path(directory, name)
    for step in steps:
        kind = step.get("kind")
        if kind not in ("produce", "gate"):
            raise ReferenceError(f"unknown step kind: {kind!r}")
        _path(directory, step.get("output"))
        if kind == "gate" and not isinstance(step.get("run"), str):
            raise ReferenceError(f"gate {step['output']!r} needs a run command")
    return document


def _inputs(document: dict, directory: str | os.PathLike[str]) -> list[str]:
    claim = document["claim"]
    names = list(claim.get("inputs", []))
    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        source = _path(directory, manifest)
        names.append(manifest)
        try:
            lines = source.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            raise ReferenceError(f"cannot read inputs manifest {manifest!r}: {exc}") from exc
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            match = re.fullmatch(r"[0-9a-fA-F]{64}  (.+)", line)
            name = match.group(1) if match else line
            _path(directory, name)
            names.append(name)
    environment = claim.get("environment")
    if environment is not None:
        names.append(environment)
    return names


def _preimage_recipe(document: dict) -> dict:
    version = document["claim"].get("format", 1)
    if version < 3:
        return document
    result = dict(document)
    steps = [{key: value for key, value in step.items()
              if key not in ("guidance", "request")}
             for step in document.get("step", [])]
    if version >= 4:
        steps.sort(key=_canonical)
    if "step" in result:
        result["step"] = steps
    return result


def root(directory: str | os.PathLike[str]) -> str:
    """Return the SHA-256 identity of a claim's criteria and pinned bytes."""
    document = load_recipe(directory)
    parts = {"digest": "sha256",
             "recipe": _canonical(_preimage_recipe(document)).decode("utf-8")}
    for name in _inputs(document, directory):
        parts["input:" + name] = _hash_file(_path(directory, name))
    for step in document.get("step", []):
        step_class = step.get("class", "generated" if step["kind"] == "produce" else "pinned")
        if step_class not in ("generated", "free"):
            name = step["output"]
            parts["pinned:" + name] = _hash_file(_path(directory, name))
    return hashlib.sha256(_canonical(parts)).hexdigest()


def build_digest(directory: str | os.PathLike[str]) -> str:
    """Hash present locally generated outputs as sorted name/hash pairs."""
    document = load_recipe(directory)
    outputs = []
    for step in document.get("step", []):
        if (step["kind"] != "produce" or
                step.get("class", "generated") not in ("generated", "free") or
                "from" in step):
            continue
        name = step["output"]
        path = _path(directory, name)
        if path.exists() or path.is_symlink():
            outputs.append([name, _hash_file(path)])
    outputs.sort(key=lambda item: item[0])
    return hashlib.sha256(_canonical(outputs)).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Reference claim identity implementation")
    parser.add_argument("operation", choices=("root", "digest", "build-digest"))
    parser.add_argument("directory")
    args = parser.parse_args()
    try:
        print(root(args.directory) if args.operation == "root" else build_digest(args.directory))
    except ReferenceError as exc:
        parser.exit(1, f"{exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
