"""Kernel recipe: read, validate, and expose a claim's recipe.

The recipe (``reticuli.toml``, or the legacy ``claim.toml``) is untrusted
input. ``load_recipe`` parses it and either returns the parsed table or
refuses with a ``ClaimError`` naming the reason -- never a raw traceback.

Public surface (the check pins these names):

* ``recipe_path(d)``            -- the recipe file of claim directory ``d``
* ``load_recipe(d)``            -- parse and validate; returns the TOML table
* ``gates(parsed)``             -- the gate steps, in recipe order
* ``produces(parsed)``          -- the produce steps, in recipe order
* ``generated_outputs(parsed)`` -- outputs whose bytes are regrowable and
                                   outside identity (class ``generated``,
                                   no ``from``)

Internal helpers (``_steps``, ``_inputs``, ``_read_input_manifest``) are
used by the layers above this one. Stdlib only, never the network.

Rules enforced here, from ``spec/claim-format.md`` and ``spec/identity.md``:

* a name is confined to the claim directory (no absolute paths, no ``..``,
  no symlink components) -- delegated to ``core._safe``;
* a name must match a directory entry exactly, case included, so identity
  never depends on a host filesystem's case folding;
* ``format`` absent means 1; a format newer than this kernel is refused in
  words;
* ``inputs_manifest`` is a fixed list, never a pattern; a manifest naming a
  file that is gone is a refusal that names it;
* TOML dates and times, and non-finite floats, cannot enter a canonical
  preimage, so they are refused at load.
"""
import datetime
import math
import os
import re
import stat
import tomllib

from reticuli._kernel import core

CLASSES = frozenset({"generated", "pinned", "validated"})
_HEX64 = re.compile(r"[0-9a-f]{64}")
_TEMPORAL = (datetime.date, datetime.time, datetime.datetime)


# ------------------------------------------------------------ small helpers
def _refuse(msg: str):
    raise core.ClaimError(msg)


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _exact_entry(d: str, rel: str) -> bool:
    """True iff every component of ``rel`` is an exact directory entry.

    Case-sensitive on purpose: ``os.path.exists`` folds case on macOS and
    Windows, which would let ``ok`` resolve to a file named ``OK``.
    """
    cur = os.path.realpath(d)
    for part in rel.split("/"):
        try:
            names = os.listdir(cur)
        except OSError:
            return False
        if part not in names:
            return False
        cur = os.path.join(cur, part)
    return True


def _declared_file(d: str, rel: str, what: str) -> str:
    """Resolve a recipe-declared file name; it must exist exactly and be regular."""
    full = core._safe(d, rel)
    if not _exact_entry(d, rel):
        _refuse(f"{what} names a file that is not in the claim: {rel!r}")
    if not stat.S_ISREG(os.lstat(full).st_mode):
        _refuse(f"{what} is not a regular file (refused): {rel!r}")
    return full


