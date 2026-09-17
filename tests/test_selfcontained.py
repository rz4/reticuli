"""Pinned files may only point at things the claim contains.

Anything pinned is materialised into a rebuilding producer's room. A pinned
file that names an unpinned one is a dangling pointer there — and worse, a
claim that describes itself using material it does not commit to is incoherent:
the description could change without the identity noticing.

So the rule, and it is narrower than "a path that exists":

    A path named in a pinned file must be inside THE CLAIM'S NAMESPACE —
    a pinned input, a declared output, the recipe itself, or one of the
    format's own structural paths.

A declared output counts even though its bytes are not in the room. The recipe
names it, so a producer reading about it learns something true: that it is
theirs to write.

    pytest tests/test_selfcontained.py      (or: python3 tests/test_selfcontained.py)
"""
import pathlib
import re
import sys
import tomllib

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: Paths the FORMAT defines, rather than paths this repository happens to have.
#: `.reticuli/manifest.json` is where any claim's root is recorded; a spec that
#: could not name it could not describe the format.
STRUCTURAL = re.compile(r"^\.reticuli/|^checks/|^reticuli/|^\.\./|^claim/")

#: Path-shaped tokens. Deliberately only those with a directory separator and a
#: known extension: bare words like "tests" are prose, not pointers.
PATHS = re.compile(r"(?<![\w/])((?:[\w.-]+/)+[\w.-]+\.(?:py|md|toml|json|jsonl|png|yml))")


def namespace() -> tuple:
    """(what may be named, what gets scanned).

    Everything the claim contains may be NAMED, including declared outputs: the
    recipe names them, so a producer reading about one learns something true.
    Only what lands in a ROOM gets scanned — pinned inputs and the recipe.
    Generated files are the producer's to write and nobody reads them there.
    """
    recipe = tomllib.loads((ROOT / "reticuli.toml").read_text(encoding="utf-8"))
    pinned = set(recipe["claim"].get("inputs", [])) | {"reticuli.toml"}
    nameable = pinned | {step["output"] for step in recipe.get("step", [])}
    return nameable, pinned


def offenders() -> dict:
    inside, scanned = namespace()
    found = {}
    for name in sorted(scanned):
        path = ROOT / name
        if not path.is_file() or path.suffix == ".png":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        # The kernel's suite is sealed inside root 4b90feef… and cites a file in
        # the v1 lab by name. It is an attribution to another repository rather
        # than a pointer into this one, and correcting it would move a root that
        # carries a cross-vendor three-machine proof. Excluded knowingly.
        if name.endswith("kernel_check.py"):
            continue
        # The repository's own published coordinate is a remote spelling of a
        # local path: `rz4/reticuli/<path>@ref` in a caller's workflow names
        # <path> here. Strip the coordinate and hold the remainder to the
        # same rule -- a remote pointer to an unpinned file still dangles.
        bad = sorted({p for p in PATHS.findall(text)
                      if (q := p.removeprefix("rz4/reticuli/")) not in inside
                      and not STRUCTURAL.match(q)})
        if bad:
            found[name] = bad
    return found


def test_pinned_files_are_self_contained() -> None:
    found = offenders()
    assert not found, (
        "pinned files name paths the claim does not contain, so they dangle "
        "inside a rebuild room:\n" + "\n".join(
            f"  {name}: {', '.join(paths)}" for name, paths in found.items()))
    nameable, scanned = namespace()
    print(f"selfcontained-ok ({len(scanned)} files scanned, "
          f"{len(nameable)} nameable)")


if __name__ == "__main__":
    try:
        test_pinned_files_are_self_contained()
    except AssertionError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from None
