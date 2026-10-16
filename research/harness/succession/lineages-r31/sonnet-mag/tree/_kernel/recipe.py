"""Kernel recipe: read an untrusted recipe, expose its steps, refuse in band."""
import datetime
import os
import re

from . import core
from .core import ClaimError

try:
    import tomllib as _toml
except ImportError:  # pragma: no cover - older interpreters
    _toml = None

_CLASSES = ("generated", "pinned", "validated")
_HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")


def recipe_path(d: str) -> str:
    """Path of the recipe in claim dir `d`: reticuli.toml, else claim.toml."""
    if not isinstance(d, (str, os.PathLike)):
        raise ClaimError(f"bad claim directory: {d!r}")
    d = os.fspath(d)
    for name in (core.RECIPE, core.LEGACY_RECIPE):
        p = os.path.join(d, name)
        if os.path.lexists(p):
            return core._safe(d, name)
    raise ClaimError(f"no recipe ({core.RECIPE} or {core.LEGACY_RECIPE}) in {d!r}")


def _refuse_times(value, where="recipe"):
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        raise ClaimError(f"TOML date/time values are refused ({where})")
    if isinstance(value, dict):
        for k, v in value.items():
            _refuse_times(v, f"{where}.{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            _refuse_times(v, f"{where}[{i}]")


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _validate(parsed: dict) -> None:
    claim = parsed.get("claim")
    if not isinstance(claim, dict):
        raise ClaimError("recipe needs a [claim] table")
    name = claim.get("name")
    if not isinstance(name, str) or not name:
        raise ClaimError("[claim] name is required and must be a string")
    if "format" in claim:
        fmt = claim["format"]
        if not _is_int(fmt) or fmt < 1:
            raise ClaimError("[claim] format must be a positive integer")
        if fmt > core.FORMAT:
            raise ClaimError(
                f"claim format {fmt} is newer than this kernel understands "
                f"(format {core.FORMAT}); upgrade reticuli to read it")
    if "inputs" in claim:
        ins = claim["inputs"]
        if not isinstance(ins, list) or not all(isinstance(x, str) for x in ins):
            raise ClaimError("[claim] inputs must be a list of strings")
    for key in ("inputs_manifest", "environment"):
        if key in claim and (not isinstance(claim[key], str) or not claim[key]):
            raise ClaimError(f"[claim] {key} must be a string")
    if "requires" in claim:
        req = claim["requires"]
        if not isinstance(req, list) or not all(isinstance(x, str) for x in req):
            raise ClaimError("[claim] requires must be a list of strings")
    if "gate_timeout" in claim:
        v = claim["gate_timeout"]
        if not _is_num(v) or not v > 0:
            raise ClaimError("[claim] gate_timeout must be a positive number")
    if "mutation_floor" in claim:
        v = claim["mutation_floor"]
        if not _is_num(v) or v < 0:
            raise ClaimError("[claim] mutation_floor must be a non-negative number")
    if "envelope" in claim:
        env = claim["envelope"]
        if not isinstance(env, dict):
            raise ClaimError("[claim] envelope must be a table")
        for unit, v in env.items():
            if unit not in core.COST_UNITS:
                raise ClaimError(f"[claim] envelope: unknown unit {unit!r}")
            if not _is_num(v) or not v > 0:
                raise ClaimError(
                    f"[claim] envelope: {unit} must be a positive number")

    steps = parsed.get("step", [])
    if not isinstance(steps, list):
        raise ClaimError("[[step]] must be an array of tables")
    for i, s in enumerate(steps):
        if not isinstance(s, dict):
            raise ClaimError(f"step {i} must be a table")
        kind = s.get("kind")
        if not isinstance(kind, str) or kind not in core.KINDS:
            raise ClaimError(f"step {i}: kind must be one of "
                             f"{sorted(core.KINDS)}, got {kind!r}")
        out = s.get("output")
        if not isinstance(out, str) or not out:
            raise ClaimError(f"step {i}: output is required and must be a string")
        if kind == "gate":
            run = s.get("run")
            if not isinstance(run, str) or not run.strip():
                raise ClaimError(f"step {i}: a gate needs a run command")
        elif "run" in s and not isinstance(s["run"], str):
            raise ClaimError(f"step {i}: run must be a string")
        if "class" in s and s["class"] not in _CLASSES:
            raise ClaimError(f"step {i}: class must be one of {list(_CLASSES)}, "
                             f"got {s['class']!r}")
        for key in ("guidance", "request", "from"):
            if key in s and not isinstance(s[key], str):
                raise ClaimError(f"step {i}: {key} must be a string")


def load_recipe(d: str) -> dict:
    """Parse and validate the recipe of claim dir `d`; refuse, never crash."""
    path = recipe_path(d)
    try:
        with open(path, "rb") as f:
            raw = f.read()
        text = raw.decode("utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise ClaimError(f"cannot read recipe: {e}")
    if _toml is None:
        raise ClaimError("no TOML parser available on this interpreter")
    try:
        parsed = _toml.loads(text)
    except (_toml.TOMLDecodeError, ValueError, TypeError, RecursionError) as e:
        raise ClaimError(f"malformed recipe: {e}")
    _refuse_times(parsed)
    _validate(parsed)
    return parsed


def _steps(recipe: dict) -> list:
    """The steps in file order."""
    return list(recipe.get("step", []) or [])


def gates(recipe: dict) -> list:
    return [s for s in _steps(recipe) if s.get("kind") == "gate"]


def produces(recipe: dict) -> list:
    return [s for s in _steps(recipe) if s.get("kind") == "produce"]


def _class(step: dict) -> str:
    default = "generated" if step.get("kind") == "produce" else "pinned"
    return step.get("class", default)


def generated_outputs(recipe: dict) -> list:
    """Outputs of generated produce steps that are not taken `from` a component."""
    return [s["output"] for s in produces(recipe)
            if _class(s) == "generated" and "from" not in s]


def _read_input_manifest(d: str, name: str) -> list:
    """Paths listed in an inputs manifest: one per line, optional sha256 prefix."""
    path = core._safe(d, name)
    try:
        with open(path, "rb") as f:
            text = f.read().decode("utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise ClaimError(f"cannot read inputs manifest {name!r}: {e}")
    paths = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) == 2 and _HEX64.match(parts[0]):
            line = parts[1].strip()
        if line:
            paths.append(line)
    return paths


def _inputs(d: str, recipe: dict) -> list:
    """Every pinned input path: declared, manifest (and its entries), environment."""
    claim = recipe.get("claim", {})
    out = []

    def add(p):
        if p not in out:
            out.append(p)

    for p in claim.get("inputs", []) or []:
        add(p)
    man = claim.get("inputs_manifest")
    if man:
        add(man)
        for p in _read_input_manifest(d, man):
            add(p)
    env = claim.get("environment")
    if env:
        add(env)
    return out
