"""An independent reference implementation of the identity computation
(spec/identity.md), used to cross-check `reticuli.kernel` against
`spec/vectors/`: two implementations, one answer. Deliberately does not
import anything from `reticuli._kernel` -- it re-derives the root and the
build digest from the recipe and the claim directory's bytes alone, so the
two implementations have nothing in common but the spec.

    python3 -m reticuli.reference root <claim-dir>
    python3 -m reticuli.reference build_digest <claim-dir>

Stdlib only.
"""
import copy
import hashlib
import json
import os
import stat
import sys
import tomllib

RECIPE = "reticuli.toml"
LEGACY_RECIPE = "claim.toml"
DIGEST_ALGO = "sha256"
KINDS = ("produce", "gate")
GUIDANCE_KEYS = ("guidance", "request")


class ClaimError(Exception):
    """A refusal with a reason -- the claim's own recipe is untrusted input."""


# -- The path and bytes boundaries (spec/identity.md, "File hashing rules") --


def _safe_path(base: str, name: str) -> str:
    """Resolve a claim-declared name under `base`, or refuse it: absolute or
    empty, any `..`/empty component, or any component that is a symlink.
    """
    if not isinstance(name, str) or name == "":
        raise ClaimError("a claim path must be a non-empty string")
    if os.path.isabs(name):
        raise ClaimError(f"a claim path must not be absolute: {name!r}")

    parts = name.split("/")
    for part in parts:
        if part in ("", ".", ".."):
            raise ClaimError(f"unsafe path component {part!r} in {name!r}")

    base_real = os.path.realpath(base)
    probe = base_real
    for part in parts:
        probe = os.path.join(probe, part)
        if os.path.islink(probe):
            raise ClaimError(f"a claim path must not cross a symlink: {name!r}")

    candidate = os.path.join(base_real, *parts)
    real = os.path.realpath(candidate)
    if real != candidate or not (
        real == base_real or real.startswith(base_real + os.sep)
    ):
        raise ClaimError(f"path escapes the claim: {name!r}")
    return real


def _hash_file(path: str) -> str:
    """sha256 of a regular, single-hard-linked file's bytes; anything else
    (FIFO, device, socket, a hard link to an outside inode) is refused.
    """
    st = os.lstat(path)
    if not stat.S_ISREG(st.st_mode):
        raise ClaimError(f"not a regular file: {path!r}")
    if st.st_nlink != 1:
        raise ClaimError(f"refusing a hard-linked file: {path!r}")
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


# -- Canonical JSON (spec/identity.md, "Computation") -------------------------


def _canonical_json(obj) -> str:
    """Sorted keys, default separators, ASCII-escaped, exact-decimal
    integers, CPython float repr -- exactly `json.dumps(obj, sort_keys=True)`.
    """
    return json.dumps(obj, sort_keys=True)


# -- Recipe parsing (spec/claim-format.md) -------------------------------------


def _recipe_path(d: str) -> str:
    primary = os.path.join(d, RECIPE)
    if os.path.isfile(primary):
        return primary
    legacy = os.path.join(d, LEGACY_RECIPE)
    if os.path.isfile(legacy):
        return legacy
    raise ClaimError(f"no recipe ({RECIPE} or {LEGACY_RECIPE}) found in {d!r}")


