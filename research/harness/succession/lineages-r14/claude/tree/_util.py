"""Small helpers shared by the exchange layer (spec/layers.md).

Deliberately independent of the kernel's private modules
(`reticuli._kernel.*`): the layers above the kernel consume only
`reticuli.kernel`'s pinned public surface, and this module exists so a
sibling layer never has to reach for a kernel private either -- each helper
here is a plain reimplementation of the same small primitive (path
confinement, file hashing, declared inputs, JSON I/O) against that public
surface. Stdlib only, never the network.
"""
import json
import hashlib
import os
import shutil
import tempfile
import time
import tomllib

from reticuli import kernel

STORE = ".reticuli"
LEDGER = ".reticuli/ledger.jsonl"
RECIPE = "claim.toml"

_RECIPE_NAMES = (kernel.RECIPE, RECIPE)
_HEXDIGITS = frozenset("0123456789abcdef")


# -- the path boundary -------------------------------------------------

def safe_path(base: str, name: str) -> str:
    """Resolve `name` inside `base`; refuse anything that escapes it."""
    if not name or os.path.isabs(name):
        raise kernel.ClaimError(f"refused path: {name!r}")
    norm = os.path.normpath(name)
    if norm in (os.curdir, os.pardir):
        raise kernel.ClaimError(f"refused path: {name!r}")
    parts = norm.split(os.sep)
    if any(part in (os.pardir, "") for part in parts):
        raise kernel.ClaimError(f"refused path: {name!r} escapes its base")

    base_real = os.path.realpath(base)
    resolved = os.path.join(base_real, norm)
    if resolved != base_real and not resolved.startswith(base_real + os.sep):
        raise kernel.ClaimError(f"refused path: {name!r} escapes its base")
    return resolved


# -- the bytes boundary ----------------------------------------------------

def hash_bytes(path: str) -> str:
    """A plain sha256 of a file's bytes."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# -- JSON I/O ---------------------------------------------------------------

def read_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str, obj) -> None:
    """Write `obj` to `path` as JSON, atomically (write-then-rename)."""
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def stamp() -> str:
    """UTC time, `YYYY-MM-DDTHH:MM:SSZ` (spec/record.md)."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# -- declared recipe content, read independently of the kernel's parser ----

def _recipe_file(d: str) -> str:
    for name in _RECIPE_NAMES:
        if os.path.isfile(os.path.join(d, name)):
            return name
    raise kernel.ClaimError(f"no recipe found in {d!r}")


def _recipe_doc(d: str) -> dict:
    path = os.path.join(d, _recipe_file(d))
    with open(path, "rb") as f:
        raw = f.read()
    return tomllib.loads(raw.decode("utf-8"))


def _read_inputs_manifest(d: str, manifest_name: str) -> list:
    path = safe_path(d, manifest_name)
    paths = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f.read().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            head, _, rest = line.partition(" ")
            if len(head) == 64 and rest.strip() and all(c in _HEXDIGITS for c in head.lower()):
                paths.append(rest.strip())
            else:
                paths.append(line)
    return paths


def declared_inputs(d: str) -> list:
    """Every pinned input path `d`'s recipe declares: `inputs`, an expanded
    `inputs_manifest`, and a declared `environment` file."""
    doc = _recipe_doc(d)
    claim = doc.get("claim", {}) if isinstance(doc, dict) else {}
    result = list(claim.get("inputs") or [])

    manifest = claim.get("inputs_manifest")
    if manifest:
        result.append(manifest)
        result.extend(_read_inputs_manifest(d, manifest))

    env_file = claim.get("environment")
    if env_file:
        result.append(env_file)

    return result


def step_output(step: dict):
    """A step's `(output, class)`, class defaulting by kind (`spec/claim-format.md`)."""
    output = step.get("output")
    cls = step.get("class")
    if cls is None:
        cls = "generated" if step.get("kind") == "produce" else "pinned"
    return output, cls


# -- copying declared content -----------------------------------------------

