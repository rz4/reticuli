"""Parsing an untrusted recipe.

A claim's recipe is the claim's own bytes, which makes it input a verifier
did not write: every malformed, hostile or simply newer recipe is refused in
band, with a sentence, never a raw TOMLDecodeError from somewhere deep.

Both filenames are read -- `reticuli.toml` is canonical and `claim.toml`
stays readable forever -- and the filename is outside the root preimage, so
twins under the two names share one identity.
"""
import os
import tomllib

from .core import (CLASSES, ClaimError, COST_UNITS, FORMAT, GUIDANCE_KEYS,
                   KINDS, LEGACY_RECIPE, RECIPE, _finite, _safe)


def recipe_path(claim: str) -> str:
    """Where this claim's recipe is, preferring the canonical name."""
    for name in (RECIPE, LEGACY_RECIPE):
        candidate = os.path.join(claim, name)
        if os.path.isfile(candidate):
            return candidate
    raise ClaimError(
        f"no recipe in {claim}: expected {RECIPE} (or {LEGACY_RECIPE})")


def _steps(parsed: dict) -> list:
    """The step list, in file order."""
    steps = parsed.get("step") or []
    if not isinstance(steps, list):
        raise ClaimError("[[step]] must be a list of tables")
    return steps


def _class_of(step: dict) -> str:
    """A produce step defaults to generated; any other output is pinned."""
    declared = step.get("class")
    if isinstance(declared, str) and declared:
        return declared
    return "generated" if step.get("kind") == "produce" else "pinned"


def gates(parsed: dict) -> list:
    return [s for s in _steps(parsed) if s.get("kind") == "gate"]


def produces(parsed: dict) -> list:
    return [s for s in _steps(parsed) if s.get("kind") == "produce"]


def generated_outputs(parsed: dict) -> list:
    return [s["output"] for s in produces(parsed)
            if _class_of(s) == "generated"]


def carried_outputs(parsed: dict) -> list:
    return [s["output"] for s in produces(parsed) if _class_of(s) == "carried"]


def pinned_outputs(parsed: dict) -> list:
    """Every step output the root covers -- anything not `generated`."""
    return [s["output"] for s in _steps(parsed)
            if s.get("output") and _class_of(s) != "generated"]


def step_class(step: dict) -> str:
    return _class_of(step)


def _read_input_manifest(claim: str, name: str) -> list:
    """The paths a format-2 manifest lists.

    One entry per line, optionally `<sha256>  <path>` so the file is
    meaningful on its own; blank lines and `#` comments are ignored. It is a
    FIXED LIST, never a pattern: a wildcard evaluated at read time would make
    identity depend on directory contents, which is the one thing a content
    address cannot tolerate.
    """
    path = _safe(claim, name)
    if not os.path.isfile(path):
        raise ClaimError(f"inputs_manifest names no file: {name}")
    listed = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            fields = line.split()
            listed.append(fields[-1] if len(fields) > 1 else fields[0])
    return listed


def _inputs(parsed: dict, claim: str) -> list:
    """Every path the root covers as a pinned INPUT.

    Wider than `[claim] inputs`, and an implementation that reads only that
    list computes wrong roots for two kinds of legal claim (spec/identity.md):
    the `environment` file is a criterion because dependency versions decide
    what passing means, and at format 2 the `inputs_manifest` is pinned
    together with every path it lists.
    """
    claim_table = parsed.get("claim") or {}
    declared = list(claim_table.get("inputs") or [])
    environment = claim_table.get("environment")
    if isinstance(environment, str) and environment:
        declared.append(environment)
    manifest = claim_table.get("inputs_manifest")
    if isinstance(manifest, str) and manifest and _claim_format(parsed) >= 2:
        declared.append(manifest)
        declared.extend(_read_input_manifest(claim, manifest))
    seen, ordered = set(), []
    for path in declared:
        if path not in seen:
            seen.add(path)
            ordered.append(path)
    return ordered


def _claim_format(parsed: dict) -> int:
    table = parsed.get("claim") or {}
    declared = table.get("format")
    if declared is None:
        return 1
    if isinstance(declared, bool) or not isinstance(declared, int) \
            or declared < 1:
        raise ClaimError(f"[claim] format must be a positive integer, "
                         f"not {declared!r}")
    return declared


