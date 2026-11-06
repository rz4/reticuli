"""Parsing an untrusted recipe into validated tables.

A claim's own recipe is untrusted input: it arrives with the claim, and a
hostile or merely damaged one must produce a refusal with a reason rather
than a raw TOMLDecodeError from somewhere deep inside the kernel.  So every
obligation a recipe declares is read HERE and held to its type here — an
unreadable hard condition must never reach a verdict (`spec/claim-format.md`,
*Validation rules*).

Two names are read.  `reticuli.toml` is canonical and preferred;
`claim.toml` is the pre-2026-09-16 spelling and stays readable forever,
because the filename is not in the root preimage — twins under the two names
are one claim with one root.
"""
import os
import tomllib

from .core import (CLASSES, ClaimError, FORMAT, GUIDANCE_KEYS, KINDS,
                   LEGACY_RECIPE, RECIPE, _finite)

#: Keys whose VALUE is a cost ceiling; the envelope admits no others.
_ENVELOPE_UNITS = ("usd", "tokens", "calls", "seconds")


def recipe_path(claimdir: str) -> str:
    """The claim's recipe file, canonical name preferred.

    The preference is not a fallback chain for convenience: both names must
    be read forever, and a kernel that knew only one was measured unable to
    read the very claim it satisfied (finding 13).
    """
    for name in (RECIPE, LEGACY_RECIPE):
        candidate = os.path.join(claimdir, name)
        if os.path.isfile(candidate):
            return candidate
    raise ClaimError(f"no recipe in {claimdir!r}: expected {RECIPE} "
                     f"(or the legacy {LEGACY_RECIPE})")


def _reject_times(value, where: str = "recipe") -> None:
    """TOML date and time values are refused at sealing.

    JSON gives them no canonical form, so they cannot enter a preimage: a
    claim carrying one has no computable identity, and the honest answer is a
    refusal rather than a root nobody else would reproduce.
    """
    import datetime
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        raise ClaimError(
            f"{where} carries a TOML date/time value ({value!r}); JSON gives "
            f"it no canonical form, so it cannot enter a root preimage")
    if isinstance(value, dict):
        for key, item in value.items():
            _reject_times(item, f"{where}.{key}")
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_times(item, where)


def _str_list(value, what: str) -> list:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(x, str) for x in value):
        raise ClaimError(f"[claim] {what} must be a list of strings")
    return list(value)


def _check_envelope(envelope) -> None:
    """A non-empty table of known units, each ceiling a FINITE positive number.

    `inf` accepts every finite spend and `nan` rejects every one, so either
    would publish an apparently hard budget that bound nothing or that
    nothing could satisfy.  A ceiling that cannot be exceeded is not a
    ceiling.
    """
    if not isinstance(envelope, dict) or not envelope:
        raise ClaimError(
            "[claim] envelope must be a non-empty table of cost ceilings")
    for unit, ceiling in envelope.items():
        if unit not in _ENVELOPE_UNITS:
            raise ClaimError(
                f"[claim] envelope names an unknown unit {unit!r}; "
                f"the vocabulary is {', '.join(_ENVELOPE_UNITS)}")
        if not _finite(ceiling) or ceiling <= 0:
            raise ClaimError(
                f"[claim] envelope {unit} = {ceiling!r} is not a finite "
                f"positive number — a ceiling that cannot be exceeded is "
                f"not a ceiling")


def _check_obligations(claim: dict) -> None:
    """Every declared obligation must be readable as what it claims to be."""
    if "envelope" in claim:
        _check_envelope(claim["envelope"])
    if "tolerance" in claim:
        tolerance = claim["tolerance"]
        if not _finite(tolerance) or tolerance < 1:
            raise ClaimError(
                f"[claim] tolerance = {tolerance!r} must be a finite number "
                f">= 1; it is read as the band [1/t, t], so t < 1 names an "
                f"empty band no measurement can satisfy")
    if "mutation_floor" in claim:
        floor = claim["mutation_floor"]
        if not _finite(floor) or floor < 0:
            raise ClaimError(
                f"[claim] mutation_floor = {floor!r} must be a finite "
                f"number >= 0")
    if "gate_timeout" in claim:
        bound = claim["gate_timeout"]
        if not _finite(bound) or bound <= 0:
            raise ClaimError(
                f"[claim] gate_timeout = {bound!r} must be a finite "
                f"positive number of seconds")
    _str_list(claim.get("requires"), "requires")
    if "environment" in claim and not isinstance(claim["environment"], str):
        raise ClaimError("[claim] environment must name one file")
    if "inputs_manifest" in claim and not isinstance(
            claim["inputs_manifest"], str):
        raise ClaimError("[claim] inputs_manifest must name one file")


