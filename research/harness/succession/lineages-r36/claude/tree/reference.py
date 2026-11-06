"""A second, independent implementation of spec/identity.md.

Deliberately standalone: it imports nothing from this package, reads the
specification rather than the kernel, and exists so that every conformance
vector has TWO answers that must agree. One implementation computing a root
proves the serialization is computable; two agreeing prove it is specified.

    python3 -m reticuli.reference root   <claim directory>
    python3 -m reticuli.reference digest <claim directory>

Stdlib only. Prints one lowercase-hex digest and nothing else.
"""
import hashlib
import json
import os
import stat
import sys
import tomllib

ALGORITHM = "sha256"
NEWEST_FORMAT = 6
NAMES = ("reticuli.toml", "claim.toml")
GUIDANCE = ("guidance", "request")


class Refused(Exception):
    """This document does not name a claim."""


def _canonical(value) -> str:
    """json.dumps(x, sort_keys=True) with every other argument at default:
    sorted keys, a space after every colon and comma, non-ASCII escaped,
    integers in exact decimal, floats as CPython's repr."""
    return json.dumps(value, sort_keys=True)


def _resolve(claim: str, declared: str) -> str:
    if not isinstance(declared, str) or not declared or \
            os.path.isabs(declared):
        raise Refused(f"declared path is absolute or empty: {declared!r}")
    pieces = declared.replace("\\", "/").split("/")
    if any(piece == ".." for piece in pieces):
        raise Refused(f"declared path climbs out: {declared!r}")
    base = os.path.realpath(claim)
    walk = base
    for piece in pieces:
        if piece in ("", "."):
            continue
        walk = os.path.join(walk, piece)
        if os.path.islink(walk):
            raise Refused(f"declared path has a symlink component: "
                          f"{declared!r}")
    final = os.path.normpath(walk)
    if final != base and not final.startswith(base + os.sep):
        raise Refused(f"declared path escapes the claim: {declared!r}")
    return final


def _digest_file(path: str) -> str:
    info = os.lstat(path)
    if not stat.S_ISREG(info.st_mode):
        raise Refused(f"not a regular file: {path}")
    if info.st_nlink != 1:
        raise Refused(f"not a single-link file: {path}")
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def _recipe_file(claim: str) -> str:
    for name in NAMES:
        candidate = os.path.join(claim, name)
        if os.path.isfile(candidate):
            return candidate
    raise Refused(f"no recipe in {claim}")


def _load(claim: str) -> dict:
    with open(_recipe_file(claim), "rb") as handle:
        return tomllib.load(handle)


def _format(parsed: dict) -> int:
    declared = (parsed.get("claim") or {}).get("format")
    if declared is None:
        return 1
    if isinstance(declared, bool) or not isinstance(declared, int) \
            or declared < 1:
        raise Refused(f"[claim] format is not a positive integer: "
                      f"{declared!r}")
    if declared > NEWEST_FORMAT:
        raise Refused(f"claim format {declared} is newer than this reader "
                      f"understands (format {NEWEST_FORMAT})")
    return declared


def _klass(step: dict) -> str:
    declared = step.get("class")
    if isinstance(declared, str) and declared:
        return declared
    return "generated" if step.get("kind") == "produce" else "pinned"


def _manifest_paths(claim: str, listing: str) -> list:
    found = []
    with open(_resolve(claim, listing), encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            fields = line.split()
            found.append(fields[-1] if len(fields) > 1 else fields[0])
    return found


def _pinned_inputs(parsed: dict, claim: str) -> list:
    """The union spec/identity.md names: the declared list, the environment
    file, and -- from format 2 -- the manifest plus every path it lists."""
    table = parsed.get("claim") or {}
    paths = list(table.get("inputs") or [])
    if table.get("environment"):
        paths.append(table["environment"])
    listing = table.get("inputs_manifest")
    if listing and _format(parsed) >= 2:
        paths.append(listing)
        paths.extend(_manifest_paths(claim, listing))
    ordered, seen = [], set()
    for path in paths:
        if path not in seen:
            seen.add(path)
            ordered.append(path)
    return ordered


def _preimage(parsed: dict) -> dict:
    fmt = _format(parsed)
    if fmt < 3:
        return parsed
    lean = dict(parsed)
    steps = [{k: v for k, v in step.items() if k not in GUIDANCE}
             for step in parsed.get("step") or []]
    if fmt in (4, 5):
        steps = sorted(steps, key=_canonical)
    if "step" in lean:
        lean["step"] = steps
    return lean


def root(claim: str) -> str:
    """The claim's identity."""
    parsed = _load(claim)
    parts = {"digest": ALGORITHM, "recipe": _canonical(_preimage(parsed))}
    for path in _pinned_inputs(parsed, claim):
        parts["input:" + path] = _digest_file(_resolve(claim, path))
    for step in parsed.get("step") or []:
        if not step.get("output") or _klass(step) == "generated":
            continue
        parts["pinned:" + step["output"]] = \
            _digest_file(_resolve(claim, step["output"]))
    return hashlib.sha256(_canonical(parts).encode("utf-8")).hexdigest()


def build_digest(claim: str) -> str:
    """The digest a signature binds: the generated bytes present."""
    parsed = _load(claim)
    fmt = _format(parsed)
    own = []
    for step in parsed.get("step") or []:
        if step.get("kind") != "produce" or step.get("from") is not None:
            continue
        if _klass(step) != "generated":
            continue
        path = _resolve(claim, step["output"])
        if not os.path.isfile(path):
            continue
        entry = [step["output"], _digest_file(path)]
        if fmt >= 6:
            entry.append("x" if os.stat(path).st_mode & 0o100 else "-")
        own.append(entry)
    return hashlib.sha256(
        _canonical(sorted(own)).encode("utf-8")).hexdigest()


def main(argv: list | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 2 or argv[0] not in ("root", "digest"):
        print("usage: python3 -m reticuli.reference root|digest <claim>",
              file=sys.stderr)
        return 2
    try:
        answer = root(argv[1]) if argv[0] == "root" else build_digest(argv[1])
    except (Refused, OSError, tomllib.TOMLDecodeError) as exc:
        print(f"reference: {exc}", file=sys.stderr)
        return 1
    print(answer)
    return 0


if __name__ == "__main__":
    sys.exit(main())
