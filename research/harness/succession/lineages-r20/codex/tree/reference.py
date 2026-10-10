"""Small, independent reference implementation of claim identity.

The preimages use Python's default JSON separators and ASCII escaping.
The recipe is serialized to a JSON *string* inside the root's parts map.
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
    """An invalid recipe or declared file."""


def _json(value: object) -> str:
    try:
        return json.dumps(value, sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise ReferenceError(f"cannot serialize recipe: {exc}") from exc


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _path(directory: str | os.PathLike[str], name: str) -> Path:
    if (not isinstance(name, str) or not name or os.path.isabs(name)
            or any(part in ("", ".", "..") for part in name.split("/"))):
        raise ReferenceError(f"unsafe claim path: {name!r}")
    path = Path(directory).resolve()
    for part in name.split("/"):
        path = path / part
        if path.is_symlink():
            raise ReferenceError(f"symlink in claim path: {name!r}")
    return path


def _hash_file(path: Path) -> str:
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ReferenceError(f"not a regular, unaliased file: {path}")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
    except OSError as exc:
        raise ReferenceError(f"cannot hash {path}: {exc}") from exc


def _recipe(directory: str | os.PathLike[str]) -> dict:
    for name in ("reticuli.toml", "claim.toml"):
        path = _path(directory, name)
        if path.exists() or path.is_symlink():
            _hash_file(path)
            try:
                with path.open("rb") as stream:
                    parsed = tomllib.load(stream)
            except (OSError, tomllib.TOMLDecodeError) as exc:
                raise ReferenceError(f"cannot read recipe: {exc}") from exc
            break
    else:
        raise ReferenceError("no reticuli.toml or claim.toml")
    claim = parsed.get("claim")
    if not isinstance(claim, dict) or not isinstance(claim.get("name"), str):
        raise ReferenceError("recipe needs [claim] with a string name")
    version = claim.get("format", 1)
    if type(version) is not int or version < 1 or version > 4:
        raise ReferenceError(f"unsupported claim format: {version!r}")
    steps = parsed.get("step", [])
    if not isinstance(steps, list) or any(not isinstance(step, dict) for step in steps):
        raise ReferenceError("step must be an array of tables")
    for step in steps:
        kind = step.get("kind")
        if kind not in ("produce", "gate"):
            raise ReferenceError(f"invalid step kind: {kind!r}")
        _path(directory, step.get("output"))
        if kind == "gate" and not isinstance(step.get("run"), str):
            raise ReferenceError("gate step needs a run command")
        cls = step.get("class", "generated" if kind == "produce" else "pinned")
        if cls not in ("generated", "free", "pinned", "exact", "validated"):
            raise ReferenceError(f"invalid step class: {cls!r}")
    return parsed


def _inputs(parsed: dict, directory: str | os.PathLike[str]) -> list[str]:
    claim = parsed["claim"]
    names = claim.get("inputs", [])
    if not isinstance(names, list) or any(not isinstance(name, str) for name in names):
        raise ReferenceError("claim inputs must be an array of paths")
    names = list(names)
    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        source = _path(directory, manifest)
        _hash_file(source)
        names.append(manifest)
        try:
            lines = source.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            raise ReferenceError(f"cannot read inputs manifest: {exc}") from exc
        for number, raw in enumerate(lines, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            match = re.fullmatch(r"[0-9a-f]{64}  (.+)", line)
            if not match and re.match(r"[0-9a-f]{64}\s", line):
                raise ReferenceError(f"invalid inputs manifest entry on line {number}")
            names.append(match.group(1) if match else line)
    environment = claim.get("environment")
    if environment is not None:
        names.append(environment)
    for name in names:
        _path(directory, name)
    return names


def _preimage_recipe(parsed: dict) -> dict:
    version = parsed["claim"].get("format", 1)
    if version < 3:
        return parsed
    result = dict(parsed)
    steps = [{key: value for key, value in step.items()
              if key not in ("guidance", "request")}
             for step in parsed.get("step", [])]
    if version >= 4:
        steps.sort(key=_json)
    if "step" in parsed:
        result["step"] = steps
    return result


def root(directory: str | os.PathLike[str]) -> str:
    """Compute the claim's content address from its declared pinned bytes."""
    parsed = _recipe(directory)
    parts = {"digest": "sha256", "recipe": _json(_preimage_recipe(parsed))}
    for name in _inputs(parsed, directory):
        parts["input:" + name] = _hash_file(_path(directory, name))
    for step in parsed.get("step", []):
        cls = step.get("class", "generated" if step["kind"] == "produce" else "pinned")
        if cls not in ("generated", "free"):
            name = step["output"]
            parts["pinned:" + name] = _hash_file(_path(directory, name))
    return _sha(_json(parts).encode("utf-8"))


def build_digest(directory: str | os.PathLike[str]) -> str:
    """Hash present local generated outputs, omitting supplied outputs."""
    parsed = _recipe(directory)
    entries = []
    for step in parsed.get("step", []):
        if step["kind"] != "produce" or "from" in step:
            continue
        if step.get("class", "generated") not in ("generated", "free"):
            continue
        name = step["output"]
        path = _path(directory, name)
        if path.exists() or path.is_symlink():
            entries.append([name, _hash_file(path)])
    entries.sort(key=lambda entry: entry[0])
    return _sha(_json(entries).encode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reference claim identity")
    parser.add_argument("operation", choices=("root", "digest", "build-digest"))
    parser.add_argument("directory")
    args = parser.parse_args(argv)
    try:
        print(root(args.directory) if args.operation == "root" else build_digest(args.directory))
    except ReferenceError as exc:
        parser.exit(1, f"reference: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
