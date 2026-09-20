"""The living kernel must satisfy the kernel claim's own acceptance suites.

`src/reticuli/` is the package this repository ships, and it must satisfy the
kernel — now a chain of two sub-claims: the identity core (kernel-core, the
sealed claim at examples/kernel) and the outer kernel built on it. This check
stages the living kernel in a claim-shaped workspace and runs BOTH suites
against it:

    reticuli/__init__.py            <- the LIVING bytes
    reticuli/_kernel/__init__.py
    reticuli/_kernel/inner.py       <- the identity core
    reticuli/kernel.py              <- the outer kernel + facade
    kernel_inner_check.py           <- the core claim's pinned suite
    kernel_check.py                 <- the outer claim's pinned suite

NOTHING HERE IS THE AUTHORITY EXCEPT THE SUITES. An earlier version had the
sealed kernel `audit()` the living bytes, so a broken kernel would never be the
judge of whether it was broken. That was sound, but it meant pinning a whole
working kernel into this repository's root claim — and ANYTHING PINNED IS HANDED
TO A REBUILDING PRODUCER. Running the suites directly gives that back and costs
nothing: a suite is a CRITERION, so a producer seeing it is correct; no
implementation is pinned, so the room stays blind; and no kernel judges
anything.

    python3 criteria/kernel_parity.py        (from the repository root)
"""
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INNER_SUITE = os.path.join(ROOT, "criteria", "kernel_inner_check.py")
OUTER_SUITE = os.path.join(ROOT, "criteria", "kernel_check.py")
# The core claim carries its own copy at examples/kernel/checks/, inside its
# sealed root, so it cannot be a symlink to this one. Two copies can drift, and
# drift would mean the criterion this repository publishes is not the one the
# claim was sealed against.
SEALED_INNER = os.path.join(ROOT, "examples", "kernel", "checks",
                            "kernel_inner_check.py")
LIVING = os.path.join(ROOT, "src", "reticuli")
GENERATED = ["__init__.py", "kernel.py", "_kernel/__init__.py",
             "_kernel/inner.py"]


def main() -> int:
    for suite in (INNER_SUITE, OUTER_SUITE):
        if not os.path.isfile(suite):
            print(f"parity: the kernel suite is missing at {suite}", file=sys.stderr)
            return 1
    for name in GENERATED:
        if not os.path.isfile(os.path.join(LIVING, name)):
            print(f"parity: the living package is missing {name}", file=sys.stderr)
            return 1

    if os.path.isfile(SEALED_INNER):
        with open(INNER_SUITE, "rb") as f:
            here = f.read()
        with open(SEALED_INNER, "rb") as f:
            sealed = f.read()
        if here != sealed:
            print(f"parity: {INNER_SUITE} has drifted from the sealed copy at "
                  f"{SEALED_INNER} ({len(here)} vs {len(sealed)} bytes)",
                  file=sys.stderr)
            return 1

    work = tempfile.mkdtemp(prefix="kernel-parity-")
    try:
        package = os.path.join(work, "reticuli")
        for name in GENERATED:
            dst = os.path.join(package, name)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(os.path.join(LIVING, name), dst)
        for suite in (INNER_SUITE, OUTER_SUITE):
            shutil.copy2(suite, os.path.join(work, os.path.basename(suite)))

        # No claim.toml is staged, so a suite writes no verdict file: it reports
        # by exit status, which is all this check needs.
        for suite in (INNER_SUITE, OUTER_SUITE):
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

    print("parity-ok (the living kernel satisfies both kernel suites)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
