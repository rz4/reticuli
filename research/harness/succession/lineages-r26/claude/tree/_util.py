"""Small helpers the exchange layer shares.

Kept independent of any `reticuli._kernel` private, per `spec/layers.md`:
"no layer imports a kernel private". Each helper here reimplements the
small piece of behavior `registry.py`/`transfer.py`/`attest.py`/`record.py`
need, reaching only the kernel's pinned public surface (`reticuli.kernel`)
for the one vocabulary of refusal (`ClaimError`) and the few constants
whose values matter across the exchange layer.
"""
import hashlib
import json
import os
import shutil
import stat
import tempfile
import time

from reticuli import kernel

STORE = ".reticuli"
LEDGER = ".reticuli/ledger.jsonl"
RECIPE = "claim.toml"


# -- the path boundary --------------------------------------------------------


def safe_path(base: str, name: str) -> str:
    """Resolve `name` to a real path under `base`, or refuse.

    The path boundary of `spec/identity.md`: no absolute path, no empty
    name, no `..` component, and no symlink component anywhere along the
    way -- even one whose target stays inside the claim.
    """
    if not name:
        raise kernel.ClaimError("a claim path must not be empty")
    if os.path.isabs(name):
        raise kernel.ClaimError(f"a claim path must not be absolute: {name!r}")
    parts = name.replace("\\", "/").split("/")
    if any(p in ("", "..") for p in parts) or any(p == "." for p in parts):
        raise kernel.ClaimError(f"a claim path must not escape the claim: {name!r}")

    base_real = os.path.realpath(base)
    walked = base_real
    for part in parts:
        walked = os.path.join(walked, part)
        if os.path.islink(walked):
            raise kernel.ClaimError(f"a claim path must not pass through a symlink: {name!r}")

    resolved = os.path.realpath(os.path.join(base_real, *parts))
    if resolved != base_real and not resolved.startswith(base_real + os.sep):
        raise kernel.ClaimError(f"a claim path must not escape the claim: {name!r}")
    return resolved


# -- the bytes boundary --------------------------------------------------------


def hash_bytes(path: str) -> str:
    """sha256 hex digest of a file's bytes.

    Refuses anything but a regular file with exactly one hard link, per
    the filesystem-aliasing rule of `spec/identity.md`.
    """
    st = os.lstat(path)
    if not stat.S_ISREG(st.st_mode):
        raise kernel.ClaimError(f"not a regular file: {path!r}")
    if st.st_nlink != 1:
        raise kernel.ClaimError(f"refuses a file with more than one hard link: {path!r}")
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# -- reading a recipe's declared inputs ---------------------------------------


def _read_input_manifest(path: str) -> list:
    paths = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            bits = line.split(None, 1)
            paths.append(bits[1] if len(bits) == 2 and len(bits[0]) == 64 else bits[0])
    return paths


def declared_inputs(d: str, parsed: dict) -> list:
    """Every pinned input path a recipe declares.

    Its `[claim] inputs` list, plus any path named by an `inputs_manifest`
    file, in the order the manifest names them.
    """
    claim = parsed.get("claim", {})
    paths = list(claim.get("inputs", []))
    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        paths.append(manifest)
        paths.extend(_read_input_manifest(safe_path(d, manifest)))
    return paths


def step_output(step: dict):
    """A step's declared output path."""
    return step.get("output")


def recipe_filename(d: str) -> str:
    """The recipe's actual on-disk filename, preferring its v2 name."""
    if os.path.isfile(os.path.join(d, kernel.RECIPE)):
        return kernel.RECIPE
    legacy = "claim.toml"
    if os.path.isfile(os.path.join(d, legacy)):
        return legacy
    raise kernel.ClaimError(f"no recipe found in {d!r}")


# -- JSON: reading, and an atomic canonical write -----------------------------


def read_json(path: str):
    """Parse a JSON file; refusals, never a raw crash."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise kernel.ClaimError(f"cannot read {path!r}: {e}") from e


def write_json(path: str, obj) -> None:
    """Write `obj` as canonical JSON, atomically: never a partial file."""
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, sort_keys=True, ensure_ascii=True)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# -- copying -------------------------------------------------------------------


def copy_into(src: str, dst: str) -> None:
    """Copy a directory's contents into `dst`, which must already exist."""
    for entry in os.listdir(src):
        s = os.path.join(src, entry)
        t = os.path.join(dst, entry)
        if os.path.isdir(s) and not os.path.islink(s):
            shutil.copytree(s, t)
        else:
            os.makedirs(os.path.dirname(t) or dst, exist_ok=True)
            shutil.copy2(s, t)


# -- timestamps ------------------------------------------------------------------


def stamp() -> str:
    """UTC time of recording, `YYYY-MM-DDTHH:MM:SSZ`."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# -- append-only logs, locked for the duration of one write -------------------


def locked_append(path: str, line: str) -> None:
    """Append one line to `path`, holding an exclusive OS lock so
    concurrent appenders never interleave their writes."""
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
            f.write(line if line.endswith("\n") else line + "\n")
        finally:
            if fcntl is not None:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def ledger_add(d: str, event: dict) -> None:
    """Append one JSON-lines event to the claim's cost ledger."""
    locked_append(os.path.join(d, LEDGER), json.dumps(event, sort_keys=True))


def trace_append(d: str, entry: dict) -> None:
    """Append one JSON-lines entry to the claim's provenance trace.

    Residue distinct from the cost ledger -- never consulted to decide
    identity or verdicts.
    """
    locked_append(os.path.join(d, STORE, "trace.jsonl"), json.dumps(entry, sort_keys=True))
