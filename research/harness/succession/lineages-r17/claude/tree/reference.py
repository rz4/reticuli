"""Independent reference implementation of the identity computation.

Computes a claim's root (`spec/identity.md`) and build digest straight from
its recipe file and the bytes on disk -- no import from `reticuli.kernel` or
any of its submodules. This is the second of the two implementations the
conformance vectors (`spec/vectors/`) must agree on.

    python3 -m reticuli.reference root <claim-dir>
    python3 -m reticuli.reference digest <claim-dir>

Stdlib only.
"""
import hashlib
import json
import os
import re
import sys
import tomllib

RECIPE = "reticuli.toml"
LEGACY_RECIPE = "claim.toml"
DIGEST = "sha256"
GUIDANCE_KEYS = ("guidance", "request")

_HEXLINE = re.compile(r"^[0-9a-f]{64}\s+(\S.*)$")


def _recipe_path(d: str) -> str:
    """The on-disk path of `d`'s recipe, preferring the canonical name."""
    for name in (RECIPE, LEGACY_RECIPE):
        path = os.path.join(d, name)
        if os.path.isfile(path):
            return path
    raise ValueError(f"no recipe found: expected {RECIPE} (or legacy "
                      f"{LEGACY_RECIPE}) in {d!r}")


def _safe(base: str, name: str) -> str:
    """Resolve `name` as a path inside `base`; refuse any escape or
    symlink component (`spec/identity.md`'s file hashing rules)."""
    if not name:
        raise ValueError("empty path refused")
    if os.path.isabs(name):
        raise ValueError(f"absolute path refused: {name!r}")
    parts = name.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError(f"path escapes the claim: {name!r}")

    base_real = os.path.realpath(base)
    cur = base_real
    for part in parts:
        cur = os.path.join(cur, part)
        if os.path.islink(cur):
            raise ValueError(f"symlink component refused: {name!r}")

    resolved = os.path.realpath(cur)
    if resolved != base_real and not resolved.startswith(base_real + os.sep):
        raise ValueError(f"path escapes the claim: {name!r}")
    return resolved


def load_recipe(d: str) -> dict:
    """Parse `d`'s recipe (the untrusted-input validation lives in the
    kernel; this reference trusts the vectors it is run against)."""
    with open(_recipe_path(d), "rb") as f:
        return tomllib.load(f)


def _hash_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _canonical_json(obj) -> str:
    """Sorted keys, default (non-compact) separators, ASCII-escaped --
    `json.dumps(obj, sort_keys=True)` with every other argument default."""
    return json.dumps(obj, sort_keys=True)


def _claim_format(parsed: dict) -> int:
    """The claim's declared format; absent means 1."""
    return parsed.get("claim", {}).get("format", 1)


def _steps(parsed: dict) -> list:
    return list(parsed.get("step", []))


def _default_class(step: dict) -> str:
    """A `produce` step defaults to `generated`; anything else to `pinned`."""
    return "generated" if step.get("kind") == "produce" else "pinned"


def _preimage_recipe(parsed: dict) -> dict:
    """The recipe as it enters the root preimage, per the claim's format.

    Format 1/2 serialize the parsed recipe untouched. Format 3 strips every
    step's `guidance`/`request` key. Format 4 additionally sorts the step
    list by each step's own canonical JSON encoding.
    """
    fmt = _claim_format(parsed)
    if fmt < 3 or "step" not in parsed:
        return parsed
    steps = [{k: v for k, v in step.items() if k not in GUIDANCE_KEYS}
             for step in parsed["step"]]
    if fmt >= 4:
        steps = sorted(steps, key=lambda s: json.dumps(s, sort_keys=True))
    result = dict(parsed)
    result["step"] = steps
    return result


def _read_input_manifest(path: str) -> list:
    """One entry per line, optionally `<sha256>  <path>`; blank/`#` ignored."""
    paths = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = _HEXLINE.match(line)
            paths.append(m.group(1) if m else line)
    return paths


def _inputs(d: str, parsed: dict) -> list:
    """The claim's pinned input paths, from `inputs` or `inputs_manifest`."""
    claim = parsed.get("claim", {})
    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        return [manifest] + _read_input_manifest(_safe(d, manifest))
    return list(claim.get("inputs", []))


def _parts(parsed: dict, d: str) -> dict:
    """The string-to-string map the root digests (`spec/identity.md`)."""
    parts = {
        "digest": DIGEST,
        "recipe": _canonical_json(_preimage_recipe(parsed)),
    }
    for path in _inputs(d, parsed):
        parts[f"input:{path}"] = _hash_file(_safe(d, path))
    for step in _steps(parsed):
        cls = step.get("class", _default_class(step))
        if cls != "generated":
            output = step["output"]
            parts[f"pinned:{output}"] = _hash_file(_safe(d, output))
    return parts


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def root(d: str) -> str:
    """The claim's identity: sha256 of the canonical `parts` map."""
    parsed = load_recipe(d)
    return _sha256_text(_canonical_json(_parts(parsed, d)))


def build_digest(d: str) -> str:
    """Digest over concrete bytes, generated outputs included: every
    `produce` step whose class is `generated`, with no `from`, and whose
    output exists, contributes `[output, sha256(bytes)]`; sorted by output
    path and hashed canonically. No qualifying output yields the empty list.
    """
    parsed = load_recipe(d)
    pairs = []
    for step in _steps(parsed):
        if step.get("kind") != "produce":
            continue
        if step.get("from") is not None:
            continue
        if step.get("class", _default_class(step)) != "generated":
            continue
        output = step["output"]
        path = _safe(d, output)
        if not os.path.isfile(path):
            continue
        pairs.append([output, _hash_file(path)])
    pairs.sort(key=lambda pair: pair[0])
    return _sha256_text(_canonical_json(pairs))


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2 or argv[0] not in ("root", "digest"):
        print("usage: python3 -m reticuli.reference {root|digest} <claim-dir>",
              file=sys.stderr)
        return 2
    cmd, d = argv
    try:
        value = root(d) if cmd == "root" else build_digest(d)
    except (ValueError, OSError, tomllib.TOMLDecodeError) as e:
        print(str(e), file=sys.stderr)
        return 1
    print(value)
    return 0


if __name__ == "__main__":
    sys.exit(main())
