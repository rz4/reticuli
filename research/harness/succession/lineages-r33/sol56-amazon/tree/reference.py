"""Small independent implementation of Reticuli's identity protocol.

This module is deliberately self contained.  It is both an executable
reference for the conformance vectors and a convenient implementation for
other tools which only need claim and build identities.  Protocol JSON uses
``json.dumps(..., sort_keys=True)`` with every other option left at its
standard-library default.
"""
from __future__ import annotations

import argparse
import copy
import datetime
import hashlib
import json
import math
import os
import re
import stat
import sys
import tomllib
from typing import Any, Iterable

RECIPE = "reticuli.toml"
LEGACY_RECIPE = "claim.toml"
DIGEST = "sha256"
FORMAT = 4
GUIDANCE_KEYS = ("guidance", "request")

_MANIFEST_ENTRY = re.compile(r"^([0-9a-f]{64})[ \t]{2,}(.+)$")


class ReferenceError(Exception):
    """A claim cannot safely be represented by the identity protocol."""


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def _recipe_path(directory: str | os.PathLike[str]) -> str:
    root_dir = os.path.abspath(os.fspath(directory))
    for name in (RECIPE, LEGACY_RECIPE):
        path = _safe(root_dir, name)
        if not os.path.lexists(path):
            continue
        try:
            info = os.lstat(path)
        except OSError as exc:
            raise ReferenceError(f"cannot inspect recipe {name!r}: {exc}") from None
        if not stat.S_ISREG(info.st_mode):
            raise ReferenceError(f"recipe is not a regular file: {name}")
        if info.st_nlink != 1:
            raise ReferenceError(f"recipe has multiple hard links: {name}")
        return path
    raise ReferenceError(f"claim has no {RECIPE} or {LEGACY_RECIPE}")


def _safe(directory: str | os.PathLike[str], name: Any) -> str:
    """Resolve a declared path while refusing traversal and symlink aliases."""
    if not isinstance(name, str) or not name or "\0" in name:
        raise ReferenceError("claim path must be a non-empty relative string")
    if os.path.isabs(name):
        raise ReferenceError(f"claim path is absolute: {name!r}")

    # On the hosts supported by the format, either slash may have arrived in a
    # foreign recipe.  Treat both as separators for traversal checks even when
    # the local OS assigns only one of them that role.
    syntax_parts = name.replace("\\", "/").split("/")
    if ".." in syntax_parts:
        raise ReferenceError(f"claim path escapes its directory: {name!r}")

    base = os.path.realpath(os.path.abspath(os.fspath(directory)))
    candidate = os.path.abspath(os.path.join(base, name))
    try:
        contained = os.path.commonpath((base, candidate)) == base
    except (OSError, ValueError):
        contained = False
    if not contained or candidate == base:
        raise ReferenceError(f"claim path escapes its directory: {name!r}")

    current = base
    for component in name.split(os.sep):
        if component in ("", "."):
            continue
        current = os.path.join(current, component)
        if os.path.lexists(current) and os.path.islink(current):
            raise ReferenceError(f"claim path contains a symlink: {name!r}")

    resolved = os.path.realpath(candidate)
    try:
        real_contained = os.path.commonpath((base, resolved)) == base
    except (OSError, ValueError):
        real_contained = False
    if not real_contained or resolved == base:
        raise ReferenceError(f"claim path escapes its directory: {name!r}")
    return resolved


