"""Zeta's own gate: every criterion, run against the library it ships.

Zeta is a claim like any other. Its criteria judge the machinery -- how a
partition becomes a lane, how witnesses collapse onto phenomena, what a queue
entry must carry, what a promotion record must say -- and they judge it against
fixtures, never against the live queue. A criterion that read the queue would
make zeta's verdict depend on whatever the last sweep happened to find, and a
verdict that moves on its own is not a criterion.

The queue, the population registry and the promotion ledger are outputs. They
are not inputs to this root, which is why a sweep can run as often as it likes
without moving zeta's identity.
"""

import glob
import os
import subprocess
import sys

failed = []
for path in sorted(glob.glob("criteria/*.py")):
    result = subprocess.run([sys.executable, path], text=True, check=False,
                            capture_output=True,
                            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1",
                                     NO_COLOR="1"))
    print(f"{'ok  ' if result.returncode == 0 else 'FAIL'}  {path}", flush=True)
    if result.returncode:
        failed.append((path, (result.stderr or result.stdout)[-800:]))

if failed:
    for path, why in failed:
        print(f"\n--- {path}\n{why}", file=sys.stderr)
    raise SystemExit(1)

with open("ZETA_OK", "w", encoding="utf-8") as handle:
    handle.write("ok\n")
print("zeta-ok")
