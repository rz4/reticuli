"""Can a claim publish a cost ceiling that binds nothing?

Research tooling -- not normative, not pinned. Recorded in
research/audits/2026-11-04-envelope-finiteness.md.

The cost envelope exists so that "reproducible" cannot be satisfied by a
reproduction nobody could afford to run. The validator requires each ceiling
to be a positive number and does not require it to be finite, so `inf` and
`nan` both parse -- one making the ceiling unexceedable, the other making it
unsatisfiable.

    PYTHONPATH=src python3 research/harness/identity/envelope_finiteness.py

Exits 0 while the defect reproduces, 1 once the validator refuses both, so
this is also the check a repair has to flip.
"""
import math
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.getcwd(), "src"))

from reticuli._kernel import recipe as recipe_mod  # noqa: E402

CLAIM = '''[claim]
name = "envelope"
format = 4
inputs = []

[claim.envelope]
usd = {ceiling}

[[step]]
kind = "gate"
output = "OK"
class = "validated"
run = "printf ok > OK"
'''


def _parses(scratch, ceiling):
    """Does a claim declaring this ceiling survive the parser?"""
    where = tempfile.mkdtemp(dir=scratch)
    with open(os.path.join(where, "reticuli.toml"), "w") as f:
        f.write(CLAIM.format(ceiling=ceiling))
    with open(os.path.join(where, "OK"), "w") as f:
        f.write("ok")
    try:
        return True, recipe_mod.load_recipe(where)["claim"]["envelope"]["usd"]
    except Exception as exc:                        # noqa: BLE001
        return False, str(exc)


def main():
    scratch = tempfile.mkdtemp(prefix="reticuli-envelope-")
    admitted = []
    try:
        print("Declared ceilings, and whether the parser admits them:\n")
        for literal in ("inf", "nan", "-inf", "0", "40.0"):
            ok, detail = _parses(scratch, literal)
            if ok and isinstance(detail, float) and not math.isfinite(detail):
                admitted.append(literal)
                note = "  <- not finite, and admitted"
            else:
                note = ""
            shown = detail if ok else f"refused: {str(detail)[:48]}"
            print(f"  usd = {literal:<6} {'parses' if ok else 'REFUSED':<8} "
                  f"{shown}{note}")

        # crosscheck compares with: within = bool(paid <= declared)
        print("\nWhat each admitted ceiling does to `paid <= declared`:\n")
        for literal in admitted:
            ceiling = float(literal)
            for paid in (0.01, 1e308):
                print(f"  usd = {literal:<4} paid = {paid:<8g} "
                      f"within = {bool(paid <= ceiling)}")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    print()
    if admitted:
        print(f"Non-finite ceilings admitted: {', '.join(admitted)}.")
        print("A claim can publish a hard budget that imposes no finite "
              "limit (inf), or none that can be met (nan).")
        return 0
    print("The validator now refuses non-finite ceilings. Update the audit "
          "record.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