def _read_inputs_manifest(d: str, path: str) -> list:
    full = _safe_path(d, path)
    try:
        with open(full, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError as exc:
        raise ClaimError(f"cannot read inputs manifest {path!r}: {exc}") from exc

    names = []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if (
            len(parts) == 2
            and len(parts[0]) == 64
            and all(c in "0123456789abcdef" for c in parts[0])
        ):
            names.append(parts[1].strip())
        else:
            names.append(line)
    return names


def load_recipe(d: str) -> dict:
    """Parse and validate the recipe under `d`; refuses, with a reason, any
    bytes that are not a well-formed claim recipe.
    """
    path = _recipe_path(d)
    try:
        with open(path, "rb") as f:
            doc = tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        raise ClaimError(f"malformed recipe {path!r}: {exc}") from exc
    except OSError as exc:
        raise ClaimError(f"cannot read recipe {path!r}: {exc}") from exc

    if not isinstance(doc, dict):
        raise ClaimError(f"malformed recipe {path!r}: not a table")

    claim = doc.get("claim", doc.get("record"))
    if not isinstance(claim, dict):
        raise ClaimError(f"recipe {path!r} needs a [claim] table")
    doc["claim"] = claim

    name = claim.get("name")
    if not isinstance(name, str):
        raise ClaimError("[claim] name is required and must be a string")

    fmt = claim.get("format", 1)
    if isinstance(fmt, bool) or not isinstance(fmt, int) or fmt < 1:
        raise ClaimError("[claim] format must be a positive integer")

    steps = doc.get("step", [])
    if not isinstance(steps, list):
        raise ClaimError(f"recipe {path!r}: [[step]] must be an array of tables")
    for step in steps:
        if not isinstance(step, dict):
            raise ClaimError("each step must be a table")
        kind = step.get("kind")
        if kind not in KINDS:
            raise ClaimError(f"step kind must be one of {sorted(KINDS)}: {kind!r}")
        output = step.get("output")
        if not isinstance(output, str) or output == "":
            raise ClaimError("every step needs a non-empty string output")
        if kind == "gate" and not isinstance(step.get("run"), str):
            raise ClaimError(f"gate step {output!r} needs a run command")
        _safe_path(d, output)

    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        if not isinstance(manifest, str):
            raise ClaimError("[claim] inputs_manifest must be a string")
        names = _read_inputs_manifest(d, manifest)
        for n in names:
            _safe_path(d, n)
        doc["_manifest_inputs"] = names
    else:
        inputs = claim.get("inputs", [])
        if not isinstance(inputs, list) or not all(isinstance(i, str) for i in inputs):
            raise ClaimError("[claim] inputs must be a list of strings")
        for n in inputs:
            _safe_path(d, n)

    return doc


def _inputs(doc: dict) -> list:
    """The claim's declared pinned inputs, in root-preimage order: the
    manifest file itself first, then every path it lists -- or, with no
    manifest, the recipe's own `inputs` list.
    """
    claim = doc.get("claim", {})
    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        return [manifest] + list(doc.get("_manifest_inputs", []))
    return list(claim.get("inputs", []))


# -- The identity computation (spec/identity.md) -------------------------------


def _preimage_recipe(doc: dict) -> dict:
    """The recipe as it enters the root preimage: parser bookkeeping
    stripped, and, at format >= 3, every step's producer guidance
    (`guidance` / `request`) stripped too.
    """
    fmt = doc.get("claim", {}).get("format", 1)
    pr = copy.deepcopy(doc)
    pr.pop("_manifest_inputs", None)
    if fmt >= 3:
        for step in pr.get("step", []):
            for key in GUIDANCE_KEYS:
                step.pop(key, None)
    return pr


def _parts(doc: dict, d: str) -> dict:
    parts = {
        "digest": DIGEST_ALGO,
        "recipe": _canonical_json(_preimage_recipe(doc)),
    }

    for path in _inputs(doc):
        parts["input:" + path] = _hash_file(_safe_path(d, path))

    for step in doc.get("step", []):
        default_class = "generated" if step.get("kind") == "produce" else "pinned"
        if step.get("class", default_class) == "generated":
            continue
        output = step["output"]
        parts["pinned:" + output] = _hash_file(_safe_path(d, output))

    return parts


def root(d: str) -> str:
    """The claim's identity: `sha256(canonical_json(parts))`."""
    doc = load_recipe(d)
    blob = _canonical_json(_parts(doc, d)).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def build_digest(d: str) -> str:
    """The digest a signature binds to: sha256 over the generated bytes
    actually present. A `produce` step with a `from` source is excluded; an
    absent generated output is omitted; no generated outputs hashes the
    empty list.
    """
    doc = load_recipe(d)
    entries = []
    for step in doc.get("step", []):
        if step.get("kind") != "produce":
            continue
        if step.get("class", "generated") != "generated":
            continue
        if "from" in step:
            continue
        output = step["output"]
        path = _safe_path(d, output)
        if not os.path.isfile(path):
            continue
        entries.append([output, _hash_file(path)])
    entries.sort(key=lambda e: e[0])
    blob = _canonical_json(entries).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


# -- CLI (spec/vectors/run.py conformance runner) ------------------------------


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2 or argv[0] not in ("root", "build_digest"):
        print(
            "usage: python3 -m reticuli.reference {root|build_digest} <claim-dir>",
            file=sys.stderr,
        )
        return 2

    verb, d = argv
    try:
        print(root(d) if verb == "root" else build_digest(d))
    except ClaimError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
