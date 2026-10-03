"""Shared helpers for the exchange layer (spec/layers.md).

Every value and helper here is derived from the kernel's own pinned
surface (`reticuli.kernel`) -- constants read straight off it, path and
hashing rules reimplemented to the same spec (spec/identity.md) rather
than reaching into a kernel private module. No layer above the kernel may
depend on an unpinned kernel name; this module is where the layers above
share the helpers that would otherwise tempt that.
"""
import datetime
import fcntl
import hashlib
import json
import os
import shutil

from reticuli import kernel

STORE = kernel.STORE
LEDGER = kernel.LEDGER
RECIPE = "claim.toml"


def safe_path(base: str, name: str) -> str:
    """Resolve a claim-declared name under `base`, refusing the same
    aliasing a kernel claim refuses (spec/identity.md, "File hashing
    rules"): an absolute or empty name, any `..` or empty component, and
    any component that is a symlink -- even one whose target stays inside
    the claim.
    """
    if not isinstance(name, str) or name == "":
        raise kernel.ClaimError("a claim path must be a non-empty string")
    if os.path.isabs(name):
        raise kernel.ClaimError(f"a claim path must not be absolute: {name!r}")

    parts = name.split("/")
    for part in parts:
        if part in ("", ".", ".."):
            raise kernel.ClaimError(f"unsafe path component {part!r} in {name!r}")

    base_real = os.path.realpath(base)
    probe = base_real
    for part in parts:
        probe = os.path.join(probe, part)
        if os.path.islink(probe):
            raise kernel.ClaimError(f"a claim path must not cross a symlink: {name!r}")

    candidate = os.path.join(base_real, *parts)
    real = os.path.realpath(candidate)
    if real != candidate or not (real == base_real or real.startswith(base_real + os.sep)):
        raise kernel.ClaimError(f"path escapes the claim: {name!r}")
    return real


def hash_bytes(data: bytes) -> str:
    """The sha256 hex digest of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def read_json(path: str):
    """Parse a JSON file off disk."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str, obj) -> None:
    """Write `obj` as JSON to `path`, atomically (write-temp, then rename)."""
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, sort_keys=True)
    os.replace(tmp, path)


def declared_inputs(parsed: dict) -> list:
    """The claim's declared pinned inputs, from a recipe already parsed by
    `kernel.load_recipe`: the manifest file itself first, then every path
    it lists (format 2), or else the recipe's own `inputs` list.
    """
    claim = parsed.get("claim", {})
    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        return [manifest] + list(parsed.get("_manifest_inputs", []))
    return list(claim.get("inputs", []))


def step_output(step: dict):
    """A step's declared output name, or `None`."""
    return step.get("output")


def copy_into(base: str, dest: str, names) -> str:
    """Copy each named file from `base` into `dest`, preserving its
    relative path, confined by `safe_path`. A name absent on disk is
    simply skipped.
    """
    base_real = os.path.realpath(base)
    for name in names:
        src = safe_path(base, name)
        if not os.path.isfile(src):
            continue
        rel = os.path.relpath(src, base_real)
        target = os.path.join(dest, rel)
        os.makedirs(os.path.dirname(target) or dest, exist_ok=True)
        shutil.copy2(src, target)
    return dest


def recipe_name(d: str) -> str:
    """The recipe's filename under `d`, preferring `kernel.RECIPE`
    (`reticuli.toml`) over the legacy name (spec/claim-format.md).
    """
    if os.path.isfile(os.path.join(d, kernel.RECIPE)):
        return kernel.RECIPE
    if os.path.isfile(os.path.join(d, RECIPE)):
        return RECIPE
    raise kernel.ClaimError(f"no recipe found in {d!r}")


def stamp() -> str:
    """UTC time of recording, `YYYY-MM-DDTHH:MM:SSZ` (spec/record.md)."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ledger_add(d: str, entry: dict) -> None:
    """Append one entry to the claim's cost ledger, through the kernel's
    own pinned `ledger` primitive.
    """
    kernel.ledger(d, entry)


def locked_append(path: str, line: str) -> None:
    """Append one line to `path` under an exclusive lock, creating the
    parent directory if needed -- safe for concurrent writers.
    """
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.write(line)
            f.write("\n")
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def trace_append(d: str, entry: dict) -> None:
    """Append one line of exchange-layer provenance residue (component
    detection, pulls, transfers) that the kernel's own ledger does not
    carry. Never read by the kernel itself.
    """
    path = os.path.join(d, STORE, "trace.jsonl")
    locked_append(path, json.dumps(entry, sort_keys=True))
