"""Shared helpers for the exchange layer (`spec/layers.md`).

Only the public kernel surface (`reticuli.kernel`) is imported here -- never
a kernel private -- so every layer above the kernel shares one boundary with
it, not an ad hoc leak of its internals. `safe_path`/`hash_bytes`/
`read_json`/`write_json`/`copy_into` are the path and bytes primitives every
higher module needs; `declared_inputs`/`step_output` resolve what a claim's
recipe actually names; `stamp` is the record's UTC clock; `ledger_add`/
`locked_append`/`trace_append` are this layer's own bookkeeping, built on
top of the kernel's (never duplicating its ledger format).

Stdlib only.
"""
import datetime
import hashlib
import json
import os
import re
import shutil
import tempfile

from reticuli import kernel

STORE = ".reticuli"
LEDGER = ".reticuli/ledger.jsonl"
RECIPE = "claim.toml"

_HEXLINE = re.compile(r"^[0-9a-f]{64}\s+(\S.*)$")


def safe_path(base: str, name: str) -> str:
    """Resolve `name` as a path inside `base`; refuse any escape."""
    if not name:
        raise kernel.ClaimError("empty path refused")
    if os.path.isabs(name):
        raise kernel.ClaimError(f"absolute path refused: {name!r}")
    parts = name.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise kernel.ClaimError(f"path escapes the claim: {name!r}")

    base_real = os.path.realpath(base)
    cur = base_real
    for part in parts:
        cur = os.path.join(cur, part)
        if os.path.islink(cur):
            raise kernel.ClaimError(f"symlink component refused: {name!r}")

    resolved = os.path.realpath(cur)
    if resolved != base_real and not resolved.startswith(base_real + os.sep):
        raise kernel.ClaimError(f"path escapes the claim: {name!r}")
    return resolved


def recipe_name(d: str) -> str:
    """The on-disk filename of `d`'s recipe, preferring the canonical name."""
    for name in (kernel.RECIPE, RECIPE):
        if os.path.isfile(os.path.join(d, name)):
            return name
    raise kernel.ClaimError(f"no recipe found in {d!r}")


def hash_bytes(data: bytes) -> str:
    """A plain sha256 of `data`."""
    return hashlib.sha256(data).hexdigest()


def read_json(path: str):
    """Parse a JSON file; malformed bytes raise in band."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise kernel.ClaimError(f"cannot read {path!r}: {e}") from e


def write_json(path: str, obj) -> None:
    """Write `obj` as JSON atomically: a temp file, then a rename."""
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, sort_keys=True)
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def copy_into(src_dir: str, dst_dir: str, names) -> None:
    """Copy each declared name from `src_dir` into `dst_dir`, via `safe_path`."""
    for name in names:
        s = safe_path(src_dir, name)
        d = safe_path(dst_dir, name)
        os.makedirs(os.path.dirname(d) or dst_dir, exist_ok=True)
        shutil.copy2(s, d)


def declared_inputs(d: str) -> list:
    """`d`'s pinned input paths, from `inputs` or `inputs_manifest`.

    Mirrors `spec/claim-format.md`'s `inputs_manifest` expansion, using only
    the public kernel surface (`kernel.load_recipe`) to reach the recipe.
    """
    parsed = kernel.load_recipe(d)
    claim = parsed.get("claim", {})
    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        paths = []
        with open(safe_path(d, manifest), "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                m = _HEXLINE.match(line)
                paths.append(m.group(1) if m else line)
        return [manifest] + paths
    return list(claim.get("inputs", []))


def step_output(d: str, step: dict) -> str:
    """The on-disk path of one step's declared output, inside `d`."""
    return safe_path(d, step["output"])


def stamp() -> str:
    """UTC time of recording, `YYYY-MM-DDTHH:MM:SSZ` (`spec/record.md`)."""
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def locked_append(path: str, line: str) -> None:
    """Append one line to `path`, serialized against concurrent writers."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        try:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        except (ImportError, OSError):
            pass
        f.write(line)
        if not line.endswith("\n"):
            f.write("\n")
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except (NameError, OSError):
            pass


def trace_append(d: str, entry: dict) -> None:
    """Append one diagnostic event to `d`'s exchange-layer trace log.

    Distinct from the kernel's own cost ledger (`ledger_add`): this is
    residue the exchange layer keeps about its own operations (registry
    links formed, transfers made), never consumed by the kernel.
    """
    locked_append(os.path.join(d, STORE, "trace.jsonl"),
                  json.dumps(entry, sort_keys=True))


def ledger_add(d: str, entry: dict) -> None:
    """Append one cost event to `d`'s ledger (the kernel's own format)."""
    kernel.ledger(d, entry)
