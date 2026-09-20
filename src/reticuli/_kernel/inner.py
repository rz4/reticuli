"""The kernel's inner layer: identity, the recipe, the seal.

Constants, the path and bytes boundaries, recipe parsing, the canonical
root and build-digest, and seal/verify -- everything the kernel needs
before it ever runs a gate. No execution, no sandbox, no network.
Carved out of kernel.py so the kernel can be rebuilt as a chain of
sub-claims; kernel.py re-exports every name here.
"""
import hashlib
import json
import os
import shutil
import stat
import sys
import time
import tomllib

# ---------------------------------------------------------------- vocabulary

RECIPE = "reticuli.toml"
#: What the recipe was called before the file took the tool's name. Claims
#: sealed under it stay readable forever: the filename is NOT in the root
#: preimage -- `parts["recipe"]` is the PARSED recipe -- so a rename moves no
#: root, and a reader that only knew one name would refuse a claim whose
#: identity is unchanged. New claims are written as RECIPE.
LEGACY_RECIPE = "claim.toml"
STORE = ".reticuli"
MANIFEST = os.path.join(STORE, "manifest.json")
LEDGER = os.path.join(STORE, "ledger.jsonl")
SIGN_DIR = os.path.join(STORE, "mint")
MUTATION_RESIDUE = os.path.join(STORE, "mutation_score.json")
USAGE = os.path.join(STORE, "usage.json")

DIGEST = "sha256"

#: The claim-format version this kernel understands. A recipe may declare
#: `[claim] format`; absent means 1, so existing claims keep their identity.
#: Format 3 removes producer GUIDANCE from the root preimage (see `root`): a
#: hint that helps a producer find a realization cannot decide whether one is
#: accepted, so it is not part of identity. Formats 1 and 2 are unchanged, so
#: every claim sealed under them keeps its root.
FORMAT = 3

#: Step keys that are GUIDANCE, not criteria: they instruct a producer, they
#: never judge its output. Excluded from the preimage at format 3+.
GUIDANCE_KEYS = ("request", "guidance")

#: ssh signature namespaces -- interchange currency, carried from v1 so that
#: signatures made by one kernel verify under another.  The two domains are
#: distinct on purpose: an attestation must never authorize a mint.
NAMESPACE = "reticuli"
SIGN_NAMESPACE = "reticuli.mint"

#: "you are already inside a platform sandbox" -- one well-known name, so a
#: conformant kernel inherits the jail instead of trying to nest one.
_JAILED = "RETICULI_JAILED"

#: environment knobs a host may set
_ENV_TIMEOUT = "RETICULI_GATE_TIMEOUT"
_ENV_SIGNERS = "RETICULI_SIGNERS"
_ENV_TOLERANCE = "RETICULI_TOLERANCE"
_ENV_VENDOR = "RETICULI_VENDOR"
_ENV_MODEL = "RETICULI_MODEL"

#: environment a producer is handed
_ENV_OUTPUT = "RETICULI_OUTPUT"
_ENV_OUTPUTS = "RETICULI_OUTPUTS"
_ENV_REQUEST = "RETICULI_REQUEST"
_ENV_USAGE = "RETICULI_USAGE"
_ENV_CLAIM = "RETICULI_CLAIM"

KINDS = frozenset({"produce", "gate"})
GATE_TIMEOUT = 600.0
#: Building a claim's declared environment (venv + hash-pinned installs) may
#: download wheels; give it its own generous ceiling, separate from gates.
FURNISH_TIMEOUT = 900.0
#: Where furnished environments are cached, overridable for tests and for
#: hosts with their own cache discipline. The cache is host residue: keyed by
#: the environment file's digest, never part of any identity.
_ENV_CACHE = "RETICULI_ENV_CACHE"
#: A mutant gets this multiple of the healthy GATE's own runtime before the
#: clock counts as having detected it, bounded at both ends: never less than
#: the floor, since a gate that passes in 40ms must not have its mutants judged
#: against 400ms of a loaded machine, and never more than the ceiling, since a
#: slow gate would otherwise make a twenty-mutant run unaffordable.
MUTANT_HEADROOM = 10.0
MUTANT_FLOOR = 5.0
MUTANT_CEILING = 60.0
PRODUCER_TIMEOUT = 3600.0
TOLERANCE = 2.0
COST_KEYS = ("calls", "tokens", "usd")
# What `cost` totals. Wider than COST_KEYS on purpose: a producer may REPORT
# calls/tokens/usd, but wall-clock is the kernel's own measurement and must
# never be overwritten by a self-report -- so "seconds" is totalled here and
# not accepted from a usage payload. It is the last unit of the cost
# envelope's unit ladder (usd > tokens > calls > seconds); without it, two
# machines that measured only wall-clock share no unit to compare.
COST_UNITS = ("calls", "tokens", "usd", "seconds")
# The cost envelope compares ONE unit: the strongest both machines measured.
# Money is better evidence of work than tokens, tokens than calls, and
# wall-clock is the last resort -- it measures the host and its load as much
# as the work, so it must never veto a comparison a stronger unit can make.
COST_LADDER = ("usd", "tokens", "calls", "seconds")

