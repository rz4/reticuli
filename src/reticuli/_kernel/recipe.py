"""The kernel's recipe layer: parse and validate an untrusted recipe."""
import os
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
            if isinstance(ceiling, bool) or not isinstance(ceiling, (int, float)) \
                    or ceiling <= 0:
                raise ClaimError(f"[claim] envelope {unit} must be a positive "
                                 f"number, got {ceiling!r}")
    _inputs(recipe)

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
        if kind == "gate":
            if not isinstance(step.get("run"), str) or not step["run"].strip():
                raise ClaimError(f"gate {output!r} has no run command")
            if not output:
                raise ClaimError(
                    f"a gate must declare the output it pins "
                    f"(step {index}, run {step.get('run')!r}): {path}")
    return recipe


def gates(recipe) -> list:
    return [s for s in _steps(recipe) if s.get("kind") == "gate"]


def produces(recipe) -> list:
    return [s for s in _steps(recipe) if s.get("kind") == "produce"]


def generated_outputs(recipe) -> list:
    return [s["output"] for s in produces(recipe)
            if s.get("class") == "generated" and isinstance(s.get("output"), str)]
