"""Core constants and filesystem boundaries for content-addressed claims."""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import shutil
import stat
import tempfile


class ClaimError(Exception):
    """A claim or filesystem operation was refused with a reason."""


NAMESPACE = "reticuli"
DIGEST = "sha256"
FORMAT = 4
STORE = ".reticuli"
MANIFEST = ".reticuli/manifest.json"
RECIPE = "reticuli.toml"
LEGACY_RECIPE = "claim.toml"
LEDGER = ".reticuli/ledger.jsonl"
USAGE = ".reticuli/usage.json"
MUTATION_RESIDUE = ".reticuli/mutation_score.json"
SIGN_DIR = ".reticuli/mint"
SIGN_NAMESPACE = "reticuli.mint"

_JAILED = "RETICULI_JAILED"
_ENV_CACHE = "RETICULI_ENV_CACHE"
_ENV_CLAIM = "RETICULI_CLAIM"
_ENV_MODEL = "RETICULI_MODEL"
_ENV_OUTPUT = "RETICULI_OUTPUT"
_ENV_OUTPUTS = "RETICULI_OUTPUTS"
_ENV_REQUEST = "RETICULI_REQUEST"
_ENV_SIGNERS = "RETICULI_SIGNERS"
_ENV_TIMEOUT = "RETICULI_GATE_TIMEOUT"
_ENV_TOLERANCE = "RETICULI_TOLERANCE"
_ENV_USAGE = "RETICULI_USAGE"
_ENV_VENDOR = "RETICULI_VENDOR"
_KEEP_ENV = ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "TZ",
             "RETICULI_JAILED")

GATE_TIMEOUT = 120.0
FURNISH_TIMEOUT = 300.0
PRODUCER_TIMEOUT = 600.0
TOLERANCE = 2.0
MUTANT_CEILING = 100
MUTANT_FLOOR = 0.0
MUTANT_HEADROOM = 0.0
COST_KEYS = ("usd", "tokens", "calls", "seconds")
COST_LADDER = COST_KEYS
COST_UNITS = COST_KEYS
GUIDANCE_KEYS = ("guidance", "request")
KINDS = frozenset({"produce", "gate"})
_SHELL = "/bin/sh"


def _now() -> str:
    """Return the current UTC time in the record timestamp format."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe(claim_dir: os.PathLike[str] | str, name: os.PathLike[str] | str) -> str:
    """Resolve a recipe path while refusing escapes and symbolic links."""
    try:
        relative = os.fspath(name)
    except TypeError as exc:
        raise ClaimError(f"invalid claim path: {name!r}") from exc
    if not isinstance(relative, str) or not relative or os.path.isabs(relative):
        raise ClaimError(f"invalid claim path: {relative!r}")
    components = relative.split(os.sep)
    if any(component in ("", ".", "..") for component in components):
        raise ClaimError(f"invalid claim path: {relative!r}")
    base = os.path.realpath(claim_dir)
    path = base
    for component in components:
        path = os.path.join(path, component)
        if os.path.islink(path):
            raise ClaimError(f"symbolic link in claim path: {relative!r}")
    resolved = os.path.realpath(path)
    if os.path.commonpath((base, resolved)) != base or resolved == base:
        raise ClaimError(f"claim path escapes directory: {relative!r}")
    return resolved


def _hash_file(path: os.PathLike[str] | str) -> str:
    """Hash the bytes of a regular, singly linked file with SHA-256."""
    try:
        info = os.lstat(path)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ClaimError(f"not a singly linked regular file: {path}")
        digest = hashlib.sha256()
        with open(path, "rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
    except OSError as exc:
        raise ClaimError(f"cannot hash {path}: {exc}") from exc


def _write_json(path: os.PathLike[str] | str, value: object) -> None:
    """Atomically replace a JSON file with a complete, UTF-8 document."""
    target = os.fspath(path)
    parent = os.path.dirname(os.path.abspath(target))
    os.makedirs(parent, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=parent,
                                         prefix=".tmp-", delete=False) as output:
            temporary = output.name
            json.dump(value, output, sort_keys=True)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, target)
    finally:
        if temporary is not None and os.path.exists(temporary):
            os.unlink(temporary)


def _copy_into(source: os.PathLike[str] | str,
               destination: os.PathLike[str] | str) -> str:
    """Copy one regular file to its destination, creating parent directories."""
    _hash_file(source)
    destination = os.fspath(destination)
    os.makedirs(os.path.dirname(os.path.abspath(destination)), exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def _judging_host() -> dict[str, str]:
    """Describe the local runtime for diagnostics."""
    import platform

    return {"platform": platform.system().lower(),
            "machine": platform.machine(),
            "runtime": platform.python_implementation() + " " + platform.python_version()}