def _reject_future(fmt: int) -> None:
    if fmt > FORMAT:
        raise ClaimError(
            f"claim format {fmt} is newer than this kernel understands "
            f"(format {FORMAT}); upgrade reticuli to read it")


def _check_envelope(table) -> None:
    """A ceiling that cannot be exceeded is not a ceiling."""
    if not isinstance(table, dict) or not table:
        raise ClaimError("[claim] envelope must be a non-empty table of "
                         "cost ceilings")
    for unit, ceiling in table.items():
        if unit not in COST_UNITS:
            raise ClaimError(f"[claim] envelope names an unknown unit: "
                             f"{unit!r} (known: {', '.join(COST_UNITS)})")
        if not _finite(ceiling) or ceiling <= 0:
            raise ClaimError(f"[claim] envelope {unit} must be a finite "
                             f"positive number, not {ceiling!r}")


def _check_obligations(table: dict) -> None:
    """Every declared obligation must be readable as what it claims to be:
    a hard condition nobody can evaluate must not reach a verdict."""
    if "envelope" in table:
        _check_envelope(table["envelope"])
    if "tolerance" in table:
        value = table["tolerance"]
        if not _finite(value) or value < 1:
            raise ClaimError(
                f"[claim] tolerance must be a finite number >= 1 (it is read "
                f"as the band [1/t, t], so t < 1 names an empty band), "
                f"not {value!r}")
    if "mutation_floor" in table:
        value = table["mutation_floor"]
        if not _finite(value) or value < 0:
            raise ClaimError(f"[claim] mutation_floor must be a finite "
                             f"number >= 0, not {value!r}")
    if "gate_timeout" in table:
        value = table["gate_timeout"]
        if not _finite(value) or value <= 0:
            raise ClaimError(f"[claim] gate_timeout must be a finite "
                             f"positive number, not {value!r}")
    requires = table.get("requires")
    if requires is not None and (not isinstance(requires, list) or
                                 any(not isinstance(r, str)
                                     for r in requires)):
        raise ClaimError("[claim] requires must be a list of strings")


def _check_format5(parsed: dict, fmt: int) -> None:
    """The format-5 vocabulary carries semantics an older kernel would not
    enforce, so a declaration below 5 refuses in words -- and at 5 the class
    vocabulary is CLOSED, because an unknown class silently meaning "pinned"
    is a typo deciding identity."""
    table = parsed.get("claim") or {}
    steps = _steps(parsed)
    carried = [s for s in steps if s.get("class") == "carried"]
    if fmt < 5:
        if carried:
            raise ClaimError(
                f"step {carried[0].get('output')!r} declares class "
                f"'carried', which format 5 introduced; declare format = 5")
        for key in ("constrains", "assembles"):
            if key in table:
                raise ClaimError(
                    f"[claim] {key} is format-5 vocabulary whose semantics "
                    f"this claim's format ({fmt}) does not enforce; "
                    f"declare format = 5")
        return
    for step in steps:
        declared = step.get("class")
        if declared is not None and declared not in CLASSES:
            raise ClaimError(
                f"unknown step class {declared!r} for "
                f"{step.get('output')!r}; at format 5 the class vocabulary "
                f"is closed ({', '.join(sorted(CLASSES))})")
    for step in carried:
        if step.get("kind") != "produce":
            raise ClaimError(
                f"only a produce step may be carried; {step.get('output')!r} "
                f"is a {step.get('kind')!r} -- a gate's verdict is earned, "
                f"never copied")
    members = table.get("assembles")
    if members is not None:
        if not isinstance(members, list):
            raise ClaimError("[claim] assembles must be a list of "
                             "'<name>@<64-hex root>' entries")
        for entry in members:
            if not isinstance(entry, str) or "@" not in entry:
                raise ClaimError(f"[claim] assembles entry must be "
                                 f"'<name>@<root>': {entry!r}")
            name, _, root = entry.rpartition("@")
            if not name or len(root) != 64 or \
                    any(c not in "0123456789abcdef" for c in root):
                raise ClaimError(
                    f"[claim] assembles entry {entry!r} does not name a "
                    f"member by a 64-hex root")
    constrains = table.get("constrains")
    if constrains is not None:
        if not isinstance(constrains, dict):
            raise ClaimError("[claim] constrains must be a table mapping a "
                             "pinned criterion to the outputs it constrains")
        declared_inputs = set(table.get("inputs") or [])
        for key, targets in constrains.items():
            if key not in declared_inputs:
                raise ClaimError(
                    f"[claim] constrains names {key!r}, which is not a "
                    f"declared input of this claim")
            if not isinstance(targets, list) or \
                    any(not isinstance(t, str) for t in targets):
                raise ClaimError(f"[claim] constrains {key!r} must list "
                                 f"output names")


