"""The living kernel must satisfy the kernel chain's own acceptance suites.

`src/reticuli/` is the package this repository ships, and it must satisfy the
kernel — now a chain of sub-claims: core, recipe, identity, seal (the identity
machinery, in src/reticuli/_kernel/), and the outer kernel built on them
(src/reticuli/kernel.py, a facade re-exporting the chain). This check stages the
living kernel in a claim-shaped workspace and runs every suite against it:

    reticuli/__init__.py                <- the LIVING bytes
    reticuli/_kernel/{core,recipe,identity,seal}.py
    reticuli/kernel.py
    {core,recipe,identity,seal}_check.py, kernel_check.py   <- the pinned suites

NOTHING HERE IS THE AUTHORITY EXCEPT THE SUITES. Running them directly, rather
than having a sealed kernel audit the living bytes, keeps a working kernel out of
the repository's root claim: a suite is a CRITERION a rebuilding producer may
read, but no implementation is pinned, so the room stays blind.

    python3 criteria/kernel_parity.py        (from the repository root)
"""
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUITES = [os.path.join(ROOT, "criteria", n) for n in
          ("core_check.py", "recipe_check.py", "identity_check.py",
           "seal_check.py", "kernel_check.py")]
LIVING = os.path.join(ROOT, "src", "reticuli")
GENERATED = ["__init__.py", "kernel.py", "_kernel/__init__.py",
             "_kernel/core.py", "_kernel/recipe.py", "_kernel/identity.py",
             "_kernel/seal.py"]


def main() -> int:
    for suite in SUITES:
        if not os.path.isfile(suite):
            print(f"parity: the kernel suite is missing at {suite}", file=sys.stderr)
            return 1
    for name in GENERATED:
        if not os.path.isfile(os.path.join(LIVING, name)):
            print(f"parity: the living package is missing {name}", file=sys.stderr)
            return 1

    work = tempfile.mkdtemp(prefix="kernel-parity-")
    try:
        package = os.path.join(work, "reticuli")
        for name in GENERATED:
            dst = os.path.join(package, name)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(os.path.join(LIVING, name), dst)
        for suite in SUITES:
            shutil.copy2(suite, os.path.join(work, os.path.basename(suite)))

        # No claim.toml is staged, so a suite writes no verdict file: it reports
        # by exit status, which is all this check needs.
        for suite in SUITES:
            base = os.path.basename(suite)
            result = subprocess.run([sys.executable, base], cwd=work, check=False,
                                    capture_output=True, text=True,
                                    env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
            if result.returncode != 0:
                print(f"parity: the living kernel does NOT satisfy {base}",
                      file=sys.stderr)
                detail = (result.stderr or result.stdout or "").strip()
                print(("…" + detail[-1500:]) if len(detail) > 1500 else detail,
                      file=sys.stderr)
                return 1
    finally:
        shutil.rmtree(work, ignore_errors=True)

    print(f"parity-ok (the living kernel satisfies all {len(SUITES)} suites)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
