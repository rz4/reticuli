"""The repository's own gate: every criterion, run against the package it ships.

This is what `ret audit .` executes, and it is the reason `ret verify .` means
anything — the root recorded in `.reticuli/manifest.json` was earned by this
script passing, cold, in a sandboxed workspace holding nothing but the claim's
declared files.

It globs `criteria/` rather than listing it. Adding a suite still moves the
repository's root, because the suite file is itself a pinned input; the gate
text does not have to change for identity to notice.
"""
import glob
import os
import subprocess
import sys

failed = []
#: Criteria that are a claim's GATE rather than a standalone check: they run
#: inside a claim directory, against the package staged beside them, so running
#: them from the repository root would fail on an import. They are not skipped
#: -- kernel_parity.py stages and runs them -- and this list is explicit so
#: the omission can never be a silent glob gap.
STAGED = {"kernel_check.py", "core_check.py", "recipe_check.py",
          "identity_check.py", "seal_check.py", "run_check.py",
          "build_check.py", "attest_check.py"}

for path in sorted(glob.glob("criteria/*.py")):
    if os.path.basename(path) in STAGED:
        continue
    result = subprocess.run([sys.executable, path], text=True, check=False,
                            capture_output=True,
                            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    print(f"{'ok  ' if result.returncode == 0 else 'FAIL'}  {path}", flush=True)
    if result.returncode:
        failed.append((path, (result.stderr or result.stdout)[-800:]))

if failed:
    for path, why in failed:
        print(f"\n--- {path}\n{why}", file=sys.stderr)
    raise SystemExit(1)

with open("REPO_OK", "w", encoding="utf-8") as f:
    f.write("ok\n")
print("repo-ok")