def _check_gate_order(parsed: dict, fmt: int) -> None:
    """Formats 4 and 5 sort the step list into the root, so two recipes
    differing only in gate ORDER share one root and can disagree about
    acceptance. Those roots must keep verifying, so the protection is a
    refusal rather than a repair -- sound, and deliberately incomplete: it
    reads a gate command for a literal mention of another gate's output.
    """
    if fmt not in (4, 5):
        return
    written = []
    for step in _steps(parsed):
        if step.get("kind") != "gate":
            continue
        command = step.get("run") or ""
        for earlier in written:
            if earlier and earlier in command:
                raise ClaimError(
                    f"[[step]] gate {step.get('output')!r} reads "
                    f"{earlier!r}, which an earlier gate writes, but format "
                    f"{fmt} sorts the step list into the root -- so this "
                    f"recipe and its reverse would share one root and "
                    f"disagree about acceptance. Declare format = 6, which "
                    f"commits step order, or make the gates independent")
        written.append(step.get("output"))


def load_recipe(claim: str) -> dict:
    """Parse and validate a claim's recipe. Refusals, never crashes."""
    path = recipe_path(claim)
    try:
        with open(path, "rb") as handle:
            parsed = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ClaimError(f"{path} is not valid TOML: {exc}") from None
    except (OSError, UnicodeDecodeError) as exc:
        raise ClaimError(f"{path} is not readable: {exc}") from None
    if not isinstance(parsed, dict):
        raise ClaimError(f"{path} is not a recipe")

    table = parsed.get("claim")
    if table is None:
        raise ClaimError(f"{path} declares no [claim] table")
    if not isinstance(table, dict):
        raise ClaimError("[claim] must be a table")
    name = table.get("name")
    if not isinstance(name, str) or not name:
        raise ClaimError("[claim] name is required and must be a string")

    fmt = _claim_format(parsed)
    _reject_future(fmt)
    _check_obligations(table)

    inputs = table.get("inputs")
    if inputs is not None and (not isinstance(inputs, list) or
                               any(not isinstance(i, str) for i in inputs)):
        raise ClaimError("[claim] inputs must be a list of paths")

    outputs = set()
    for step in _steps(parsed):
        if not isinstance(step, dict):
            raise ClaimError("every [[step]] must be a table")
        kind = step.get("kind")
        if kind not in KINDS:
            raise ClaimError(
                f"unknown step kind {kind!r}; a step is one of "
                f"{', '.join(sorted(KINDS))}")
        output = step.get("output")
        if not isinstance(output, str) or not output:
            raise ClaimError(f"a {kind} step needs an output name")
        if output in outputs:
            raise ClaimError(f"two steps declare the output {output!r}; "
                             f"one path, one owner")
        outputs.add(output)
        if kind == "gate" and not isinstance(step.get("run"), str):
            raise ClaimError(f"the gate {output!r} needs a run command")

    _check_format5(parsed, fmt)
    _check_gate_order(parsed, fmt)
    return parsed


def strip_guidance(parsed: dict, fmt: int) -> dict:
    """The recipe as the preimage sees it: at format 3 and above a producer
    hint is not identity, because guidance helps a producer FIND a
    realization and must never decide whether one is ACCEPTED."""
    if fmt < 3:
        return parsed
    lean = dict(parsed)
    steps = []
    for step in _steps(parsed):
        steps.append({k: v for k, v in step.items()
                      if k not in GUIDANCE_KEYS})
    if "step" in lean:
        lean["step"] = steps
    return lean


def step_guidance(step: dict):
    """The hint a producer is handed, under either spelling."""
    for key in GUIDANCE_KEYS:
        value = step.get(key)
        if isinstance(value, str) and value:
            return value
    return None
