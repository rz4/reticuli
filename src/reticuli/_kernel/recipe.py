"""The kernel's recipe layer: parse and validate an untrusted recipe."""
import datetime
import json
import math
import os
import re
import tomllib

from .core import (
    COST_UNITS,
    FORMAT,
    KINDS,
    LEGACY_RECIPE,
    RECIPE,
    ClaimError,
    _safe,
)


def _steps(recipe) -> list:
    steps = (recipe or {}).get("step") or []
    return [s for s in steps if isinstance(s, dict)]


MANIFEST_KEY = "inputs_manifest"


def _read_input_manifest(claimdir: str, name: str) -> list:
    """Read a pinned list of input paths from a file instead of the recipe.

    A claim over a real corpus enumerates hundreds of files, and putting every
    path in the recipe body makes it unreadable and its diffs useless -- the
    TOML conformance example is 920 paths in a 44KB recipe. The list moves into
    a file, which is ITSELF a pinned input, so the whole set is still committed
    to by the root: change the corpus and the manifest changes and the root
    moves, exactly as before.

    What this must NOT become is a wildcard evaluated at read time. Identity
    would then depend on what happens to be in the directory when someone
    looks, which is the one thing a content address cannot tolerate. The
    manifest is a fixed list, written once at seal time.

    Format: one path per line, optionally `<sha256>  <path>` so the file is
    meaningful on its own. Blank lines and `#` comments are ignored.
    """
    path = _safe(claimdir, name)
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise ClaimError(f"unreadable [claim] {MANIFEST_KEY} {name}: {exc}") from None
    out = []
    for lineno, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        entry = parts[1].strip() if len(parts) == 2 and len(parts[0]) == 64 else line
        if not entry:
            raise ClaimError(f"{name}:{lineno}: empty input path")
        out.append(entry)
    return out


def _inputs(recipe, claimdir: str | None = None) -> list:
    claim = (recipe or {}).get("claim") or {}
    ins = claim.get("inputs") or []
    if isinstance(ins, str):
        ins = [ins]
    if not isinstance(ins, list):
        raise ClaimError("[claim] inputs must be a list of paths")
    for name in ins:
        if not isinstance(name, str):
            raise ClaimError(f"[claim] inputs must be paths: {name!r}")
    ins = list(ins)

    # The declared environment file is a pinned input: dependency versions
    # decide what "passes" means, so they are criteria, hashed into the root
    # like fixture bytes. Declaring it here rather than asking authors to
    # also list it under inputs keeps one declaration authoritative.
    env_file = claim.get("environment")
    if env_file is not None:
        if not isinstance(env_file, str) or not env_file:
            raise ClaimError(f"[claim] environment must be a path, got {env_file!r}")
        ins = ins + [env_file]

    listed = claim.get(MANIFEST_KEY)
    if listed is not None:
        if not isinstance(listed, str) or not listed:
            raise ClaimError(f"[claim] {MANIFEST_KEY} must be a path, got {listed!r}")
        if claimdir is None:
            # The manifest names a file, so the paths cannot be resolved from
            # the recipe alone. Callers that only have a parsed recipe get the
            # declared list; every caller that hashes or materializes passes
            # the directory.
            return ins + [listed]
        return ins + [listed] + _read_input_manifest(claimdir, listed)
    return ins


# --------------------------------------------------------------- the recipe

def recipe_path(claimdir: str):
    """The claim's recipe file, whichever of the two names it carries."""
    for name in (RECIPE, LEGACY_RECIPE):
        candidate = os.path.join(claimdir, name)
        if os.path.isfile(candidate):
            return candidate
    return None


