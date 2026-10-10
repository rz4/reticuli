"""Independent, standard-library reference for claim identity vectors.

The root hashes a canonical JSON map containing the parsed recipe and the
digests of its declared pinned files. Generated files affect only the build
digest, never the root.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import stat
import sys
import tomllib
from pathlib import Path


class ClaimError(Exception):
    """A claim cannot be assigned an identity."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True).encode("utf-8")


def _path(directory: Path, name: str) -> Path:
    if not isinstance(name, str) or not name or os.path.isabs(name):
        raise ClaimError(f"invalid claim path: {name!r}")
    components = name.split(os.sep)
    if any(part in ("", ".", "..") for part in components):
        raise ClaimError(f"invalid claim path: {name!r}")
    path = directory
    for part in components:
        path = path / part
        if path.is_symlink():
            raise ClaimError(f"symlink in claim path: {name!r}")
    return path


def _hash_file(path: Path) -> str:
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


def _recipe(directory: Path) -> dict:
    for name in ("reticuli.toml", "claim.toml"):
        path = _path(directory, name)
        if path.exists():
            _hash_file(path)
            try:
                with path.open("rb") as stream:
                    parsed = tomllib.load(stream)
            except (OSError, tomllib.TOMLDecodeError) as exc:
                raise ClaimError(f"cannot read recipe: {exc}") from exc
            break
    else:
        raise ClaimError(f"no recipe in {directory}")
    claim = parsed.get("claim")
    if not isinstance(claim, dict) or not isinstance(claim.get("name"), str):
        raise ClaimError("recipe requires [claim] with a string name")
    version = claim.get("format", 1)
    if type(version) is not int or version < 1 or version > 4:
        raise ClaimError(f"unsupported claim format: {version!r}")
    steps = parsed.get("step", [])
    if not isinstance(steps, list) or any(not isinstance(s, dict) for s in steps):
        raise ClaimError("recipe step must be an array of tables")
    for step in steps:
        if step.get("kind") not in ("produce", "gate"):
            raise ClaimError(f"invalid step kind: {step.get('kind')!r}")
        _path(directory, step.get("output"))
        if step["kind"] == "gate" and not isinstance(step.get("run"), str):
            raise ClaimError("gate requires a run command")
    return parsed


def _inputs(recipe: dict, directory: Path) -> list[str]:
    claim = recipe["claim"]
    names = claim.get("inputs", [])
    if not isinstance(names, list) or any(not isinstance(n, str) for n in names):
        raise ClaimError("claim inputs must be an array of paths")
    result = list(names)
    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        path = _path(directory, manifest)
        _hash_file(path)
        result.append(manifest)
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            raise ClaimError(f"cannot read inputs manifest: {exc}") from exc
        for line in lines:
            entry = line.strip()
            if not entry or entry.startswith("#"):
                continue
            annotated = re.fullmatch(r"[0-9a-f]{64}  (.+)", entry)
            result.append(annotated.group(1) if annotated else entry)
    if "environment" in claim:
        result.append(claim["environment"])
    return list(dict.fromkeys(result))


def _preimage_recipe(parsed: dict) -> dict:
    result = copy.deepcopy(parsed)
    version = parsed["claim"].get("format", 1)
    if version >= 3:
        for step in result.get("step", []):
            step.pop("guidance", None)
            step.pop("request", None)
    if version >= 4 and "step" in result:
        result["step"].sort(key=_canonical)
    return result


def _step_class(step: dict) -> str:
    return step.get("class", "generated" if step["kind"] == "produce" else "pinned")


def root(directory: os.PathLike[str] | str) -> str:
    """Compute the SHA-256 root of a claim directory."""
    directory = Path(directory).resolve()
    parsed = _recipe(directory)
    parts = {"digest": "sha256", "recipe": _canonical(_preimage_recipe(parsed)).decode("ascii")}
    for name in _inputs(parsed, directory):
        parts["input:" + name] = _hash_file(_path(directory, name))
    for step in parsed.get("step", []):
        if _step_class(step) not in ("generated", "free"):
            name = step["output"]
            parts["pinned:" + name] = _hash_file(_path(directory, name))
    return hashlib.sha256(_canonical(parts)).hexdigest()


def build_digest(directory: os.PathLike[str] | str) -> str:
    """Hash present, locally generated outputs in name order."""
    directory = Path(directory).resolve()
    parsed = _recipe(directory)
    entries = []
    for step in parsed.get("step", []):
        if _step_class(step) not in ("generated", "free") or "from" in step:
            continue
        name = step["output"]
        path = _path(directory, name)
        if os.path.lexists(path):
            entries.append([name, _hash_file(path)])
    entries.sort(key=lambda entry: entry[0])
    return hashlib.sha256(_canonical(entries)).hexdigest()


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2 or argv[0] not in ("root", "digest"):
        print("usage: python -m reticuli.reference {root|digest} CLAIM", file=sys.stderr)
        return 2
    try:
        print(root(argv[1]) if argv[0] == "root" else build_digest(argv[1]))
    except ClaimError as exc:
        print(f"reference: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