#: env names a gate is allowed to see.  Everything else is scrubbed, so a
#: hostile gate cannot read an inherited secret and seal it into a verdict.
_KEEP_ENV = ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "TZ", _JAILED)

_SHELL = shutil.which("sh") or "/bin/sh"


class ClaimError(Exception):
    """A claim is damaged, hostile, or cannot be judged here.

    Everything the kernel refuses, it refuses in band with this: hostile bytes
    never surface as a raw TOMLDecodeError / JSONDecodeError / KeyError, and a
    verifier facing a wreck neither crashes nor blesses it.
    """


# ------------------------------------------------------------- small helpers

def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _judging_host() -> None:
    """Judging executes claim code -- sandboxes, process groups, sh -- and
    all of it is POSIX. Identity (root, seal, verify, reading records) works
    on any platform; on any other, judging refuses here, in band and in
    words, instead of dying in a traceback halfway through a verdict.
    """
    if os.name != "posix":
        raise ClaimError(
            f"judging runs on POSIX (macOS or Linux); this platform "
            f"({sys.platform}) can verify identity but cannot run gates")


def _write_json(path: str, payload) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, sort_keys=True, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def _safe(claimdir: str, name: str) -> str:
    """THE PATH BOUNDARY.  Resolve `name` inside the claim, or refuse.

    A claim's own recipe is untrusted input: a name that is absolute, climbs
    out with `..`, or is a symlink would let the kernel read or write outside
    the claim it is judging -- or alias one part of the claim as another.

    NO COMPONENT OF A DECLARED PATH MAY BE A SYMLINK, not even one whose
    target stays inside the claim.  An internal link from a pinned name to a
    generated output smuggles bytes across the pinned/generated boundary in
    both directions the design cares about: sealing hashes generated bytes
    into the root through the alias, and materializing flattens the link, so
    a blind rebuilder's room arrives holding the implementation it was never
    to see.  `..` is refused outright for the same reason a lexical check
    cannot be trusted: `link/../x` resolves relative to the link's target,
    not its name.  The hardlink rule in `_hash_file` closes this channel's
    twin.
    """
    if not isinstance(name, str) or not name:
        raise ClaimError(f"not a usable path: {name!r}")
    if "\x00" in name:
        raise ClaimError("a path may not contain NUL")
    if os.path.isabs(name) or name.startswith("~"):
        raise ClaimError(f"path escapes the claim (not relative): {name}")
    base = os.path.realpath(claimdir)
    walked = base
    for part in name.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            raise ClaimError(f"a path may not contain '..': {name}")
        walked = os.path.join(walked, part)
        if os.path.islink(walked):
            raise ClaimError(f"a path component is a symlink: {name} ({part})")
    resolved = os.path.realpath(os.path.join(base, name))
    if resolved == base:
        raise ClaimError(f"path is the claim directory itself: {name}")
    if not resolved.startswith(base + os.sep):
        raise ClaimError(f"path escapes the claim directory: {name}")
    return resolved


def _hash_file(path: str) -> str:
    """THE BYTES BOUNDARY.  sha256 of a file that lives inside the claim.

    A declared file must be a REGULAR file with a SINGLE link, so its bytes are
    the claim's own.  A hardlink to an outside inode keeps a local-looking name
    yet seals foreign bytes; a FIFO or device would block or feed nonsense into
    the claim; a directory is not a file.  All are refused here.
    """
    try:
        st = os.lstat(path)
    except OSError as exc:
        raise ClaimError(f"declared file is unreadable: {path} ({exc.strerror})") from None
    if stat.S_ISLNK(st.st_mode):
        raise ClaimError(f"declared file is a symlink: {path}")
    if stat.S_ISDIR(st.st_mode):
        raise ClaimError(f"declared file is a directory: {path}")
    if not stat.S_ISREG(st.st_mode):
        raise ClaimError(f"declared file is not a regular file: {path}")
    if st.st_nlink != 1:
        raise ClaimError(f"declared file has {st.st_nlink} links, so its bytes "
                         f"live outside the claim too: {path}")
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ClaimError(f"declared file is unreadable: {path} ({exc})") from None
    return digest.hexdigest()


def _copy_into(src: str, dst: str) -> None:
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    try:
        shutil.copyfile(src, dst)
        # Carry the permission bits: a generated output may legitimately BE an
        # executable (a compiled binary), and copyfile drops the exec bit, so a
        # gate that runs its own output would fail with "Permission denied" the
        # moment the claim is materialized anywhere. Only the low 9 bits travel
        # -- setuid, setgid and sticky are deliberately not carried into a
        # workspace the kernel just created.
        os.chmod(dst, stat.S_IMODE(os.stat(src).st_mode) & 0o777)
    except (OSError, shutil.Error) as exc:
        raise ClaimError(f"cannot materialize {dst}: {exc}") from None


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