def _check_format5_vocabulary(claim: dict, steps: list, fmt: int) -> None:
    """Format 5 admits new vocabulary; below it, declaring any of it refuses.

    Each new key carries semantics an older kernel would not enforce —
    carried bytes copied rather than regrown, `constrains` held at seal,
    members held to their declared roots — so a kernel that would read the
    words without holding the claim to them must refuse in words instead.
    """
    carried = [s for s in steps if s.get("class") == "carried"]
    if carried and fmt < 5:
        raise ClaimError(
            f"step class 'carried' needs format 5; this recipe declares "
            f"format {fmt}. Carried bytes ship without being regrown, which "
            f"an older kernel would not enforce — declare format = 5")
    for step in carried:
        if step.get("kind") != "produce":
            raise ClaimError(
                f"[[step]] {step.get('output')!r} is a carried gate; only a "
                f"produce step may be carried — a gate's verdict is earned, "
                f"never copied")
    if "constrains" in claim and fmt < 5:
        raise ClaimError(
            f"[claim] constrains needs format 5; this recipe declares "
            f"format {fmt}")
    if "assembles" in claim and fmt < 5:
        raise ClaimError(
            f"[claim] assembles needs format 5; this recipe declares "
            f"format {fmt}")
    if fmt >= 5:
        for step in steps:
            cls = step.get("class")
            if cls is not None and cls not in CLASSES:
                raise ClaimError(
                    f"[[step]] {step.get('output')!r} declares the unknown "
                    f"class {cls!r}; at format 5 the class vocabulary is "
                    f"closed ({', '.join(sorted(CLASSES))})")
    declared_inputs = set(_str_list(claim.get("inputs"), "inputs"))
    constrains = claim.get("constrains")
    if constrains is not None:
        if not isinstance(constrains, dict):
            raise ClaimError("[claim] constrains must be a table")
        for key, targets in constrains.items():
            if key not in declared_inputs:
                raise ClaimError(
                    f"[claim] constrains names {key!r}, which is not a "
                    f"declared input; a criterion must be pinned to constrain "
                    f"anything")
            _str_list(targets, f"constrains[{key!r}]")
    members = claim.get("assembles")
    if members is not None:
        for entry in _str_list(members, "assembles"):
            name, _, root = entry.partition("@")
            if not name or len(root) != 64 or any(
                    c not in "0123456789abcdef" for c in root):
                raise ClaimError(
                    f"[claim] assembles entry {entry!r} is not "
                    f"'<name>@<64-hex root>'")


def _check_gate_order(steps: list, fmt: int) -> None:
    """Formats 4 and 5 sort the step list, so a gate chain there is unsound.

    Gates run in file order in one shared workspace, so a gate reading what
    an earlier gate wrote makes the order decide acceptance — and at format 4
    the order is not in the root.  A root sealed under 4 or 5 must keep
    verifying, so the repair is format 6 and the protection here is a
    refusal.  It reads gate commands for a literal mention of an earlier
    gate's declared output, which catches the shape an author writes by hand;
    it is sound but deliberately incomplete, and `spec/claim-format.md` says
    so.
    """
    if fmt not in (4, 5):
        return
    written: list = []
    for step in steps:
        if step.get("kind") != "gate":
            continue
        command = step.get("run") or ""
        for earlier in written:
            if earlier and earlier in command:
                raise ClaimError(
                    f"[[step]] gate {step.get('output')!r} reads "
                    f"{earlier!r}, which an earlier gate writes, but format "
                    f"{fmt} sorts the step list into the root — so this "
                    f"recipe and its reverse would share one root and "
                    f"disagree about acceptance. Declare format = 6, which "
                    f"commits step order, or make the gates independent")
        written.append(step.get("output"))


def load_recipe(claimdir: str) -> dict:
    """Parse and validate a claim's recipe; refusals, never crashes."""
    path = recipe_path(claimdir)
    try:
        with open(path, "rb") as handle:
            parsed = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ClaimError(f"{path}: not readable as TOML ({exc})") from None
    except OSError as exc:
        raise ClaimError(f"{path}: {exc.strerror or exc}") from None
    if not isinstance(parsed, dict):
        raise ClaimError(f"{path}: the recipe is not a table")
    _reject_times(parsed)

    claim = parsed.get("claim")
    if claim is None:
        raise ClaimError(
            f"{path}: no [claim] table — a recipe states what claim it is")
    if not isinstance(claim, dict):
        raise ClaimError(f"{path}: [claim] must be a table")
    name = claim.get("name")
    if not isinstance(name, str) or not name:
        raise ClaimError(f"{path}: [claim] name is required and must be a "
                         f"string, not {name!r}")

    fmt = claim.get("format", 1)
    if isinstance(fmt, bool) or not isinstance(fmt, int) or fmt < 1:
        raise ClaimError(f"{path}: [claim] format must be a positive integer")
    if fmt > FORMAT:
        raise ClaimError(
            f"claim format {fmt} is newer than this kernel understands "
            f"(format {FORMAT}); upgrade reticuli to read it")

    _str_list(claim.get("inputs"), "inputs")
    _check_obligations(claim)

    steps = parsed.get("step", [])
    if steps is None:
        steps = []
    if not isinstance(steps, list):
        raise ClaimError(f"{path}: [[step]] must be an array of tables")
    for step in steps:
        if not isinstance(step, dict):
            raise ClaimError(f"{path}: every [[step]] must be a table")
        kind = step.get("kind")
        if kind not in KINDS:
            raise ClaimError(
                f"{path}: [[step]] kind {kind!r} is not in the step "
                f"vocabulary ({', '.join(sorted(KINDS))})")
        output = step.get("output")
        if not isinstance(output, str) or not output:
            raise ClaimError(f"{path}: every [[step]] needs an output")
        if kind == "gate" and not isinstance(step.get("run"), str):
            raise ClaimError(
                f"{path}: gate {output!r} needs a run command")
        if "from" in step and not isinstance(step["from"], str):
            raise ClaimError(f"{path}: [[step]] from must name a component")

    _check_format5_vocabulary(claim, steps, fmt)
    _check_gate_order(steps, fmt)
    parsed["step"] = steps
    return parsed


