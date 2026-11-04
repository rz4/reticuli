"""The kernel's identity layer: the canonical root and build-digest serialization."""
import hashlib
import json
import os
import stat

from .core import (  # noqa: F401
    DIGEST,
    FORMAT,
    GUIDANCE_KEYS,
    ClaimError,
    _hash_file,
    _safe,
)
from .recipe import (
    _inputs,
    _steps,
    load_recipe,
    produces,
)

# ------------------------------------------------------- identity and digest

def _claim_format(recipe) -> int:
    fmt = (recipe.get("claim") or {}).get("format", 1)
    return fmt if isinstance(fmt, int) and not isinstance(fmt, bool) else 1


def _preimage_recipe(recipe):
    """The recipe as it enters the root preimage.  Format 3+ removes producer
    guidance from every step; formats 4 and 5 additionally CANONICALIZE the
    step list (steps sorted by their canonical JSON encodings) — the steps are
    a set of obligations, and file order is authoring form, which can no more
    reject a realization than a hint's wording can (two conforming packs
    were measured minting different roots for one claim by order alone).
    Formats 1 and 2 pass the recipe through whole, so their roots never
    move.  The transform is defined identically in the reference
    implementation, or the two would disagree at formats 3 and 4.

    FORMAT 6 STOPS SORTING, because the premise was false where it mattered.
    Sorting assumes order cannot decide acceptance; gates execute in file
    order in a shared workspace, so a gate that reads what an earlier gate
    wrote makes order decide it.  Two claims differing only in the order of
    two such gates were measured sealing to ONE root with one auditing
    `earned` and the other `failed` (2026-11-04), and the reference
    implementation agreed on that root — the rule was unsound, not the
    implementation.  At format 6 the order is in the preimage, so those two
    claims are two roots, which is what they always were.

    Formats 3 to 5 keep sorting and keep every root sealed under them.  What
    protects THEM is a seal-time refusal: `recipe._refuse_ordered_gates`
    rejects a recipe whose gates are detectably order-dependent at a format
    that discards order.  That check is sound but incomplete — it reads gate
    commands, and a command can hide the dependency — so format 6 is the
    guarantee and the refusal is the net."""
    fmt = _claim_format(recipe)
    if fmt < 3:
        return recipe
    steps = recipe.get("step")
    if not isinstance(steps, list):
        return recipe
    stripped = []
    for step in steps:
        if isinstance(step, dict):
            stripped.append({k: v for k, v in step.items()
                             if k not in GUIDANCE_KEYS})
        else:
            stripped.append(step)
    if 4 <= fmt <= 5:
        stripped.sort(key=lambda s: json.dumps(s, sort_keys=True))
    out = dict(recipe)
    out["step"] = stripped
    return out


def root(recipe, claimdir: str) -> str:
    """THE CANONICAL ROOT.  The claim's identity, and interchange currency.

    lowercase hex sha256 of json.dumps(parts, sort_keys=True) with DEFAULT
    separators, where parts is

        "digest"          -> "sha256"                       the algorithm, in-band
        "recipe"          -> json.dumps(recipe, sort_keys=True)
        "input:<path>"    -> sha256(input bytes)            per [claim].inputs
        "pinned:<output>" -> sha256(output bytes)           per non-generated step

    Generated outputs never enter the preimage.  Every path crosses `_safe`
    first, so a recipe cannot name its way out of its own directory.

    AT FORMAT 3+, producer guidance is stripped from the recipe before it is
    serialized into the preimage (`_preimage_recipe`): two claims that differ
    only in how they instruct a producer are the same claim, because guidance
    cannot reject a realization.  Formats 1 and 2 serialize the whole recipe,
    so their roots are unchanged.
    """
    return hashlib.sha256(json.dumps(_parts(recipe, claimdir),
                                     sort_keys=True).encode("utf-8")).hexdigest()


def _parts(recipe, claimdir: str) -> dict:
    """The root's preimage parts, exactly as `root` hashes them."""
    if not isinstance(recipe, dict):
        raise ClaimError("a recipe must be a table")
    try:
        serialized = json.dumps(_preimage_recipe(recipe), sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise ClaimError(f"recipe is not serializable: {exc}") from None

    parts = {"digest": DIGEST, "recipe": serialized}
    for name in _inputs(recipe, claimdir):
        parts[f"input:{name}"] = _hash_file(_safe(claimdir, name))
    for step in _steps(recipe):
        if step.get("class") == "generated":
            continue                      # the equivalence class: never hashed
        output = step.get("output")
        if not isinstance(output, str) or not output:
            continue
        parts[f"pinned:{output}"] = _hash_file(_safe(claimdir, output))
    return parts


def build_digest(claimdir: str) -> str:
    """THE CANONICAL BUILD DIGEST.  The generated bytes a signature freezes.

    lowercase hex sha256 of json.dumps(sorted(own), sort_keys=True) with
    default separators, where `own` holds [output, sha256(bytes)] pairs for
    every step that is kind="produce", carries no `from` (a component's output
    is covered by folding that component's signature), is class="generated",
    and whose file is present.  An absent output is omitted; no such outputs
    digests the empty list.

    FORMAT 6 ADDS THE EXECUTABLE BIT, as a third element "x" or "-".  Content
    alone does not determine whether a gate can run its own output: `chmod
    644` on a generated program left this digest byte-identical while the
    cold audit went from earned to "Permission denied", so a signature froze
    two builds that do not behave the same (measured 2026-11-04).  Only that
    one bit is committed -- the read and write bits are the operator's
    business, the exec bit is the claim's.  Formats 1 through 5 digest pairs
    exactly as before, so every build digest sealed under them is unchanged.
    """
    recipe = load_recipe(claimdir)
    fmt = _claim_format(recipe)
    own = []
    for step in produces(recipe):
        if "from" in step:
            continue                      # belongs to a component, not to us
        if step.get("class") != "generated":
            continue                      # pinned bytes are the root's business
        output = step.get("output")
        if not isinstance(output, str) or not output:
            continue
        path = _safe(claimdir, output)
        if not os.path.isfile(path):
            continue                      # absent generated output: omitted
        entry = [output, _hash_file(path)]
        if fmt >= 6:
            entry.append("x" if os.stat(path).st_mode & stat.S_IXUSR else "-")
        own.append(entry)
    preimage = json.dumps(sorted(own), sort_keys=True).encode("utf-8")
    return hashlib.sha256(preimage).hexdigest()


def sign_node(root_hex: str, digest: str, below) -> str:
    """Fold one node of the signed identity chain, bottom-anchored.

    A layer's signature binds its root, the concrete generated bytes under that
    root, and the SET of signatures beneath it -- enumeration order is not
    identity, so the same DAG folds the same way however it is walked.
    """
    beneath = sorted({str(x) for x in (below or [])})
    payload = {"root": str(root_hex), "build_digest": str(digest), "below": beneath}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
