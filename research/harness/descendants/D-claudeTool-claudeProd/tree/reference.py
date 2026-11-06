"""The reference identity implementation -- the second, independent one.

`spec/identity.md` is a specification, and a specification with one
implementation is a description of that implementation. This module computes
the root and the build digest from the document alone, sharing no code with
`reticuli.kernel`, so the two must AGREE for a vector to pass; where they
diverge, the specification is what settles it.

    python3 -m reticuli.reference root   <claim>
    python3 -m reticuli.reference digest <claim>

Deliberately standalone: it reads TOML, hashes files, and serializes. It
imports nothing from the rest of this package.
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
HINTS = ("guidance", "request")


class ReferenceError(Exception):
    """A refusal with a reason."""


def _recipe_file(claim):
    for name in NAMES:
        candidate = os.path.join(claim, name)
        if os.path.isfile(candidate):
            return candidate
    raise ReferenceError(f"no recipe in {claim}")


def _read(claim):
    with open(_recipe_file(claim), "rb") as handle:
        return tomllib.load(handle)


def _confine(claim, declared):
    """Absolute, empty, `..`, or a symlink component: all refused."""
    if not isinstance(declared, str) or not declared or \
            os.path.isabs(declared):
        raise ReferenceError(f"declared path refused: {declared!r}")
    parts = [p for p in declared.replace("\\", "/").split("/")
             if p not in ("", ".")]
    if not parts or ".." in parts:
        raise ReferenceError(f"declared path refused: {declared!r}")
    base = os.path.realpath(claim)
    here = base
    for part in parts:
        here = os.path.join(here, part)
        if os.path.islink(here):
            raise ReferenceError(f"declared path is a symlink: {declared!r}")
    return here


def _hash(path):
    info = os.lstat(path)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ReferenceError(f"not a plain self-contained file: {path}")
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def _format(document):
    declared = (document.get("claim") or {}).get("format")
    if declared is None:
        return 1
    if isinstance(declared, bool) or not isinstance(declared, int):
        raise ReferenceError("[claim] format must be an integer")
    if declared > NEWEST_FORMAT:
        raise ReferenceError(
            f"claim format {declared} is newer than this implementation "
            f"understands (format {NEWEST_FORMAT})")
    return declared


def _steps(document):
    listed = document.get("step") or []
    return [s for s in listed if isinstance(s, dict)]


def _step_class(step):
    declared = step.get("class")
    if isinstance(declared, str) and declared:
        return declared
    return "generated" if step.get("kind") == "produce" else "pinned"


def _manifest_entries(claim, name):
    with open(_confine(claim, name), encoding="utf-8") as handle:
        text = handle.read()
    listed = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        listed.append(fields[-1] if len(fields) > 1 else fields[0])
    return listed


def _pinned_inputs(claim, document):
    """Wider than `[claim] inputs`: the environment file and the manifest."""
    table = document.get("claim") or {}
    paths = list(table.get("inputs") or [])
    if table.get("environment"):
        paths.append(table["environment"])
    if table.get("inputs_manifest") and _format(document) >= 2:
        paths.append(table["inputs_manifest"])
        paths.extend(_manifest_entries(claim, table["inputs_manifest"]))
    ordered = []
    for path in paths:
        if path not in ordered:
            ordered.append(path)
    return ordered


def _no_temporal(value):
    import datetime
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        raise ReferenceError("a TOML date or time cannot enter a preimage")
    if isinstance(value, dict):
        for item in value.values():
            _no_temporal(item)
    elif isinstance(value, list):
        for item in value:
            _no_temporal(item)


def preimage_recipe(document):
    """The recipe as the root names it: guidance stripped, order per format."""
    fmt = _format(document)
    copy = _plain_copy(document)
    if fmt < 3:
        return copy
    steps = copy.get("step")
    if isinstance(steps, list):
        stripped = [{k: v for k, v in s.items() if k not in HINTS}
                    if isinstance(s, dict) else s for s in steps]
        if 4 <= fmt <= 5:
            stripped.sort(key=lambda s: json.dumps(s, sort_keys=True))
        copy["step"] = stripped
    return copy


def _plain_copy(value):
    if isinstance(value, dict):
        return {k: _plain_copy(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain_copy(v) for v in value]
    return value


def parts(claim):
    """The string-to-string map whose canonical JSON the root hashes."""
    document = _read(claim)
    _no_temporal(document)
    _format(document)
    table = {"digest": ALGORITHM,
             "recipe": json.dumps(preimage_recipe(document), sort_keys=True)}
    for declared in _pinned_inputs(claim, document):
        table["input:" + declared] = _hash(_confine(claim, declared))
    for step in _steps(document):
        if _step_class(step) == "generated":
            continue
        output = step.get("output")
        if output:
            table["pinned:" + output] = _hash(_confine(claim, output))
    return table


def root(claim):
    """The claim's identity."""
    payload = json.dumps(parts(claim), sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_digest(claim):
    """The concrete generated bytes a signature froze."""
    document = _read(claim)
    fmt = _format(document)
    own = []
    for step in _steps(document):
        if step.get("kind") != "produce" or step.get("from"):
            continue
        if _step_class(step) != "generated":
            continue
        output = step.get("output")
        if not output:
            continue
        where = _confine(claim, output)
        if not os.path.isfile(where):
            continue
        entry = [output, _hash(where)]
        if fmt >= 6:
            entry.append("x" if os.stat(where).st_mode & 0o100 else "-")
        own.append(entry)
    payload = json.dumps(sorted(own), sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 2 or argv[0] not in ("root", "digest"):
        print("usage: python3 -m reticuli.reference {root|digest} <claim>",
              file=sys.stderr)
        return 2
    verb, claim = argv
    try:
        print(root(claim) if verb == "root" else build_digest(claim))
    except (ReferenceError, OSError, tomllib.TOMLDecodeError) as exc:
        print(f"reference: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