def copy_into(src: str, dst: str, names) -> None:
    """Copy each named file from `src` into `dst`, creating directories;
    silently skips a name that is not present in `src`."""
    for name in names:
        source = safe_path(src, name)
        if not os.path.isfile(source):
            continue
        target = safe_path(dst, name)
        os.makedirs(os.path.dirname(target) or dst, exist_ok=True)
        shutil.copy2(source, target)


# -- host residue: a cost ledger and a generic trace, both outside identity -

def ledger_add(d: str, entry: dict) -> None:
    """Append one cost-ledger entry (spec/verification.md)."""
    path = os.path.join(d, LEDGER)
    os.makedirs(os.path.dirname(path) or d, exist_ok=True)
    record = dict(entry)
    record.setdefault("when", stamp())
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True))
        f.write("\n")


def trace_append(d: str, entry: dict) -> None:
    """Append one line to a claim's generic audit trail (host bookkeeping,
    distinct from the cost ledger, never identity)."""
    path = os.path.join(d, STORE, "trace.jsonl")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    record = dict(entry)
    record.setdefault("when", stamp())
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True))
        f.write("\n")


# -- the kernel's `from` lookup: a literal sibling file, not a component ---
#
# `_materialize` (the kernel's own, pinned room-builder) reads a produce
# step's `from` value as the literal name of a file already sitting beside
# the recipe -- not a component name -- and copies it to the step's
# `output` verbatim; if that file is absent it silently leaves `output`
# unmaterialized (never falling back to `output`'s own current bytes, even
# when the caller asked for every generated output to be carried in). A
# composed claim whose `from` NAMES a component therefore needs that exact
# file to exist, or a raw `kernel.audit`/`kernel.rebuild` on it can never
# place the output at all. Two produce steps are free to declare the same
# `from` value (one component can supply several files), which the kernel
# resolves to ONE shared file -- so a flat copy cannot serve both outputs.
# The alias below is instead a small dispatcher: copied verbatim to
# whichever output name the kernel renames it to, it reads its OWN
# destination filename and re-executes that output's real, frozen source --
# the one piece of information the shared lookup key cannot carry.

def _grouped_from_steps(parsed: dict) -> dict:
    groups = {}
    for step in parsed.get("step", []):
        if step.get("kind") != "produce":
            continue
        frm = step.get("from")
        output = step.get("output")
        if frm and isinstance(output, str):
            groups.setdefault(frm, []).append(output)
    return groups


def _alias_bootstrap(payload: dict) -> str:
    return (
        "import json as _json, os as _os\n"
        f"_PAYLOAD = _json.loads({json.dumps(payload)!r})\n"
        "_key = _os.path.splitext(_os.path.basename(__file__))[0]\n"
        "exec(compile(_PAYLOAD[_key], __file__, 'exec'), globals())\n"
    )


def _sync_aliases(d: str) -> None:
    """Freeze, under each `from` value `d`'s recipe declares, a dispatcher
    carrying every sharing output's CURRENT bytes -- so a later raw
    `kernel.audit`/`kernel.rebuild` on `d` can materialize them at all.
    Frozen at the moment this runs: an edit to `output` afterward (a
    sabotage, a forgery) never reaches it, exactly as a `from` step's
    bytes are never something a producer earns."""
    try:
        parsed = kernel.load_recipe(d)
    except kernel.ClaimError:
        return
    for frm, outputs in _grouped_from_steps(parsed).items():
        payload = {}
        for output in outputs:
            full = os.path.join(d, output)
            if not os.path.isfile(full):
                continue
            key = os.path.splitext(os.path.basename(output))[0]
            try:
                with open(full, "r", encoding="utf-8") as f:
                    payload[key] = f.read()
            except UnicodeDecodeError:
                continue
        if payload:
            with open(os.path.join(d, frm), "w", encoding="utf-8") as f:
                f.write(_alias_bootstrap(payload))


def locked_append(path: str, line: str) -> None:
    """Append one line to `path`, exclusive where `fcntl` is available."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    text = line if line.endswith("\n") else line + "\n"
    try:
        import fcntl
    except ImportError:
        with open(path, "a", encoding="utf-8") as f:
            f.write(text)
        return
    with open(path, "a", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.write(text)
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
