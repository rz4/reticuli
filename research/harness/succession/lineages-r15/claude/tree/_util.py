"""Shared helpers for the layers above the kernel (`spec/layers.md`).

`_util.py` sits beside the kernel: small helpers every exchange-layer module
needs (safe paths, JSON I/O, the declared-content listing, the ledger
append). No layer above the kernel imports a kernel private -- everything
here is built from the kernel's own public surface (`reticuli.kernel`) plus
the standard library, so a layer that needs one of these primitives reaches
it from here rather than reaching past the kernel's public boundary.

Stdlib only.
"""
import hashlib
import json
import os
import shutil
import tempfile
import time

from reticuli import kernel

STORE = ".reticuli"
LEDGER = ".reticuli/ledger.jsonl"
RECIPE = "claim.toml"

_ATTEST_DIR = ".reticuli/attest"


def safe_path(base: str, name: str) -> str:
    """Resolve `name` as a path inside `base`, or refuse (`spec/identity.md`'s
    path-confinement rules: no absolute path, no `..`, no symlink component).
    """
    if not name:
        raise kernel.ClaimError(f"empty path is refused: {name!r}")
    if os.path.isabs(name):
        raise kernel.ClaimError(f"absolute path is refused: {name!r}")
    parts = name.split(os.sep)
    if os.altsep:
        parts = [p for piece in parts for p in piece.split(os.altsep)]
    for part in parts:
        if part in ("", ".."):
            raise kernel.ClaimError(f"path escapes the claim: {name!r}")

    root = os.path.realpath(base)
    resolved = root
    for part in parts:
        candidate = os.path.join(resolved, part)
        if os.path.islink(candidate):
            raise kernel.ClaimError(f"path crosses a symlink: {name!r}")
        resolved = candidate

    resolved = os.path.realpath(resolved)
    if resolved != root and not resolved.startswith(root + os.sep):
        raise kernel.ClaimError(f"path escapes the claim: {name!r}")
    return resolved


def hash_bytes(data: bytes) -> str:
    """The bytes boundary: a plain sha256 hex digest of `data`."""
    return hashlib.sha256(data).hexdigest()


def copy_into(base: str, dest: str, name: str) -> str:
    """Copy the claim-relative entry `name` from `base` into `dest`."""
    src = safe_path(base, name)
    target = os.path.join(dest, name)
    os.makedirs(os.path.dirname(target) or dest, exist_ok=True)
    if os.path.isdir(src):
        shutil.copytree(src, target, dirs_exist_ok=True)
    else:
        shutil.copy2(src, target)
    return target


def read_json(path: str):
    """Read and parse one JSON file, or refuse with a reason."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise kernel.ClaimError(f"cannot read json {path!r}: {e}") from e


def write_json(path: str, obj) -> None:
    """Write `obj` as JSON atomically: never leave a half-written file."""
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, sort_keys=True)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def stamp() -> str:
    """UTC time of recording, `YYYY-MM-DDTHH:MM:SSZ` (`spec/record.md`)."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def step_output(doc: dict, path: str):
    """The step (if any) in recipe `doc` whose declared output is `path`."""
    for step in (doc.get("step") or []):
        if step.get("output") == path:
            return step
    return None


def locked_append(path: str, line: str) -> None:
    """Append one line to `path`, locked against a concurrent writer."""
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        try:
            import fcntl
        except ImportError:
            fcntl = None
        if fcntl is not None:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.write(line)
            if not line.endswith("\n"):
                f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        finally:
            if fcntl is not None:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def trace_append(path: str, entry: dict) -> None:
    """Append one JSON-encoded entry as a line to the trace file at `path`."""
    locked_append(path, json.dumps(entry, sort_keys=True))


def ledger_add(d: str, entry: dict) -> None:
    """Append one entry to claim `d`'s cost ledger, timestamped if not already."""
    record = dict(entry)
    record.setdefault("when", stamp())
    trace_append(safe_path(d, LEDGER), record)


def _read_input_manifest(path: str) -> list:
    paths = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            head, _, rest = line.partition(" ")
            if len(head) == 64 and rest.strip() and all(c in "0123456789abcdef" for c in head):
                paths.append(rest.strip())
            else:
                paths.append(line)
    return paths


def declared_inputs(d: str, doc: dict) -> list:
    """Every pinned input path `doc` declares: the inline list, the
    `inputs_manifest` expansion (itself a pinned input), and the
    `environment` file, if any (`spec/claim-format.md`).
    """
    claim = doc.get("claim", {}) if isinstance(doc, dict) else {}
    inputs = list(claim.get("inputs", []))
    manifest_name = claim.get("inputs_manifest")
    if manifest_name:
        inputs.append(manifest_name)
        manifest_path = safe_path(d, manifest_name)
        if os.path.isfile(manifest_path):
            inputs.extend(_read_input_manifest(manifest_path))
    env_file = claim.get("environment")
    if env_file:
        inputs.append(env_file)

    seen = set()
    out = []
    for p in inputs:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def claim_files(doc: dict, d: str, include_generated: bool) -> list:
    """The claim's declared content, present on disk, as paths relative to
    `d`: the recipe file, every pinned input, every step output (generated
    ones only when `include_generated`), the manifest, and any attestation
    residue. The declared set only -- never a tree walk -- so undeclared
    bytes sitting in the claim's own directory never travel.
    """
    rel = set()
    if os.path.isfile(os.path.join(d, kernel.RECIPE)):
        rel.add(kernel.RECIPE)
    elif os.path.isfile(os.path.join(d, kernel.LEGACY_RECIPE)):
        rel.add(kernel.LEGACY_RECIPE)

    for p in declared_inputs(d, doc):
        if os.path.isfile(os.path.join(d, p)):
            rel.add(p)

    for step in (doc.get("step") or []):
        output = step.get("output")
        if not output:
            continue
        cls = step.get("class")
        generated = step.get("kind") == "produce" and \
            (cls if cls is not None else "generated") in ("generated", "free")
        if generated and not include_generated:
            continue
        if os.path.isfile(os.path.join(d, output)):
            rel.add(output)

    if os.path.isfile(os.path.join(d, kernel.MANIFEST)):
        rel.add(kernel.MANIFEST)

    attest_dir = os.path.join(d, _ATTEST_DIR)
    if os.path.isdir(attest_dir):
        for base, _dirs, files in os.walk(attest_dir):
            for fn in files:
                full = os.path.join(base, fn)
                rel.add(os.path.relpath(full, d))

    return sorted(rel)
