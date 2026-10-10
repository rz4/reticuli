"""reticuli.reference: a second, independent implementation of the identity
computation (spec/identity.md), used as the cross-check the kernel's root
and build-digest computations must agree with, and as a CLI any
conformance vector runner can point at (spec/vectors/run.py).

    python3 -m reticuli.reference root <claim-dir>
    python3 -m reticuli.reference digest <claim-dir>

Stdlib only.
"""
import hashlib
import json
import os
import sys
import tomllib

RECIPE = "reticuli.toml"
LEGACY_RECIPE = "claim.toml"
GUIDANCE_KEYS = ("guidance", "request")


class ReferenceError(Exception):
    """A refusal with a reason."""


def _hash_file(path: str) -> str:
    """sha256 of a regular file's bytes; refuses anything else
    (spec/identity.md: file hashing rules)."""
    st = os.lstat(path)
    if os.path.islink(path) or not os.path.isfile(path):
        raise ReferenceError(f"not a regular file: {path}")
    if st.st_nlink != 1:
        raise ReferenceError(f"refused: {path} has more than one hard link")
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe(d: str, name: str) -> str:
    """A recipe-declared path resolved under the claim, refusing an
    absolute path, an empty name, a `.`/`..` component, or any symlink
    component (spec/identity.md)."""
    if not isinstance(name, str) or name == "" or os.path.isabs(name):
        raise ReferenceError(f"refused path: {name!r}")
    parts = name.split("/")
    if any(p in ("", ".", "..") for p in parts):
        raise ReferenceError(f"refused path: {name!r}")

    base = os.path.realpath(d)
    cur = base
    for part in parts:
        cur = os.path.join(cur, part)
        if os.path.islink(cur):
            raise ReferenceError(f"refused symlink component: {name!r}")

    resolved = os.path.realpath(os.path.join(base, name))
    if resolved != base and not resolved.startswith(base + os.sep):
        raise ReferenceError(f"refused path escaping claim: {name!r}")
    return resolved


def recipe_path(d: str) -> str:
    """The on-disk path of `d`'s recipe, preferring the canonical name."""
    for name in (RECIPE, LEGACY_RECIPE):
        p = os.path.join(d, name)
        if os.path.isfile(p):
            return p
    raise ReferenceError(f"no recipe found in {d!r} ({RECIPE} or {LEGACY_RECIPE})")


def load_recipe(d: str) -> dict:
    path = recipe_path(d)
    with open(path, "rb") as f:
        raw = f.read()
    try:
        parsed = tomllib.loads(raw.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
        raise ReferenceError(f"malformed recipe {path!r}: {e}") from e
    if not isinstance(parsed, dict) or not isinstance(parsed.get("claim"), dict):
        raise ReferenceError("malformed recipe: missing [claim] table")
    return parsed


def _claim_format(parsed: dict) -> int:
    """The claim's declared format; absent means 1 (spec/claim-format.md)."""
    return parsed.get("claim", {}).get("format", 1)


def _effective_class(step: dict) -> str:
    """A `produce` step defaults to `generated`; any other step output
    defaults to `pinned` (spec/claim-format.md)."""
    cls = step.get("class")
    if cls is not None:
        return cls
    return "generated" if step.get("kind") == "produce" else "pinned"


def _strip_guidance(step: dict) -> dict:
    return {k: v for k, v in step.items() if k not in GUIDANCE_KEYS}


def _canonical_json(obj) -> str:
    """`json.dumps(obj, sort_keys=True)` with every other argument at its
    default (spec/identity.md): sorted keys, default separators, ASCII
    escaping, arbitrary-precision integers, shortest-round-trip floats. A
    TOML date/time value has no canonical form and is refused."""
    def _refuse(o):
        raise ReferenceError(
            f"refused: a {type(o).__name__} value has no canonical form "
            "and cannot enter a preimage (TOML date/time values are refused)"
        )
    return json.dumps(obj, sort_keys=True, default=_refuse)


def _preimage_recipe(parsed: dict) -> dict:
    """The recipe exactly as it enters the root preimage (spec/identity.md).

    Format < 3: the parsed recipe unchanged. Format >= 3: every step's
    guidance keys stripped. Format >= 4: the guidance-stripped step list
    additionally sorted by each step's own canonical JSON encoding, so
    file order cannot move the root.
    """
    fmt = _claim_format(parsed)
    if fmt < 3:
        return parsed
    steps = [_strip_guidance(s) for s in parsed.get("step", [])]
    if fmt >= 4:
        steps.sort(key=_canonical_json)
    out = dict(parsed)
    out["step"] = steps
    return out


def _read_input_manifest(path: str) -> list:
    """Format-2 `inputs_manifest`: one path per line, optionally prefixed
    `<sha256>  <path>`; blank lines and `#` comments ignored."""
    paths = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            head, _, tail = line.partition(" ")
            if len(head) == 64 and tail.strip() and all(c in "0123456789abcdef" for c in head):
                paths.append(tail.strip())
            else:
                paths.append(line)
    return paths


def _inputs(d: str, parsed: dict) -> list:
    """Every pinned input path the recipe declares: `inputs`, the
    `inputs_manifest` file plus the paths it names, and the `environment`
    file (spec/claim-format.md)."""
    claim = parsed.get("claim", {})
    paths = list(claim.get("inputs", []) or [])
    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        paths.append(manifest)
        paths.extend(_read_input_manifest(_safe(d, manifest)))
    environment = claim.get("environment")
    if environment is not None:
        paths.append(environment)
    return paths


def _parts(parsed: dict, d: str) -> dict:
    """The string-to-string map the root hashes (spec/identity.md)."""
    parts = {
        "digest": "sha256",
        "recipe": _canonical_json(_preimage_recipe(parsed)),
    }
    for path in _inputs(d, parsed):
        parts["input:" + path] = _hash_file(_safe(d, path))
    for step in parsed.get("step", []):
        if _effective_class(step) != "generated":
            parts["pinned:" + step["output"]] = _hash_file(_safe(d, step["output"]))
    return parts


def root(d: str) -> str:
    """The claim's identity (spec/identity.md)."""
    parsed = load_recipe(d)
    preimage = _canonical_json(_parts(parsed, d)).encode("ascii")
    return hashlib.sha256(preimage).hexdigest()


def build_digest(d: str) -> str:
    """The digest a signature binds: sha256 over the generated outputs
    present on disk, excluding any `from`-attributed output; the digest
    of the empty list when none exist (spec/identity.md)."""
    parsed = load_recipe(d)
    pairs = []
    for step in parsed.get("step", []):
        if _effective_class(step) != "generated" or step.get("from") is not None:
            continue
        path = _safe(d, step["output"])
        if os.path.isfile(path):
            pairs.append([step["output"], _hash_file(path)])
    pairs.sort()
    preimage = _canonical_json(pairs).encode("ascii")
    return hashlib.sha256(preimage).hexdigest()


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2 or argv[0] not in ("root", "digest"):
        print("usage: python3 -m reticuli.reference {root|digest} <claim-dir>",
              file=sys.stderr)
        return 2
    cmd, d = argv
    try:
        print(root(d) if cmd == "root" else build_digest(d))
    except ReferenceError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