def _steps(parsed: dict) -> list:
    """Every step, in file order."""
    steps = parsed.get("step") or []
    return list(steps)


def step_class(step: dict, fmt: int = 1) -> str:
    """A step's effective class.

    A produce step defaults to `generated`; any other step output defaults to
    `pinned`.  Below format 5 an unrecognized class silently means `pinned`,
    and that loose reading is kept there so no sealed claim is stranded.
    """
    cls = step.get("class")
    if cls in CLASSES:
        return cls
    if cls is None:
        return "generated" if step.get("kind") == "produce" else "pinned"
    return "pinned"


def gates(parsed: dict) -> list:
    """The gate steps, in file order — the order they execute in."""
    return [s for s in _steps(parsed) if s.get("kind") == "gate"]


def produces(parsed: dict) -> list:
    """The produce steps, in file order."""
    return [s for s in _steps(parsed) if s.get("kind") == "produce"]


def generated_outputs(parsed: dict) -> list:
    """The outputs whose bytes the root does not cover — the implementation."""
    fmt = int(parsed.get("claim", {}).get("format", 1) or 1)
    return [s["output"] for s in produces(parsed)
            if step_class(s, fmt) == "generated"]


def carried_outputs(parsed: dict) -> list:
    """Format-5 carried outputs: shipped, hashed, never regrown."""
    fmt = int(parsed.get("claim", {}).get("format", 1) or 1)
    return [s["output"] for s in produces(parsed)
            if step_class(s, fmt) == "carried"]


def pinned_outputs(parsed: dict) -> list:
    """Every step output whose bytes ARE inside the root."""
    fmt = int(parsed.get("claim", {}).get("format", 1) or 1)
    return [s["output"] for s in _steps(parsed)
            if step_class(s, fmt) != "generated"]


def _read_input_manifest(path: str) -> list:
    """The paths an `inputs_manifest` lists.

    One entry per line, optionally `<sha256>  <path>` so the file is
    meaningful on its own; blank lines and `#` comments are ignored.  It is a
    fixed list, never a pattern: a wildcard evaluated at read time would make
    identity depend on directory contents, which is the one thing a content
    address cannot tolerate.
    """
    try:
        with open(path, encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except OSError as exc:
        raise ClaimError(f"{path}: {exc.strerror or exc}") from None
    except UnicodeDecodeError as exc:
        raise ClaimError(f"{path}: not readable as text ({exc})") from None
    out = []
    for line in lines:
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        fields = entry.split()
        out.append(fields[-1] if len(fields) > 1 else fields[0])
    return out


def _inputs(parsed: dict, claimdir: str) -> list:
    """The pinned-input set — wider than `[claim] inputs`.

    It is the union of the declared list, the file named by `[claim]
    environment` (dependency versions decide what "passes" means, so they are
    criteria), and at format 2 and above the `inputs_manifest` PLUS every
    path that file lists.  An implementation that reads only `inputs`
    computes wrong roots for two kinds of legal claim.
    """
    claim = parsed.get("claim", {})
    out = list(claim.get("inputs") or [])
    environment = claim.get("environment")
    if environment:
        out.append(environment)
    fmt = int(claim.get("format", 1) or 1)
    manifest = claim.get("inputs_manifest")
    if fmt >= 2 and manifest:
        out.append(manifest)
        out.extend(_read_input_manifest(_safe_join(claimdir, manifest)))
    return out


def _safe_join(claimdir: str, name: str) -> str:
    from .core import _safe
    return _safe(claimdir, name)


def declared_inputs(parsed: dict, claimdir: str) -> list:
    """`_inputs`, under the name the layers above import."""
    return _inputs(parsed, claimdir)


def step_guidance(step: dict):
    """A produce step's producer hint, under either spelling."""
    for key in GUIDANCE_KEYS:
        if isinstance(step.get(key), str):
            return step[key]
    return None
