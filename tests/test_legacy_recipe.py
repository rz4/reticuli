"""A claim sealed under the older recipe filename still verifies and audits.

The recipe file was named `claim.toml` before it took the tool's name. Readers
still accept it, and they must: the filename is not in the root preimage, so a
claim sealed under the old name has exactly the identity it always had, and a
reader that only knew the new name would refuse a claim whose identity never
changed.

This used to be demonstrated by a frozen claim kept in the repository on the
old name. That claim was retired, and exhibiting a property is a weaker way to
hold it than testing it — an exhibit can pass while the property is broken for
every OTHER claim, because the exhibit was never the general case.

    pytest tests/test_legacy_recipe.py     (or: python3 tests/test_legacy_recipe.py)
"""
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from reticuli import kernel, pack


def test_a_claim_named_claim_toml_still_works() -> None:
    work = tempfile.mkdtemp(prefix="legacy-recipe-")
    try:
        claim = os.path.join(work, "legacy")
        os.makedirs(claim)
        with open(os.path.join(claim, "impl.py"), "w") as f:
            f.write("def double(x):\n    return x * 2\n")
        with open(os.path.join(claim, "check.py"), "w") as f:
            f.write("import sys\n\nsys.path.insert(0, '.')\nfrom impl import double\n\n"
                    "assert double(3) == 6\nprint('ok')\n")
        result = pack.pack(claim, "legacy", ["impl.py"], ["check.py"],
                           "python3 check.py && printf ok > OK", "OK")
        assert result["ok"], "the claim seals"

        # Seal writes the CURRENT name. Rename it to the old one, exactly as a
        # claim sealed before the rename would carry it.
        new = os.path.join(claim, kernel.RECIPE)
        old = os.path.join(claim, kernel.LEGACY_RECIPE)
        assert os.path.isfile(new), f"pack writes {kernel.RECIPE}"
        os.rename(new, old)

        assert kernel.recipe_path(claim) == old, "a reader finds the older name"
        verdict = kernel.verify(claim)
        assert verdict["ok"], "and the root is unchanged — the filename is not in it"
        assert kernel.audit(claim)["ok"], "and the claim can still re-earn its verdict"

        # The second implementation must agree, or the two have diverged on
        # what a claim even is.
        proc = subprocess.run([sys.executable, "-m", "reticuli.reference", "root", claim],
                              check=False, capture_output=True, text=True,
                              env=dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src")))
        assert proc.stdout.strip() == verdict["root"], \
            f"the reference implementation reads it too: {proc.stdout!r} {proc.stderr[-200:]}"

        # And a directory carrying NEITHER name is refused by name, not by crash.
        os.rename(old, os.path.join(claim, "not-a-recipe.toml"))
        try:
            kernel.load_recipe(claim)
            raise AssertionError("a directory with no recipe must be refused")
        except kernel.ClaimError as exc:
            assert kernel.RECIPE in str(exc) and kernel.LEGACY_RECIPE in str(exc), \
                f"and the refusal names both spellings it looked for: {exc}"

        print("legacy-recipe-ok")
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    test_a_claim_named_claim_toml_still_works()
