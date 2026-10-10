"""Shared, standard-library-only primitives for the Reticuli kernel.

The claim directory is the trust boundary. Names supplied by a recipe are
checked before they can be used to read, copy, or hash files.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import platform
import shutil
import stat
import sys
import tempfile


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
_KEEP_ENV = ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "TZ", _JAILED)

GATE_TIMEOUT = 120.0
FURNISH_TIMEOUT = 300.0
PRODUCER_TIMEOUT = 3600.0
TOLERANCE = 2.0
MUTANT_CEILING = 100
MUTANT_FLOOR = 0.0
MUTANT_HEADROOM = 0.1
COST_KEYS = ("usd", "tokens", "calls", "seconds")
COST_LADDER = COST_KEYS
COST_UNITS = COST_KEYS
GUIDANCE_KEYS = ("guidance", "request")
KINDS = frozenset({"produce", "gate"})
_SHELL = os.environ.get("SHELL", "/bin/sh")


class ClaimError(Exception):
    """A claim cannot be safely or meaningfully processed."""


def _safe(directory: str | os.PathLike[str], name: str) -> str:
    """Resolve a recipe path beneath *directory*, refusing filesystem aliases."""
    if not isinstance(name, str) or not name or os.path.isabs(name):
        raise ClaimError(f"invalid claim path: {name!r}")
    # Check components as written: normalizing first would hide '..'.
    components = name.replace("\\", "/").split("/")
    if any(part in ("", ".", "..") for part in components):
        raise ClaimError(f"invalid claim path: {name!r}")
    base = os.path.realpath(os.fspath(directory))
    path = base
    for part in components:
        path = os.path.join(path, part)
        if os.path.islink(path):
            raise ClaimError(f"symlink in claim path: {name!r}")
    resolved = os.path.realpath(path)
    if os.path.commonpath((base, resolved)) != base or resolved == base:
        raise ClaimError(f"claim path escapes directory: {name!r}")
    return resolved


def _hash_file(path: str | os.PathLike[str]) -> str:
    """Hash a regular, singly linked file's unmodified bytes."""
    try:
        info = os.lstat(path)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ClaimError(f"not a regular singly linked file: {path}")
        digest = hashlib.sha256()
        with open(path, "rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
    except OSError as exc:
        raise ClaimError(f"cannot hash {path}: {exc}") from exc


def _write_json(path: str | os.PathLike[str], value: object) -> None:
    """Replace a JSON file atomically within its own directory."""
    path = os.fspath(path)
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=parent,
                                         prefix=".reticuli-", delete=False) as out:
            temp_path = out.name
            json.dump(value, out, sort_keys=True)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path is not None and os.path.exists(temp_path):
            os.unlink(temp_path)


def _now() -> str:
    """Current UTC time in the record format."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _copy_into(source: str | os.PathLike[str], target: str | os.PathLike[str]) -> None:
    """Copy a regular file to a destination, creating its parent directory."""
    _hash_file(source)
    target = os.fspath(target)
    os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
    shutil.copyfile(source, target)


def _judging_host() -> dict[str, str]:
    """Describe the host and interpreter that judged a claim."""
    return {
        "platform": sys.platform,
        "machine": platform.machine(),
        "runtime": f"{platform.python_implementation()} {platform.python_version()}",
    }
