"""Shared constants and small primitives for the Reticuli kernel.

This module is intentionally limited to the Python standard library.  It is
the lowest layer of the implementation: in particular, it performs no network
operations.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
import platform
import shutil
import sys
import tempfile
from typing import Any


class ClaimError(Exception):
    """A claim is malformed or cannot safely be handled.

    Public kernel operations use this exception for expected refusals, so bad
    claim data does not leak an implementation-specific parsing or filesystem
    exception through the API.
    """


# Identity and on-disk protocol.
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

# Environment protocol shared by the kernel layers.
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
_KEEP_ENV = (
    "PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "TZ", "RETICULI_JAILED",
)

# Policy defaults.  Their names and useful types form the core seam; callers
# may impose tighter limits.
GATE_TIMEOUT = 120.0
FURNISH_TIMEOUT = 600.0
PRODUCER_TIMEOUT = 1200.0
TOLERANCE = 2.0
MUTANT_CEILING = 100
MUTANT_FLOOR = 10
MUTANT_HEADROOM = 20

COST_KEYS = ("usd", "tokens", "calls", "seconds")
COST_LADDER = ("usd", "tokens", "calls", "seconds")
COST_UNITS = ("usd", "tokens", "calls", "seconds")
GUIDANCE_KEYS = ("guidance", "request")
KINDS = frozenset({"produce", "gate"})
_SHELL = os.environ.get("SHELL") or "/bin/sh"


def _now() -> str:
    """Return the current UTC second in the record timestamp format."""

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _hash_file(path: str | os.PathLike[str]) -> str:
    """Return the lowercase SHA-256 digest of a file's bytes."""

    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe(root: str | os.PathLike[str], name: str) -> str:
    """Resolve a claim-relative name, refusing escapes and symlink aliases.

    The returned path is absolute and uses the real spelling of *root*.
    Existing symlink components are refused even when their target remains
    within the claim; this keeps declared names from aliasing other content.
    The final component need not exist, since output paths are checked before
    they are created.
    """

    if not isinstance(name, str) or not name or "\x00" in name:
        raise ClaimError("claim path must be a non-empty relative string")
    if os.path.isabs(name):
        raise ClaimError(f"claim path is absolute: {name!r}")

    # Refuse traversal as syntax, rather than accepting a path merely because
    # normalisation happens to bring it back under the root.
    components = name.split(os.sep)
    if os.path.altsep:
        expanded: list[str] = []
        for component in components:
            expanded.extend(component.split(os.path.altsep))
        components = expanded
    if any(component == ".." for component in components):
        raise ClaimError(f"claim path escapes its directory: {name!r}")

    base = os.path.realpath(os.fspath(root))
    candidate = os.path.abspath(os.path.join(base, name))
    try:
        contained = os.path.commonpath((base, candidate)) == base
    except (OSError, ValueError):
        contained = False
    if not contained or candidate == base:
        raise ClaimError(f"claim path escapes its directory: {name!r}")

    current = base
    for component in components:
        if component in ("", "."):
            continue
        current = os.path.join(current, component)
        if os.path.lexists(current) and os.path.islink(current):
            raise ClaimError(f"claim path contains a symlink: {name!r}")

    # A final realpath check also protects against unusual host path syntax.
    resolved = os.path.realpath(candidate)
    try:
        inside_real = os.path.commonpath((base, resolved)) == base
    except (OSError, ValueError):
        inside_real = False
    if not inside_real or resolved == base:
        raise ClaimError(f"claim path escapes its directory: {name!r}")
    return resolved


def _write_json(path: str | os.PathLike[str], value: Any) -> None:
    """Atomically replace *path* with a deterministic JSON document."""

    target = os.path.abspath(os.fspath(path))
    parent = os.path.dirname(target) or os.curdir
    fd = -1
    temporary = ""
    try:
        fd, temporary = tempfile.mkstemp(prefix=".reticuli-json-", dir=parent)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            fd = -1
            json.dump(value, stream, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        temporary = ""
    finally:
        if fd >= 0:
            os.close(fd)
        if temporary:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def _copy_into(source: str | os.PathLike[str], target: str | os.PathLike[str]) -> str:
    """Copy one file into place, creating its destination directory."""

    destination = os.fspath(target)
    parent = os.path.dirname(destination)
    if parent:
        os.makedirs(parent, exist_ok=True)
    shutil.copyfile(os.fspath(source), destination)
    return destination


def _judging_host() -> dict[str, str]:
    """Describe the host fields used in verdict and record diagnostics."""

    return {
        "platform": platform.system().lower() or sys.platform,
        "machine": platform.machine(),
        "runtime": f"{platform.python_implementation()} {platform.python_version()}",
    }