def load_recipe(claimdir: str) -> dict:
    """Parse and validate `claim.toml`.  Hostile bytes are refused here.

    The step vocabulary is closed (produce, gate), so an unknown kind is caught
    at parse rather than surfacing later as a KeyError deep inside a rebuild.
    """
    path = recipe_path(claimdir)
    if path is None:
        raise ClaimError(
            f"no recipe at {os.path.join(claimdir, RECIPE)} "
            f"(nor {os.path.join(claimdir, LEGACY_RECIPE)})")
    try:
        with open(path, "rb") as f:
            recipe = tomllib.load(f)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise ClaimError(f"damaged recipe {path}: {exc}") from None
    if not isinstance(recipe, dict):
        raise ClaimError(f"damaged recipe {path}: not a table")

    claim = recipe.get("claim")
    if not isinstance(claim, dict):
        raise ClaimError(f"recipe has no [claim] table: {path}")
    name = claim.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ClaimError(f"recipe has no [claim] name: {path}")

    # Format version. Absent means 1, so today's claims declare nothing and
    # keep their roots. Its only job is DIAGNOSTIC: the recipe text is inside
    # the root, so a claim written in a future format already fails to verify
    # under an older kernel -- but it fails as a bare hash mismatch, which
    # says nothing about why. Declaring the format turns that into a sentence.
    declared = claim.get("format", 1)
    if isinstance(declared, bool) or not isinstance(declared, int) or declared < 1:
        raise ClaimError(f"[claim] format must be a positive integer, got {declared!r}")
    if declared > FORMAT:
        raise ClaimError(
            f"claim format {declared} is newer than this kernel understands "
            f"(format {FORMAT}); upgrade reticuli to read it")

    # The cost envelope: ceilings a redo commits to, per unit. Recipe content,
    # so the commitment is inside the root. Validated here so a hostile or
    # damaged table refuses at parse, not mid-crosscheck.
    envelope = claim.get("envelope")
    if envelope is not None:
        if not isinstance(envelope, dict) or not envelope:
            raise ClaimError("[claim] envelope must be a table of cost ceilings")
        unknown = set(envelope) - set(COST_UNITS)
        if unknown:
            raise ClaimError(f"[claim] envelope has unknown unit(s) "
                             f"{sorted(unknown)} (the units are {sorted(COST_UNITS)})")
        for unit, ceiling in envelope.items():
            # FINITE, and this was the half left behind. TOML admits `inf`
            # and `nan` as float literals, so `usd = inf` passed a check that
            # only asked for a positive number -- and `paid <= inf` is true
            # for every finite spend, so a claim could publish an apparently
            # hard budget that bound nothing. `nan` passed too, and makes the
            # ceiling unsatisfiable instead. `-inf` was refused only by
            # accident, by `<= 0`.
            #
            # Finiteness was already required of a RECORD's cost value
            # (attest.record_validate), of a MEASURED cost (run), and of
            # `tolerance` and `mutation_floor` thirty lines below -- the last
            # added 2026-10-29 under a comment naming this very check as the
            # exemplar it was modelled on. It was the exemplar for type and
            # sign; the copy added finiteness and nobody came back. The
            # envelope is the declaration side of a rule the measurement side
            # has enforced since r25 forced it (closure ledger, 2026-10-14).
            if isinstance(ceiling, bool) or not isinstance(ceiling, (int, float)) \
                    or not math.isfinite(ceiling) or ceiling <= 0:
                raise ClaimError(f"[claim] envelope {unit} must be a finite "
                                 f"positive number, got {ceiling!r}")

    # THE OTHER TWO DECLARED OBLIGATIONS, validated here for the same reason
    # and overlooked until 2026-10-29. `envelope` has always refused a
    # damaged table at parse; `tolerance` and `mutation_floor` are hard
    # conditions of the same kind and were taken on faith, each failing
    # silently in its own direction. A `tolerance = "banana"` was carried
    # all the way into the crosscheck, where it decided nothing and the
    # verdict came back `accept` -- a claim declaring a hard condition
    # nobody could evaluate, which is the one outcome the three-valued
    # verdict exists to prevent. A non-numeric `mutation_floor` was coerced
    # to None, silently discarding a bar the claim had published. A declared
    # obligation that cannot be read is a refusal, not a default.
    # The bars differ because the quantities do, and getting this wrong once
    # already recreated the defect it was meant to fix. `mutation_floor` is a
    # kill RATE, so 0 is legal and meaningful (a declared floor nothing can
    # fail) -- and `attest.record_validate` has always admitted `>= 0`, so
    # refusing 0 here would make a claim unparseable whose own record still
    # reads, stranding any already-sealed claim that declared it.
    # `tolerance` is a RATIO read as the band [1/t, t] by `_in_band`, so
    # anything below 1 names an EMPTY band -- `tolerance = 0.5` asks for
    # [2.0, 0.5], a condition no measurement can satisfy. That is refused
    # with a reason rather than left to fail silently at crosscheck time.
    for key, floor in (("tolerance", 1.0), ("mutation_floor", 0.0)):
        value = claim.get(key)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) \
                or not math.isfinite(value) or value < floor:
            raise ClaimError(
                f"[claim] {key} must be a finite number >= {floor:g}, "
                f"got {value!r}"
                + (" (the band is [1/t, t], so t < 1 is empty)"
                   if key == "tolerance" else ""))
    _refuse_ordered_gates(recipe)
    _inputs(recipe)

    # THE FORMAT-5 VOCABULARY, shape-validated here (an obligation must be
    # readable as what it claims to be); the semantic half lives where the
    # semantics do -- `constrains` ownership at seal, `assembles` resolution
    # at materialization. Each key is refused below format 5, because a
    # kernel that reads the key without enforcing it would let a judged
    # composition pass as mere residue -- the gate exists so older kernels
    # refuse in words rather than silently under-enforce.
    constrains = claim.get("constrains")
    if constrains is not None:
        if declared < 5:
            raise ClaimError("[claim] constrains needs claim format 5 or newer")
        if not isinstance(constrains, dict) or not constrains:
            raise ClaimError("[claim] constrains must be a non-empty table of "
                             "criterion path -> owned outputs")
        pinned = set(_inputs(recipe, os.path.dirname(path)))
        for criterion, targets in constrains.items():
            if criterion not in pinned:
                raise ClaimError(f"[claim] constrains names {criterion!r}, "
                                 "which is not a declared input")
            if not isinstance(targets, list) or not targets \
                    or any(not isinstance(t, str) or not t for t in targets):
                raise ClaimError(f"[claim] constrains {criterion!r} must name "
                                 "at least one output path")
    assembles = claim.get("assembles")
    if assembles is not None:
        if declared < 5:
            raise ClaimError("[claim] assembles needs claim format 5 or newer")
        if not isinstance(assembles, list) or not assembles:
            raise ClaimError("[claim] assembles must be a non-empty list of "
                             '"<name>@<root>" members')
        seen = set()
        for entry in assembles:
            if not isinstance(entry, str) or entry.count("@") != 1:
                raise ClaimError(f"[claim] assembles entry must be "
                                 f'"<name>@<root>", got {entry!r}')
            member, declared_root = entry.split("@")
            if not member or not re.fullmatch(r"[0-9a-f]{64}", declared_root):
                raise ClaimError(f"[claim] assembles entry must name a member "
                                 f"and its 64-hex root, got {entry!r}")
            if member in seen:
                raise ClaimError(f"[claim] assembles names {member!r} twice")
            seen.add(member)

    steps = recipe.get("step")
    if steps is None:
        steps = []
    if not isinstance(steps, list) or any(not isinstance(s, dict) for s in steps):
        raise ClaimError(f"[[step]] must be a list of tables: {path}")
    for index, step in enumerate(steps):
        kind = step.get("kind")
        if kind not in KINDS:
            raise ClaimError(f"unknown step kind: {kind!r} "
                             f"(the vocabulary is {sorted(KINDS)})")
        output = step.get("output")
        if output is not None and (not isinstance(output, str) or not output):
            raise ClaimError(f"a step output must be a path: {output!r}")
        cls = step.get("class")
        if cls == "carried":
            # hashed into the root like a pinned output, never regrown, copied
            # byte-for-byte at rebuild -- semantics an older kernel would not
            # guarantee, so the class arrives with the format that does
            if declared < 5:
                raise ClaimError(f"step {output!r} is class carried, which "
                                 "needs claim format 5 or newer")
            if kind != "produce":
                raise ClaimError(f"step {output!r}: only a produce step can "
                                 "be carried; a gate's verdict is earned, "
                                 "never copied")
        elif declared >= 5 and cls is not None \
                and cls not in ("generated", "pinned", "validated"):
            # format 5 closes the class vocabulary: before it, any unknown
            # string silently meant "pinned", which is how a typo became an
            # identity decision; older formats keep the loose reading so no
            # sealed claim is stranded
            raise ClaimError(
                f"step {output!r} has unknown class {cls!r} (the format-5 "
                "vocabulary is carried, generated, pinned, validated)")
        if kind == "gate":
            if not isinstance(step.get("run"), str) or not step["run"].strip():
                raise ClaimError(f"gate {output!r} has no run command")
            if not output:
                raise ClaimError(
                    f"a gate must declare the output it pins "
                    f"(step {index}, run {step.get('run')!r}): {path}")
    return recipe


_BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")


def _toml_key(key: str) -> str:
    return key if _BARE_KEY.match(key) else json.dumps(key, ensure_ascii=False)


def _toml_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        # json string escaping is valid TOML basic-string escaping; with
        # ensure_ascii off, non-ASCII text stays literal UTF-8, which TOML
        # allows and which avoids escapes TOML does not define.
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    if isinstance(value, dict):
        return ("{" + ", ".join(f"{_toml_key(k)} = {_toml_value(v)}"
                                for k, v in value.items()) + "}")
    raise ClaimError(
        f"cannot write a recipe value of type {type(value).__name__}")


def _dump_recipe(recipe: dict) -> str:
    """The PARSED recipe, written back as TOML that parses to the same tables.

    This exists so a judging room can be handed the recipe the root was
    computed from (`identity._preimage_recipe`) rather than the raw file: the
    raw file may carry producer guidance the root deliberately excludes, and a
    gate that read it could accept on words the identity does not cover.
    Formatting and comments are not identity -- the preimage serializes the
    parsed tables -- so only the tables are reproduced.  The result is parsed
    back before it is returned; a recipe this writer cannot reproduce exactly
    is refused, never approximated.
    """
    lines, tables, arrays = [], [], []
    for key, value in recipe.items():
        if isinstance(value, dict):
            tables.append((key, value))
        elif isinstance(value, list) and value \
                and all(isinstance(v, dict) for v in value):
            arrays.append((key, value))
        else:
            # scalars first: a bare `key = value` after a [table] header would
            # belong to that table, not to the document
            lines.append(f"{_toml_key(key)} = {_toml_value(value)}")
    for key, table in tables:
        if lines:
            lines.append("")
        lines.append(f"[{_toml_key(key)}]")
        for k, v in table.items():
            lines.append(f"{_toml_key(k)} = {_toml_value(v)}")
    for key, rows in arrays:
        for row in rows:
            if lines:
                lines.append("")
            lines.append(f"[[{_toml_key(key)}]]")
            for k, v in row.items():
                lines.append(f"{_toml_key(k)} = {_toml_value(v)}")
    text = "\n".join(lines) + "\n"
    try:
        parsed = tomllib.loads(text)
    except ValueError as exc:
        raise ClaimError(f"cannot rewrite the recipe as TOML: {exc}") from None
    if parsed != recipe:
        raise ClaimError("cannot rewrite the recipe as TOML: the round trip "
                         "did not reproduce it")
    return text