# ------------------------------------------------------- identity and digest

def _claim_format(recipe) -> int:
    fmt = (recipe.get("claim") or {}).get("format", 1)
    return fmt if isinstance(fmt, int) and not isinstance(fmt, bool) else 1


def _preimage_recipe(recipe):
    """The recipe as it enters the root preimage.  Format 3+ removes producer
    guidance from every step; formats 1 and 2 pass the recipe through whole,
    so their roots never move.  The transform is defined identically in the
    reference implementation, or the two would disagree at format 3."""
    if _claim_format(recipe) < 3:
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
    """
    recipe = load_recipe(claimdir)
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
        own.append([output, _hash_file(path)])
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


# -------------------------------------------------------- manifest and seal

def read_manifest(claimdir: str) -> dict:
    """The sealed manifest, or a refusal.  Damaged residue is never data."""
    path = os.path.join(claimdir, MANIFEST)
    if not os.path.isfile(path):
        raise ClaimError(f"no manifest at {path}: the claim is not sealed")
    try:
        with open(path, "rb") as f:
            manifest = json.loads(f.read().decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise ClaimError(f"damaged manifest {path}: {exc}") from None
    if not isinstance(manifest, dict):
        raise ClaimError(f"damaged manifest {path}: not an object")
    if not isinstance(manifest.get("name"), str):
        raise ClaimError(f"damaged manifest {path}: name is not a string")
    stored = manifest.get("root")
    if stored is not None and not isinstance(stored, str):
        raise ClaimError(f"damaged manifest {path}: root is not a string")
    return manifest


def seal(claimdir: str) -> dict:
    """Freeze the claim's identity onto its manifest.

    Sealing computes the root and records it.  It does not run gates: the
    verdicts belong to `audit`, which earns them, and a seal that re-ran the
    gates in place would overwrite the very pinned bytes it is meant to fix.
    """
    recipe = load_recipe(claimdir)
    parts = _parts(recipe, claimdir)
    computed = hashlib.sha256(
        json.dumps(parts, sort_keys=True).encode("utf-8")).hexdigest()
    manifest = {}
    if os.path.isfile(os.path.join(claimdir, MANIFEST)):
        try:
            manifest = read_manifest(claimdir)
        except ClaimError:
            manifest = {}                 # a wreck is replaced, not trusted
    manifest.update({
        "name": recipe["claim"]["name"],
        "digest": DIGEST,
        "root": computed,
        "sealed": _now(),
    })
    _write_json(os.path.join(claimdir, MANIFEST), manifest)
    # RESIDUE, never identity: the preimage parts, so a later broken verify
    # can NAME which pinned file moved instead of shrugging two hex strings.
    # Untrusted on read -- verify uses it only after re-deriving the sealed
    # root from it, so a stale or tampered copy is ignored, not believed.
    _write_json(os.path.join(claimdir, STORE, "parts.json"), parts)
    return manifest


def verify(claimdir: str) -> dict:
    """Does the claim still hash to what was sealed?

    This is the shallow check -- identity, not verdict.  `root` is the sealed
    identity, `recomputed` is what the bytes on disk say now.  A generated
    rebuild keeps them equal; an edited input moves them apart.
    """
    recipe = load_recipe(claimdir)
    manifest = read_manifest(claimdir)
    now_parts = _parts(recipe, claimdir)
    recomputed = hashlib.sha256(
        json.dumps(now_parts, sort_keys=True).encode("utf-8")).hexdigest()
    stored = manifest.get("root")
    out = {
        "ok": isinstance(stored, str) and stored == recomputed,
        "root": stored,
        "recomputed": recomputed,
        "name": manifest.get("name"),
        "claim": os.path.abspath(claimdir),
    }
    if not out["ok"]:
        out["changed"] = _changed_parts(claimdir, stored, now_parts)
    return out


def _changed_parts(claimdir: str, sealed_root, now_parts: dict) -> list | None:
    """Which preimage parts moved, by name -- or None when it cannot be said.

    The parts residue written at seal time is UNTRUSTED: it is used only if
    hashing it reproduces the sealed root exactly, so a stale or edited copy
    names nothing. With a valid copy, the diff of sealed parts against the
    parts recomputed now is precisely the set of moved criteria."""
    try:
        with open(os.path.join(claimdir, STORE, "parts.json"),
                  encoding="utf-8") as f:
            sealed = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(sealed, dict):
        return None
    derived = hashlib.sha256(
        json.dumps(sealed, sort_keys=True).encode("utf-8")).hexdigest()
    if derived != sealed_root:
        return None                       # stale or tampered: name nothing
    moved = sorted(set(sealed) ^ set(now_parts)
                   | {k for k in set(sealed) & set(now_parts)
                      if sealed[k] != now_parts[k]})
    names = []
    for key in moved:
        if key == "recipe":
            names.append("reticuli.toml (the recipe)")
        elif key.startswith(("input:", "pinned:")):
            names.append(key.split(":", 1)[1])
        else:
            names.append(key)
    return sorted(names)
