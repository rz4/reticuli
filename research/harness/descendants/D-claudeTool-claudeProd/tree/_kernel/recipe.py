"""Kernel recipe: parsing an untrusted claim file.

A claim's own recipe is untrusted input, so every refusal here is a
`ClaimError` with a reason rather than a raw parse crash. Both filenames are
read -- `reticuli.toml` is canonical, `claim.toml` stays readable forever --
and the filename is outside the root preimage, so twins share one root.
"""
import os
import re
import tomllib

from .core import (CLASSES, ClaimError, FORMAT, GUIDANCE_KEYS, KINDS,
                   LEGACY_RECIPE, RECIPE, COST_UNITS, _finite, _is_number,
                   _safe)

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def recipe_path(claim: str) -> str:
    """The claim's recipe file, canonical name preferred."""
    for name in (RECIPE, LEGACY_RECIPE):
        candidate = os.path.join(claim, name)
        if os.path.isfile(candidate):
            return candidate
    raise ClaimError(f"no recipe ({RECIPE} or {LEGACY_RECIPE}) in {claim}")


def _steps(parsed: dict) -> list:
    steps = parsed.get("step") or []
    if not isinstance(steps, list):
        raise ClaimError("[[step]] must be a list of tables")
    return [s for s in steps if isinstance(s, dict)]


def gates(parsed: dict) -> list:
    return [s for s in _steps(parsed) if s.get("kind") == "gate"]


def produces(parsed: dict) -> list:
    return [s for s in _steps(parsed) if s.get("kind") == "produce"]


def generated_outputs(parsed: dict) -> list:
    return [s["output"] for s in produces(parsed)
            if s.get("class", "generated") == "generated" and s.get("output")]


def _claim_format(parsed: dict) -> int:
    declared = (parsed.get("claim") or {}).get("format")
    if declared is None:
        return 1
    return int(declared)


def _read_input_manifest(claim: str, name: str) -> list:
    """The format-2 manifest: one entry per line, optionally `<sha>  <path>`."""
    path = _safe(claim, name)
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except OSError as exc:
        raise ClaimError(f"cannot read inputs_manifest {name!r}: {exc}") from exc
    listed = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        listed.append(fields[-1] if len(fields) > 1 else fields[0])
    return listed


def _inputs(parsed: dict, claim: str) -> list:
    """The pinned-input set: wider than `[claim] inputs`.

    The union of the declared list, the `environment` file, and -- at format 2
    and above -- the `inputs_manifest` plus every path it lists.
    """
    table = parsed.get("claim") or {}
    declared = table.get("inputs") or []
    if not isinstance(declared, list):
        raise ClaimError("[claim] inputs must be a list of paths")
    paths = [p for p in declared]
    environment = table.get("environment")
    if environment:
        paths.append(environment)
    manifest = table.get("inputs_manifest")
    if manifest and _claim_format(parsed) >= 2:
        paths.append(manifest)
        paths.extend(_read_input_manifest(claim, manifest))
    seen, ordered = set(), []
    for path in paths:
        if path not in seen:
            seen.add(path)
            ordered.append(path)
    return ordered


def _bad_envelope(table) -> str | None:
    if not isinstance(table, dict) or not table:
        return "[claim] envelope must be a non-empty table of unit ceilings"
    for unit, ceiling in table.items():
        if unit not in COST_UNITS:
            return f"[claim] envelope names an unknown unit {unit!r}"
        if not _finite(ceiling) or float(ceiling) <= 0:
            return (f"[claim] envelope {unit} must be a finite positive "
                    f"number, not {ceiling!r}")
    return None


def _validate_obligations(table: dict) -> None:
    if "envelope" in table:
        why = _bad_envelope(table["envelope"])
        if why:
            raise ClaimError(why)
    if "tolerance" in table:
        value = table["tolerance"]
        if not _finite(value) or float(value) < 1:
            raise ClaimError(
                "[claim] tolerance must be a finite number >= 1, "
                f"not {value!r}")
    if "mutation_floor" in table:
        value = table["mutation_floor"]
        if not _finite(value) or float(value) < 0:
            raise ClaimError(
                "[claim] mutation_floor must be a finite number >= 0, "
                f"not {value!r}")


def _validate_format5(parsed: dict, fmt: int) -> None:
    """Format 5 admits new vocabulary; below it, saying the words refuses."""
    table = parsed.get("claim") or {}
    steps = _steps(parsed)
    carried = [s for s in steps if s.get("class") == "carried"]
    if fmt < 5:
        if carried:
            raise ClaimError(
                "class = \"carried\" is format 5 vocabulary; this recipe "
                f"declares format {fmt}. Declare format = 5 to use it")
        if "constrains" in table:
            raise ClaimError(
                "[claim] constrains is format 5 vocabulary; this recipe "
                f"declares format {fmt}. Declare format = 5 to use it")
        if "assembles" in table:
            raise ClaimError(
                "[claim] assembles is format 5 vocabulary; this recipe "
                f"declares format {fmt}. Declare format = 5 to use it")
        return
    for step in steps:
        klass = step.get("class")
        if klass is not None and klass not in CLASSES:
            raise ClaimError(
                f"unknown step class {klass!r}: at format 5 the class "
                f"vocabulary is closed ({sorted(CLASSES)})")
        if klass == "carried" and step.get("kind") != "produce":
            raise ClaimError(
                "only a produce step may be carried: a gate's verdict is "
                "earned, never copied")
    if "assembles" in table:
        members = table["assembles"]
        if not isinstance(members, list):
            raise ClaimError("[claim] assembles must be a list of <name>@<root>")
        for entry in members:
            if not isinstance(entry, str) or "@" not in entry:
                raise ClaimError(
                    f"[claim] assembles entry {entry!r} is not <name>@<root>")
            name, _, root = entry.rpartition("@")
            if not name or not _HEX64.match(root or ""):
                raise ClaimError(
                    f"[claim] assembles member {entry!r} needs a 64-hex root")
    if "constrains" in table:
        declared = table["constrains"]
        if not isinstance(declared, dict):
            raise ClaimError("[claim] constrains must be a table")
        inputs = table.get("inputs") or []
        for key, targets in declared.items():
            if key not in inputs:
                raise ClaimError(
                    f"[claim] constrains key {key!r} is not a declared input")
            if not isinstance(targets, list) or not all(
                    isinstance(t, str) for t in targets):
                raise ClaimError(
                    f"[claim] constrains {key!r} must name a list of outputs")


