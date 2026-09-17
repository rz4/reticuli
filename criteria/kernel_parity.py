"""The living kernel must satisfy the kernel claim's own acceptance suite.

`src/reticuli/` is the package this repository ships, and it must satisfy the
kernel claim, root 82a81357… (the v2.3 revision). This check stages the living kernel in a
claim-shaped workspace and runs that claim's suite against it:

    reticuli/{__init__,kernel}.py   <- the LIVING bytes
    kernel_check.py                 <- the claim's pinned suite

NOTHING HERE IS THE AUTHORITY EXCEPT THE SUITE. An earlier version had the
sealed kernel `audit()` the living bytes, so a broken kernel would never be the
judge of whether it was broken. That was sound, but it meant pinning a whole
working kernel into this repository's root claim — and ANYTHING PINNED IS
HANDED TO A REBUILDING PRODUCER. An M3 asked to regrow `src/reticuli/kernel.py`
could read a conformant one sitting beside it: 57KB of 255KB, and the
foundational module.

Running the suite directly gives that back and costs nothing. The suite is a
CRITERION, so a producer seeing it is correct and necessary; no implementation
is pinned, so the room stays blind. And no kernel judges anything — the suite
does, which is a weaker assumption than the one it replaces.

    python3 criteria/kernel_parity.py        (from the repository root)
"""
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUITE = os.path.join(ROOT, "criteria", "kernel_check.py")
SEALED = os.path.join(ROOT, "examples", "kernel", "checks", "kernel_check.py")
LIVING = os.path.join(ROOT, "src", "reticuli")
GENERATED = ["__init__.py", "kernel.py"]


def main() -> int:
    if not os.path.isfile(SUITE):
        print(f"parity: the kernel claim's suite is missing at {SUITE}",
              file=sys.stderr)
        return 1
    for name in GENERATED:
        if not os.path.isfile(os.path.join(LIVING, name)):
            print(f"parity: the living package is missing {name}", file=sys.stderr)
            return 1

    # The sealed claim carries its own copy at checks/kernel_check.py, inside
    # root 82a81357…, so it cannot be a symlink to this one. Two copies can
    # drift, and drift would mean the criterion this repository publishes is not
    # the criterion the claim was sealed against.
    if os.path.isfile(SEALED):
        with open(SUITE, "rb") as f:
            here = f.read()
        with open(SEALED, "rb") as f:
            sealed = f.read()
        if here != sealed:
            print(f"parity: {SUITE} has drifted from the sealed copy at {SEALED} "
                  f"({len(here)} vs {len(sealed)} bytes)", file=sys.stderr)
            return 1

    work = tempfile.mkdtemp(prefix="kernel-parity-")
    try:
        package = os.path.join(work, "reticuli")
        os.makedirs(package)
        for name in GENERATED:
            shutil.copy2(os.path.join(LIVING, name), os.path.join(package, name))
        shutil.copy2(SUITE, os.path.join(work, "kernel_check.py"))

        # No claim.toml is staged, so the suite writes no verdict file: it
        # reports by exit status, which is all this check needs.
        result = subprocess.run([sys.executable, "kernel_check.py"], cwd=work,
                                check=False, capture_output=True, text=True,
                                env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    finally:
        shutil.rmtree(work, ignore_errors=True)

    if result.returncode == 0:
        print("parity-ok (the living kernel satisfies the kernel claim's suite)")
        return 0

    print("parity: the living kernel does NOT satisfy the suite", file=sys.stderr)
    detail = (result.stderr or result.stdout or "").strip()
    print(("…" + detail[-1500:]) if len(detail) > 1500 else detail, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