def _refuse_ordered_gates(recipe) -> None:
    """At a format that DISCARDS step order, refuse a recipe whose gates
    detectably depend on it.

    Gates run in file order in one workspace, and gate outputs are never
    materialized into a room, so a later gate reading what an earlier gate
    wrote makes order decide acceptance.  At formats 4 and 5 the preimage
    sorts the steps, so two orderings of such a recipe are ONE root with two
    verdicts -- measured 2026-11-04, kernel and reference agreeing on the
    root, which placed the defect in the specification rather than in either
    implementation.

    Format 6 fixes it properly by putting order back in the preimage.  This
    refusal is what protects the formats that cannot be changed without
    breaking roots already sealed under them: it keeps NEW claims out of the
    unsound shape without reinterpreting a single existing one.

    SOUND BUT INCOMPLETE, and deliberately so.  It reads gate commands for a
    literal mention of another gate's declared output, which catches the
    shape a person actually writes.  A command that reaches the same file
    through a variable, a wildcard, or a script is not caught, and nothing
    short of executing the recipe would catch it.  An incomplete check that
    says what it does not cover is worth more than no check; the complete
    answer is to declare `format = 6`.
    """
    fmt = (recipe.get("claim") or {}).get("format", 1)
    if not isinstance(fmt, int) or isinstance(fmt, bool) or not 4 <= fmt <= 5:
        return                            # order is identity, or never sorted
    produced = []
    for step in _steps(recipe):
        if step.get("kind") != "gate":
            continue
        output = step.get("output")
        command = step.get("run")
        if isinstance(command, str):
            for earlier in produced:
                if earlier in command:
                    raise ClaimError(
                        f"[[step]] gate {output!r} reads {earlier!r}, which an "
                        f"earlier gate writes, but format {fmt} sorts the step "
                        f"list into the root -- so this recipe and its reverse "
                        f"would share one root and disagree about acceptance. "
                        f"Declare format = 6, which commits step order, or "
                        f"make the gates independent")
        if isinstance(output, str) and output:
            produced.append(output)


def gates(recipe) -> list:
    return [s for s in _steps(recipe) if s.get("kind") == "gate"]


def produces(recipe) -> list:
    return [s for s in _steps(recipe) if s.get("kind") == "produce"]


def generated_outputs(recipe) -> list:
    return [s["output"] for s in produces(recipe)
            if s.get("class") == "generated" and isinstance(s.get("output"), str)]