def _refuse_unrepresentable(node, where: str) -> None:
    """Refuse values with no canonical JSON form: temporal values, non-finite floats."""
    if isinstance(node, dict):
        for key, value in node.items():
            _refuse_unrepresentable(value, f"{where}.{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            _refuse_unrepresentable(value, f"{where}[{i}]")
    elif isinstance(node, bool) or isinstance(node, (int, str)):
        return
    elif isinstance(node, float):
        if not math.isfinite(node):
            _refuse(f"non-finite number refused at {where}: {node!r}")
    elif isinstance(node, _TEMPORAL):
        _refuse(f"TOML date/time refused at {where}: it has no canonical form")
    else:
        _refuse(f"unsupported recipe value at {where}: {type(node).__name__}")


# ------------------------------------------------------------ recipe location
def recipe_path(d: str) -> str:
    """The recipe file of claim directory ``d``.

    ``reticuli.toml`` is preferred; ``claim.toml`` is read for claims sealed
    under the old name (the filename is not in the root preimage). Names are
    matched exactly, and the recipe itself may not be a symlink.
    """
    if not os.path.isdir(d):
        _refuse(f"not a claim directory: {d}")
    try:
        names = os.listdir(d)
    except OSError as e:
        _refuse(f"cannot read claim directory {d}: {e}")
    for name in (core.RECIPE, core.LEGACY_RECIPE):
        if name in names:
            path = os.path.join(d, name)
            st = os.lstat(path)
            if stat.S_ISLNK(st.st_mode):
                _refuse(f"recipe is a symlink (refused): {name}")
            if not stat.S_ISREG(st.st_mode):
                _refuse(f"recipe is not a regular file (refused): {name}")
            return path
    _refuse(f"no recipe in {d}: expected {core.RECIPE} or {core.LEGACY_RECIPE}")


# ------------------------------------------------------------ validation
def _validate_claim(d: str, claim) -> None:
    if not isinstance(claim, dict):
        _refuse("recipe has no [claim] table")
    if not isinstance(claim.get("name"), str):
        _refuse("[claim] name is required and must be a string")

    fmt = claim.get("format", 1)
    if isinstance(fmt, bool) or not isinstance(fmt, int) or fmt < 1:
        _refuse("[claim] format must be a positive integer")
    if fmt > core.FORMAT:
        _refuse(f"claim format {fmt} is newer than this kernel understands "
                f"(format {core.FORMAT}); upgrade reticuli to read it")

    if "inputs" in claim:
        inputs = claim["inputs"]
        if not isinstance(inputs, list) or not all(isinstance(p, str) for p in inputs):
            _refuse("[claim] inputs must be a list of path strings")
        for rel in inputs:
            core._safe(d, rel)
    if "inputs_manifest" in claim:
        if not isinstance(claim["inputs_manifest"], str):
            _refuse("[claim] inputs_manifest must be a path string")
        core._safe(d, claim["inputs_manifest"])
    if "environment" in claim:
        if not isinstance(claim["environment"], str):
            _refuse("[claim] environment must be a path string")
        core._safe(d, claim["environment"])
    if "requires" in claim:
        req = claim["requires"]
        if not isinstance(req, list) or not all(isinstance(r, str) for r in req):
            _refuse("[claim] requires must be a list of strings")
    for key in ("gate_timeout", "mutation_floor", "tolerance"):
        if key in claim and (not _is_number(claim[key]) or claim[key] <= 0):
            _refuse(f"[claim] {key} must be a positive number")
    if "envelope" in claim:
        env = claim["envelope"]
        if not isinstance(env, dict) or not env:
            _refuse("[claim] envelope must be a non-empty table")
        for unit, ceiling in env.items():
            if unit not in core.COST_UNITS:
                _refuse(f"[claim] envelope names an unknown unit: {unit!r}")
            if not _is_number(ceiling) or ceiling <= 0:
                _refuse(f"[claim] envelope ceiling for {unit!r} must be a positive number")


def _validate_steps(d: str, steps) -> None:
    if not isinstance(steps, list) or not all(isinstance(s, dict) for s in steps):
        _refuse("[[step]] must be an array of tables")
    seen = set()
    for i, step in enumerate(steps, 1):
        where = f"step {i}"
        kind = step.get("kind")
        if not isinstance(kind, str) or kind not in core.KINDS:
            _refuse(f"{where}: kind must be one of produce, gate (got {kind!r})")
        output = step.get("output")
        if not isinstance(output, str):
            _refuse(f"{where}: output is required and must be a string")
        core._safe(d, output)
        if output in seen:
            _refuse(f"{where}: output {output!r} is named by more than one step")
        seen.add(output)
        if "class" in step:
            cls = step["class"]
            if not isinstance(cls, str) or cls not in CLASSES:
                _refuse(f"{where}: class must be one of generated, pinned, validated")
        if kind == "gate":
            run = step.get("run")
            if not isinstance(run, str) or run == "":
                _refuse(f"{where}: a gate needs a non-empty run command")
        for key in ("guidance", "request"):
            if key in step and not isinstance(step[key], str):
                _refuse(f"{where}: {key} must be a string")
        if "from" in step and (not isinstance(step["from"], str) or step["from"] == ""):
            _refuse(f"{where}: from must be a non-empty string")


# ------------------------------------------------------------ public reads
def load_recipe(d: str) -> dict:
    """Parse and validate the recipe of claim directory ``d``.

    Returns the parsed TOML table. Every malformed or hostile input is a
    ``ClaimError`` with a reason.
    """
    path = recipe_path(d)
    try:
        with open(path, "rb") as f:
            raw = f.read()
        text = raw.decode("utf-8")
    except (OSError, UnicodeDecodeError) as e:
        _refuse(f"recipe is unreadable: {e}")
    try:
        parsed = tomllib.loads(text)
    except (tomllib.TOMLDecodeError, ValueError, TypeError, RecursionError) as e:
        _refuse(f"recipe is not valid TOML: {e}")
    _refuse_unrepresentable(parsed, "recipe")
    _validate_claim(d, parsed.get("claim"))
    _validate_steps(d, parsed.get("step", []))
    return parsed


def _steps(parsed: dict) -> list:
    """The step tables of a parsed recipe, in file order."""
    return list(parsed.get("step", []))


def _class(step: dict) -> str:
    if "class" in step:
        return step["class"]
    return "generated" if step["kind"] == "produce" else "pinned"


def gates(parsed: dict) -> list:
    """The gate steps, in recipe order."""
    return [s for s in _steps(parsed) if s.get("kind") == "gate"]


def produces(parsed: dict) -> list:
    """The produce steps, in recipe order."""
    return [s for s in _steps(parsed) if s.get("kind") == "produce"]


def generated_outputs(parsed: dict) -> list:
    """Outputs of produce steps whose bytes are regrowable.

    Class ``generated`` and not declared ``from`` a component: those bytes
    are outside the root and outside the build digest.
    """
    return [s["output"] for s in produces(parsed)
            if _class(s) == "generated" and "from" not in s]


def _read_input_manifest(d: str, rel: str) -> list:
    """Read an ``inputs_manifest`` file into the list of pinned input paths.

    One entry per line, either ``<sha256>  <path>`` or a bare ``<path>``;
    blank lines and ``#`` comments are ignored. A stated digest must match
    the file's bytes. The manifest is a fixed list: a named file that is
    gone is a refusal that names it.
    """
    full = _declared_file(d, rel, "inputs manifest")
    try:
        with open(full, "rb") as f:
            text = f.read().decode("utf-8")
    except (OSError, UnicodeDecodeError) as e:
        _refuse(f"inputs manifest {rel!r} is unreadable: {e}")

    entries = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        digest = None
        head = line.split(None, 1)
        if len(head) == 2 and _HEX64.fullmatch(head[0]):
            digest, path = head[0], head[1].strip()
        else:
            path = line
        entries.append((path, digest))

    paths = []
    for path, digest in entries:
        target = _declared_file(d, path, f"inputs manifest {rel!r}")
        if digest is not None and core._hash_file(target) != digest:
            _refuse(f"inputs manifest {rel!r} states a digest for {path!r} "
                    f"that the file's bytes do not match")
        paths.append(path)
    return paths


def _inputs(d: str, parsed: dict) -> list:
    """Every pinned input of the claim: inline ``inputs`` then the manifest.

    Duplicates collapse, keeping first occurrence. Each must exist exactly.
    """
    claim = parsed.get("claim", {})
    names = []
    for rel in claim.get("inputs", []):
        _declared_file(d, rel, "input")
        names.append(rel)
    if "inputs_manifest" in claim:
        names.extend(_read_input_manifest(d, claim["inputs_manifest"]))
    seen, out = set(), []
    for name in names:
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out
