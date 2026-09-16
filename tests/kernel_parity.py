"""The living kernel must stay inside the sealed claim's equivalence class.

`src/reticuli/` is the package this repository ships; `conformance/kernel/` is the sealed
claim the kernel must satisfy (root 4b90feef…; its proven predecessor
d64cc301… is kept at conformance/kernel-2.0/). This check asks the claim to judge
the living bytes:

    audit(seed, produce_from={seed's generated outputs: src's files})

which is the kernel's own composed-audit path — a component's check
re-earning a dependent's shipped bytes. The judge is the SEALED kernel, not
the living one: a broken kernel must not be the authority on whether it is
broken. The verdict is earned by running the seed's gate on src's bytes, so
identity alone never carries it.

    python3 tests/kernel_parity.py        (from the repository root)
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLAIM = os.path.join(ROOT, "conformance", "kernel")
LIVING = os.path.join(ROOT, "src", "reticuli")

sys.path.insert(0, CLAIM)                      # the sealed kernel judges
from reticuli import kernel

GENERATED = ["reticuli/__init__.py", "reticuli/kernel.py"]


def main() -> int:
    for rel in GENERATED:
        src = os.path.join(LIVING, os.path.basename(rel))
        if not os.path.isfile(src):
            print(f"parity: the living package is missing {src}", file=sys.stderr)
            return 1

    substitute = {rel: os.path.join(LIVING, os.path.basename(rel)) for rel in GENERATED}
    a = kernel.audit(CLAIM, produce_from=substitute)
    if a["ok"]:
        print(f"parity-ok (living kernel earns {a['root'][:12]}…)")
        return 0

    print("parity: the living kernel does NOT earn the sealed claim", file=sys.stderr)
    for g in a.get("gates", []):
        print(f"  gate {g['output']}: {g['status']} {g.get('detail', '')}", file=sys.stderr)
    if a.get("environment"):
        print(f"  environment missing: {a['environment']}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