def _portable_json_values(value: Any, where: str = "recipe") -> None:
    if isinstance(value, (datetime.date, datetime.time)):
        raise ReferenceError(f"{where} contains a TOML date or time")
    if isinstance(value, float) and not math.isfinite(value):
        raise ReferenceError(f"{where} contains a non-finite number")
    if isinstance(value, dict):
        for key, child in value.items():
            _portable_json_values(child, f"{where}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _portable_json_values(child, f"{where}[{index}]")


def _format(recipe: dict[str, Any]) -> int:
    claim = recipe.get("claim")
    if not isinstance(claim, dict):
        raise ReferenceError("recipe requires a [claim] table")
    value = claim.get("format", 1)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ReferenceError("[claim] format must be a positive integer")
    if value > FORMAT:
        raise ReferenceError(
            f"claim format {value} is newer than this reference understands "
            f"(format {FORMAT})"
        )
    return value


def _validate_path(directory: str, value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ReferenceError(f"{label} must be a non-empty path string")
    _safe(directory, value)
    return value


def _load_recipe(directory: str | os.PathLike[str]) -> dict[str, Any]:
    root_dir = os.path.abspath(os.fspath(directory))
    try:
        with open(_recipe_path(root_dir), "rb") as stream:
            recipe = tomllib.load(stream)
    except ReferenceError:
        raise
    except (OSError, tomllib.TOMLDecodeError, UnicodeError, ValueError) as exc:
        raise ReferenceError(f"cannot load claim recipe: {exc}") from None

    if not isinstance(recipe, dict):
        raise ReferenceError("recipe must be a TOML table")
    _portable_json_values(recipe)
    version = _format(recipe)
    claim = recipe["claim"]
    if not isinstance(claim.get("name"), str):
        raise ReferenceError("[claim] name is required and must be a string")

    inputs = claim.get("inputs", [])
    if not isinstance(inputs, list):
        raise ReferenceError("[claim] inputs must be an array of paths")
    for name in inputs:
        _validate_path(root_dir, name, "input")

    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        _validate_path(root_dir, manifest, "inputs_manifest")
        if version < 2:
            raise ReferenceError("inputs_manifest requires claim format 2 or newer")
        # Reading it now makes malformed manifest entries recipe failures.
        for name in _manifest_inputs(root_dir, manifest):
            _validate_path(root_dir, name, "manifest input")

    environment = claim.get("environment")
    if environment is not None:
        _validate_path(root_dir, environment, "environment")

    steps = recipe.get("step", [])
    if not isinstance(steps, list):
        raise ReferenceError("[[step]] entries must form an array")
    for index, step in enumerate(steps, 1):
        if not isinstance(step, dict):
            raise ReferenceError(f"step {index} must be a table")
        kind = step.get("kind")
        if kind not in ("produce", "gate"):
            raise ReferenceError(f"step {index} has unknown kind {kind!r}")
        _validate_path(root_dir, step.get("output"), f"step {index} output")
        if kind == "gate" and not isinstance(step.get("run"), str):
            raise ReferenceError(f"step {index} gate requires a string run command")
        for key in GUIDANCE_KEYS:
            if key in step and not isinstance(step[key], str):
                raise ReferenceError(f"step {index} {key} must be a string")
        if "from" in step and not isinstance(step["from"], str):
            raise ReferenceError(f"step {index} from must be a string")
    return recipe


def load_recipe(directory: str | os.PathLike[str]) -> dict[str, Any]:
    """Parse the preferred recipe file in *directory*.

    The public helper mainly exists for small foreign-tool integrations; root
    computation itself accepts a directory and does not expose parsed TOML in
    its API.
    """
    return _load_recipe(directory)


def _manifest_inputs(directory: str, name: str) -> list[str]:
    path = _safe(directory, name)
    try:
        with open(path, "r", encoding="utf-8", newline=None) as stream:
            lines = stream.readlines()
    except (OSError, UnicodeError) as exc:
        raise ReferenceError(f"cannot read input manifest {name!r}: {exc}") from None

    result: list[str] = []
    for number, raw in enumerate(lines, 1):
        text = raw.strip()
        if not text or text.startswith("#"):
            continue
        matched = _MANIFEST_ENTRY.fullmatch(text)
        entry = (matched.group(2) if matched else text).strip()
        if not entry:
            raise ReferenceError(
                f"input manifest {name!r} has an empty path on line {number}"
            )
        result.append(entry)
    return result


def _inputs(recipe: dict[str, Any], directory: str) -> list[str]:
    claim = recipe["claim"]
    names = list(claim.get("inputs", []))
    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        names.extend(_manifest_inputs(directory, manifest))
        names.append(manifest)
    environment = claim.get("environment")
    if environment is not None:
        names.append(environment)

    result: list[str] = []
    seen: set[str] = set()
    for name in names:
        if name not in seen:
            seen.add(name)
            result.append(name)
    return result


def _hash_declared(directory: str, name: str) -> str:
    path = _safe(directory, name)
    try:
        info = os.lstat(path)
        if not stat.S_ISREG(info.st_mode):
            raise ReferenceError(f"declared file is not a regular file: {name}")
        if info.st_nlink != 1:
            raise ReferenceError(f"declared file has multiple hard links: {name}")
        digest = hashlib.sha256()
        with open(path, "rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
    except ReferenceError:
        raise
    except (OSError, ValueError, TypeError) as exc:
        raise ReferenceError(f"cannot hash declared file {name!r}: {exc}") from None


def _preimage_recipe(recipe: dict[str, Any]) -> dict[str, Any]:
    version = _format(recipe)
    result = copy.deepcopy(recipe)
    if version >= 3:
        steps = result.get("step", [])
        for step in steps:
            if isinstance(step, dict):
                for key in GUIDANCE_KEYS:
                    step.pop(key, None)
        if version >= 4:
            steps.sort(key=_canonical)
    return result


def parts(directory: str | os.PathLike[str]) -> dict[str, str]:
    """Return the canonical string map whose digest is the claim root."""
    root_dir = os.path.abspath(os.fspath(directory))
    recipe = _load_recipe(root_dir)
    result = {
        "digest": DIGEST,
        "recipe": _canonical(_preimage_recipe(recipe)),
    }
    for name in _inputs(recipe, root_dir):
        result["input:" + name] = _hash_declared(root_dir, name)
    for step in recipe.get("step", []):
        default = "generated" if step.get("kind") == "produce" else "pinned"
        if step.get("class", default) not in ("generated", "free"):
            name = step["output"]
            result["pinned:" + name] = _hash_declared(root_dir, name)
    return result


def root(directory: str | os.PathLike[str]) -> str:
    """Compute the SHA-256 content address of the claim in *directory*."""
    payload = _canonical(parts(directory)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _generated_outputs(recipe: dict[str, Any]) -> Iterable[str]:
    for step in recipe.get("step", []):
        if (step.get("kind") == "produce"
                and step.get("class", "generated") in ("generated", "free")
                and "from" not in step):
            yield step["output"]


def build_digest(directory: str | os.PathLike[str]) -> str:
    """Digest the present, claim-owned generated outputs in *directory*."""
    root_dir = os.path.abspath(os.fspath(directory))
    recipe = _load_recipe(root_dir)
    files: list[list[str]] = []
    for name in _generated_outputs(recipe):
        path = _safe(root_dir, name)
        if not os.path.lexists(path):
            continue
        files.append([name, _hash_declared(root_dir, name)])
    files.sort(key=lambda item: item[0])
    return hashlib.sha256(_canonical(files).encode("utf-8")).hexdigest()


# Historical descriptive spelling retained for tiny interoperability scripts.
realization_digest = build_digest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m reticuli.reference",
        description="compute Reticuli identity protocol digests",
    )
    parser.add_argument(
        "operation",
        choices=("root", "digest", "build-digest", "build_digest"),
    )
    parser.add_argument("directory")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.operation == "root":
            answer = root(args.directory)
        else:
            answer = build_digest(args.directory)
    except ReferenceError as exc:
        print(f"reticuli.reference: {exc}", file=sys.stderr)
        return 1
    print(answer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DIGEST", "FORMAT", "LEGACY_RECIPE", "RECIPE", "ReferenceError",
    "build_digest", "load_recipe", "main", "parts", "realization_digest",
    "root",
]
