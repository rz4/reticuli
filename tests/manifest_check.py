"""A claim may list its pinned inputs in a file instead of in the recipe.

A claim over a real corpus enumerates hundreds of paths; the TOML conformance
example was 920 of them in a 44KB recipe, which is unreadable and produces
useless diffs. `[claim] inputs_manifest` moves the list into a pinned file.

The property that must survive is the one that makes any of this worth doing:
the corpus is still committed to. The manifest is itself a pinned input, so
changing any case changes the manifest's bytes and moves the root, exactly as
enumerating them did. What the manifest must NEVER become is a wildcard read
at verification time -- identity would then depend on what happens to be in
the directory when someone looks.

    python3 tests/manifest_check.py        (from the repository root)
"""
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from reticuli import kernel, pack


def _project(work: str, cases: int = 12) -> str:
    d = os.path.join(work, "proj")
    os.makedirs(os.path.join(d, "src"))
    os.makedirs(os.path.join(d, "cases"))
    with open(os.path.join(d, "src", "impl.py"), "w") as f:
        f.write("def f(x):\n    return x * 2\n")
    for i in range(1, cases + 1):
        with open(os.path.join(d, "cases", f"c{i}.txt"), "w") as f:
            f.write(f"{i}\n{i * 2}\n")
    with open(os.path.join(d, "check.py"), "w") as f:
        f.write('import sys, glob\nsys.path.insert(0, "src")\n'
                'from impl import f\n'
                'for p in sorted(glob.glob("cases/*.txt")):\n'
                '    a, b = open(p).read().split()\n'
                '    assert f(int(a)) == int(b), p\n'
                'print("ok")\n')
    return d


def battery() -> None:
    work = tempfile.mkdtemp(prefix="manifest-check-")
    try:
        d = _project(work)
        result = pack.pack(d, "manifested", ["src/*.py"], ["check.py", "cases/*.txt"],
                           "python3 check.py && printf ok > OK", "OK",
                           inputs_manifest="INPUTS")
        assert result["ok"], "a manifested claim seals"

        recipe = kernel.load_recipe(d)
        claim = recipe["claim"]
        assert claim.get("inputs_manifest") == "INPUTS", "the recipe names the manifest"
        assert not claim.get("inputs"), "and does not also enumerate the paths"
        assert claim.get("format") == 2, "declaring the format so an older kernel refuses"

        size = os.path.getsize(os.path.join(d, kernel.RECIPE))
        assert size < 600, f"the recipe stays small regardless of corpus size: {size}"

        resolved = kernel._inputs(recipe, d)
        assert "INPUTS" in resolved, "the manifest is itself a pinned input"
        assert len(resolved) == 14, f"13 declared files plus the manifest: {resolved}"
        assert kernel.verify(d)["ok"], "and the claim verifies"

        # THE PROPERTY WORTH HAVING: the corpus is still inside the identity.
        before = kernel.read_manifest(d)["root"]
        case = os.path.join(d, "cases", "c7.txt")
        with open(case, "rb") as fh:
            original = fh.read()
        with open(case, "wb") as f:
            f.write(b"7\n999\n")
        assert not kernel.verify(d)["ok"], \
            "touching one case of twelve must break verification"
        with open(case, "wb") as f:
            f.write(original)
        assert kernel.verify(d)["ok"] and kernel.read_manifest(d)["root"] == before, \
            "and restoring it must bring the root back"

        # A manifest is a FIXED LIST, not a pattern: a file appearing in the
        # directory afterwards is not silently absorbed into the claim.
        with open(os.path.join(d, "cases", "c99.txt"), "w") as f:
            f.write("99\n198\n")
        assert kernel.verify(d)["ok"], \
            "an undeclared file must not change the root -- otherwise identity " \
            "would depend on directory contents at read time"
        os.remove(os.path.join(d, "cases", "c99.txt"))

        # A manifest naming a file that is gone is a refusal with a reason,
        # not a crash and not a quietly smaller claim.
        with open(os.path.join(d, "INPUTS"), "a") as f:
            f.write("cases/does-not-exist.txt\n")
        try:
            kernel.verify(d)
            raise AssertionError("a manifest naming a missing file must refuse")
        except kernel.ClaimError as exc:
            assert "does-not-exist" in str(exc), f"and name it: {exc}"

        print("manifest-ok")
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    battery()
