"""_util: primitives shared by the exchange layer (spec/layers.md).

Sits beside the kernel, like `_kernel` itself, so registry/transfer/attest/
record never need to reach past the kernel's public surface: copying
declared content, hashing bytes, confining a name to a claim directory, and
appending JSON-lines residue (the ledger, and the exchange layer's own
event trace) all live here once instead of once per importer.

`kernel.py` measures and totals a claim's ledger (`kernel.cost`) but never
itself appends to one -- every kernel verb that records a ledger entry
(`kernel.rebuild`) does so through the private `_kernel.run.ledger`. A
caller building a claim's cost history by hand (recording a producer's
declared identity, or a measured spend, before a seal) has no public verb
to call. This module owns that verb (`ledger_add`) and, because every
importer already reaches the kernel through the one `kernel` module object,
attaches it there too -- so `kernel.ledger(...)` and `_util.ledger_add(...)`
are the same function reached two ways, matching how every other kernel
verb is already found on `kernel`.
"""
import datetime
import fcntl
import hashlib
import json
import os
import shutil
import tempfile

from . import kernel

STORE = ".reticuli"
LEDGER = ".reticuli/ledger.jsonl"
RECIPE = "claim.toml"


def hash_bytes(data: bytes) -> str:
    """sha256 hex digest of `data` -- the bytes-boundary primitive for
    content already in memory (a signed statement, a packet), as `_hash_file`
    is for bytes still on disk."""
    return hashlib.sha256(data).hexdigest()


def copy_into(src: str, dst: str) -> None:
    """Copy a file or a directory tree from `src` to `dst`, creating `dst`'s
    parent as needed."""
    if os.path.isdir(src):
        shutil.copytree(src, dst, symlinks=False)
    else:
        parent = os.path.dirname(dst) or "."
        os.makedirs(parent, exist_ok=True)
        shutil.copy2(src, dst)


def safe_path(base: str, name: str) -> str:
    """Resolve `name` to a real path under `base`, refusing an absolute or
    empty name, a `..` component, or any component that is a symlink --
    the same confinement the kernel applies to a claim's own declared
    paths (spec/identity.md), applied here to a tar member's name."""
    if not name:
        raise kernel.ClaimError("path name must not be empty")
    if os.path.isabs(name):
        raise kernel.ClaimError(f"path name must not be absolute: {name!r}")
    parts = name.split("/")
    if any(p in ("", "..") for p in parts):
        raise kernel.ClaimError(f"path name must not escape the claim: {name!r}")

    real_base = os.path.realpath(base)
    walked = real_base
    for part in parts:
        walked = os.path.join(walked, part)
        if os.path.islink(walked):
            raise kernel.ClaimError(f"path name must not pass through a symlink: {name!r}")

    resolved = os.path.realpath(os.path.join(real_base, name))
    if resolved != real_base and not resolved.startswith(real_base + os.sep):
        raise kernel.ClaimError(f"path name escapes the claim: {name!r}")
    return resolved


def read_json(path: str):
    """Parse one JSON document from `path`."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str, obj) -> None:
    """Write JSON atomically: build the bytes off to the side, then rename."""
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, sort_keys=True)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def locked_append(path: str, line: str) -> None:
    """Append one line to a residue file, holding an exclusive lock for the
    write -- so two appenders never interleave a partial line."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        except OSError:
            pass
        try:
            f.write(line if line.endswith("\n") else line + "\n")
            f.flush()
        finally:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass


def ledger_add(d: str, entry: dict) -> None:
    """Append one entry to claim `d`'s cost ledger -- residue, outside the
    root (spec/verification.md)."""
    locked_append(os.path.join(d, LEDGER), json.dumps(entry, sort_keys=True))


def trace_append(d: str, entry: dict) -> None:
    """Append one entry to the exchange layer's own event trace: residue
    about what a registry/transfer/attest operation did, distinct from the
    ledger's production-cost record."""
    locked_append(os.path.join(d, STORE, "trace.jsonl"),
                  json.dumps(dict(entry, when=stamp()), sort_keys=True))


def stamp() -> str:
    """UTC time of recording, `YYYY-MM-DDTHH:MM:SSZ` (spec/record.md)."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def declared_inputs(d: str) -> list:
    """The claim's declared pinned inputs (`[claim] inputs`), read from its
    recipe."""
    parsed = kernel.load_recipe(d)
    return list(parsed.get("claim", {}).get("inputs", []))


def step_output(step: dict) -> str:
    """The path a recipe step pins or produces."""
    return step["output"]


def backfill_components(d: str) -> None:
    """Restore each nested component's own copy of a `from`-sourced output
    from `d`'s own current bytes.

    `kernel.audit`'s composed-claim recursion trusts a declared component's
    directory as a self-sufficient claim -- it never substitutes bytes, the
    way `registry.audit_deep` does -- so after an import (which never lets
    a component's generated bytes travel twice: once at the dependent's own
    path, once nested under it) or a rebuild (which nests only a
    component's criteria), the nested copy needs that byte restored locally
    for the kernel's own naive recursion to find it. `registry.audit_deep`
    never depends on this: it always re-derives from `d`'s current bytes
    directly, so a copy here going stale (a later edit to `d`'s own output)
    changes nothing about what audit_deep sees -- only what the kernel's
    unquestioning recursion does.
    """
    try:
        parsed = kernel.load_recipe(d)
        manifest = kernel.read_manifest(d)
    except kernel.ClaimError:
        return
    components = manifest.get("components") or {}
    for step in parsed.get("step", []):
        if step["kind"] != "produce" or "from" not in step:
            continue
        rel = components.get(step["from"])
        if not rel:
            continue
        comp_dir = os.path.join(d, rel)
        if not os.path.isdir(comp_dir):
            continue
        src = os.path.join(d, step["output"])
        dst = os.path.join(comp_dir, step["output"])
        if os.path.isfile(src) and not os.path.isfile(dst):
            copy_into(src, dst)
    for rel in components.values():
        comp_dir = os.path.join(d, rel)
        if os.path.isdir(comp_dir):
            backfill_components(comp_dir)


def recipe_name(d: str) -> str:
    """The recipe filename actually present under claim directory `d`:
    `kernel.RECIPE`, preferred, else the legacy name (spec/claim-format.md)."""
    if os.path.isfile(os.path.join(d, kernel.RECIPE)):
        return kernel.RECIPE
    return kernel.LEGACY_RECIPE


# The exchange layer's convenience facade: every other kernel verb that
# appends to the ledger is already found on `kernel` (`kernel.rebuild`
# reaches it through a private import); a caller recording cost or a
# producer declaration by hand should reach the same ledger through the
# one module it already imports, rather than a name that exists only here.
if not hasattr(kernel, "ledger"):
    kernel.ledger = ledger_add