def _validate_gate_order(parsed: dict, fmt: int) -> None:
    """At format 4 and 5 the preimage sorts, so an ordering dependency between
    gates would give one root two acceptance predicates. Refuse the shape an
    author writes by hand; format 6 is the guarantee, this is the net."""
    if fmt not in (4, 5):
        return
    earlier: list = []
    for gate in gates(parsed):
        command = gate.get("run") or ""
        tokens = set(re.split(r"[^\w./+-]+", command))
        for previous in earlier:
            if previous and previous in tokens:
                raise ClaimError(
                    f"[[step]] gate {gate.get('output')!r} reads "
                    f"{previous!r}, which an earlier gate writes, but format "
                    f"{fmt} sorts the step list into the root -- so this "
                    f"recipe and its reverse would share one root and "
                    f"disagree about acceptance. Declare format = 6, which "
                    f"commits step order, or make the gates independent")
        if gate.get("output"):
            earlier.append(gate["output"])


def load_recipe(claim: str) -> dict:
    """Parse and validate a claim's recipe. Refusals, not crashes."""
    path = recipe_path(claim)
    try:
        with open(path, "rb") as handle:
            parsed = tomllib.load(handle)
    except (tomllib.TOMLDecodeError, UnicodeDecodeError, OSError) as exc:
        raise ClaimError(f"damaged recipe at {path}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ClaimError(f"recipe at {path} is not a table")
    table = parsed.get("claim")
    if not isinstance(table, dict):
        raise ClaimError(f"recipe at {path} has no [claim] table")
    name = table.get("name")
    if not isinstance(name, str) or not name:
        raise ClaimError("[claim] name is required and must be a string")

    declared = table.get("format")
    if declared is not None:
        if isinstance(declared, bool) or not isinstance(declared, int) \
                or declared < 1:
            raise ClaimError(
                f"[claim] format must be a positive integer, not {declared!r}")
        if declared > FORMAT:
            raise ClaimError(
                f"claim format {declared} is newer than this kernel "
                f"understands (format {FORMAT}); upgrade reticuli to read it")
    fmt = _claim_format(parsed)

    for step in _steps(parsed):
        kind = step.get("kind")
        if kind not in KINDS:
            raise ClaimError(
                f"unknown step kind {kind!r}: a step is "
                f"{' or '.join(sorted(KINDS))}")
        output = step.get("output")
        if not isinstance(output, str) or not output:
            raise ClaimError(f"a {kind} step needs an output")
        if kind == "gate" and not isinstance(step.get("run"), str):
            raise ClaimError(f"gate {output!r} needs a run command")
        for key in GUIDANCE_KEYS:
            if key in step and not isinstance(step[key], str):
                raise ClaimError(f"step {output!r}: {key} must be a string")

    requires = table.get("requires")
    if requires is not None and not isinstance(requires, list):
        raise ClaimError("[claim] requires must be a list of names")
    timeout = table.get("gate_timeout")
    if timeout is not None and (not _finite(timeout) or float(timeout) <= 0):
        raise ClaimError("[claim] gate_timeout must be a finite positive number")

    _validate_obligations(table)
    _validate_format5(parsed, fmt)
    _validate_gate_order(parsed, fmt)
    _reject_temporal(parsed)
    return parsed


def _reject_temporal(value) -> None:
    """TOML dates and times have no canonical JSON form, so they are refused
    at sealing rather than entering a preimage under an invented spelling."""
    import datetime as _dt
    if isinstance(value, (_dt.datetime, _dt.date, _dt.time)):
        raise ClaimError(
            "a TOML date or time value cannot enter a root preimage; "
            "spell it as a string")
    if isinstance(value, dict):
        for item in value.values():
            _reject_temporal(item)
    elif isinstance(value, list):
        for item in value:
            _reject_temporal(item)


def step_class(step: dict) -> str:
    """Class defaults keep v1 semantics: produce is generated, else pinned."""
    declared = step.get("class")
    if isinstance(declared, str) and declared:
        return declared
    return "generated" if step.get("kind") == "produce" else "pinned"


def owned_outputs(parsed: dict) -> list:
    """Produce outputs this claim owns -- a produce step without `from`."""
    return [s["output"] for s in produces(parsed) if not s.get("from")]


def members(parsed: dict) -> list:
    """`[claim] assembles` entries, parsed into (name, root) pairs."""
    table = parsed.get("claim") or {}
    out = []
    for entry in table.get("assembles") or []:
        name, _, root = entry.rpartition("@")
        out.append((name, root))
    return out


def _is_number_ok(value) -> bool:
    return _is_number(value)
