"""Held-out evaluation, on a claim small enough to know the answers for.

`src/reticuli/heldout.py` hides part of a claim's case corpus, re-seals on the
rest, has producers regrow the implementation blind, and judges each rebuild on
the cases it never saw. Three things have to hold for that number to mean
anything, and all three are checked here against a synthetic eight-case claim
whose rule (`f(n) = 3n + 1`) lives nowhere but in the cases:

  * the rig judges correctly — the claim's own implementation passes every
    hidden case, so a low rate is the producer's, never the room's;
  * the measurement is SENSITIVE — a producer that carries the rule scores
    1.00 on the hidden cases and a producer that memorises the kept ones
    scores 0.00, from the same split and the same gate;
  * the claim being measured is NOT MUTATED — it verifies at the same root
    afterwards, because every step of the procedure happens on copies.

The agreement arithmetic is pinned separately on hand-built outcome vectors:
it must not depend on which cases a particular root happens to hide.

    python3 tests/heldout_check.py        (from the repository root)
"""
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from reticuli import assess, heldout, kernel, pack

CHECK = '''import glob
import sys

sys.path.insert(0, ".")
from impl import f

cases = sorted(glob.glob("cases/*.txt"))
assert cases, "no cases in the room"
for path in cases:
    with open(path, encoding="utf-8") as handle:
        arg, want = handle.read().split()
    got = f(int(arg))
    assert got == int(want), f"{path}: f({arg}) = {got}, expected {want}"
print(f"tripler-ok ({len(cases)} cases)")
'''

# A producer that carries the rule: it never reads the cases at all.
GOOD = '''import os

with open(os.environ["RETICULI_OUTPUT"], "w", encoding="utf-8") as handle:
    handle.write("def f(n):\\n    return 3 * n + 1\\n")
'''

# A producer that enumerates: whatever cases are in the blind workspace become a
# lookup table, and anything else gets a constant. It passes every case it can
# see, so it lands on the kept claim -- and that is the whole point.
CRIB = '''import glob
import os
import sys

table = {}
for path in sorted(glob.glob("cases/*.txt")):
    with open(path, encoding="utf-8") as handle:
        arg, want = handle.read().split()
    table[int(arg)] = int(want)
with open(os.environ["RETICULI_OUTPUT"], "w", encoding="utf-8") as handle:
    handle.write(f"_SEEN = {table!r}\\n\\n\\ndef f(n):\\n"
                 f"    return _SEEN.get(n, {sys.argv[1]})\\n")
'''


def _claim(room: str) -> str:
    """An eight-case claim whose rule exists only in the cases."""
    os.makedirs(os.path.join(room, "cases"))
    with open(os.path.join(room, "check.py"), "w", encoding="utf-8") as f:
        f.write(CHECK)
    for n in range(1, 9):
        with open(os.path.join(room, "cases", f"c{n}.txt"), "w", encoding="utf-8") as f:
            f.write(f"{n} {3 * n + 1}\n")
    with open(os.path.join(room, "impl.py"), "w", encoding="utf-8") as f:
        f.write("def f(n):\n    return 3 * n + 1\n")
    pack.pack(room, "tripler", generated=["impl.py"], inputs=["check.py", "cases/*.txt"],
              gate="python3 check.py && printf ok > OK", gate_output="OK")
    return room


def battery() -> None:
    # -- the arithmetic, independent of any particular split -----------------
    both = {"a": True, "b": True, "c": False, "d": False}
    same = heldout.agreement(both, dict(both))
    assert same == {"cases": 4, "agreement": 1.0, "expected": 0.5, "excess": 0.5}, \
        f"two producers that pass and fail together at p=0.5 show excess 0.5: {same}"
    opposite = heldout.agreement(both, {k: not v for k, v in both.items()})
    assert opposite["agreement"] == 0.0 and opposite["excess"] == -0.5, \
        f"two producers that never agree show a negative excess: {opposite}"
    assert heldout.agreement({}, {})["excess"] is None, "no shared cases: no number"

    # a claim with no family of inputs has no corpus, and says so rather than
    # inventing one out of its acceptance test
    assert heldout.case_corpus({"claim": {"inputs": ["check.py"]}, "step": []}) == []

    work = tempfile.mkdtemp(prefix="heldout-check-")
    try:
        claim = _claim(os.path.join(work, "tripler"))
        sealed_root = kernel.read_manifest(claim)["root"]

        recipe = kernel.load_recipe(claim)
        corpus = heldout.case_corpus(recipe)
        assert len(corpus) == 8 and "check.py" not in corpus, \
            f"the corpus is the cases, never the gate's own decider: {corpus}"
        kept, held = heldout.split(corpus, 0.25, sealed_root)
        assert (kept, held) == heldout.split(corpus, 0.25, sealed_root), \
            "the split is seeded from the root, so it is reproducible"
        assert len(held) == 2 and len(kept) == 6 and sorted(kept + held) == sorted(corpus), \
            f"the split partitions the corpus: {len(kept)} kept, {len(held)} held"

        producers = [f"good=python3 {os.path.join(work, 'good.py')}",
                     f"crib=python3 {os.path.join(work, 'crib.py')} 0"]
        for name, source in (("good.py", GOOD), ("crib.py", CRIB)):
            with open(os.path.join(work, name), "w", encoding="utf-8") as f:
                f.write(source)

        before = sorted(os.listdir(claim)), sorted(os.listdir(work))
        r = heldout.measure(claim, fraction=0.25, producers=producers)
        assert r["cases"] == 8 and r["kept"] == 6 and r["held_out"] == 2, r
        rows = {row["name"]: row for row in r["producers"]}
        assert set(rows) == {"sealed", "good", "crib"}, f"one row per producer: {set(rows)}"
        assert all(row["landed"] for row in rows.values()), \
            f"every producer satisfied the KEPT cases: {[(k, v['why']) for k, v in rows.items()]}"

        # the rig's own check: the claim's code was written with every case in
        # view, so anything below 1.00 here is a broken judging room
        assert rows["sealed"]["pass_rate"] == 1.0, \
            f"the claim's own implementation passes the hidden cases: {rows['sealed']}"
        assert not rows["sealed"]["blind"], "the claim's own code is a control, not a producer"
        # and the measurement is sensitive: carrying the rule and memorising the
        # cases are the two ends, from the same split and the same gate
        assert rows["good"]["pass_rate"] == 1.0, f"a rule that generalises: {rows['good']}"
        assert rows["crib"]["pass_rate"] == 0.0, f"a table that enumerates: {rows['crib']}"

        assert [(p["a"], p["b"]) for p in r["pairs"]] == [("good", "crib")], \
            f"pairs are over BLIND producers only, so the control is not paired: {r['pairs']}"
        pair = r["pairs"][0]
        assert abs(pair["excess"] - (pair["agreement"] - pair["expected"])) < 1e-12, pair

        # the measured claim is untouched: same root, still fresh, and nothing
        # left behind either inside it or beside it (v1 built its workspace at
        # `<claim>.heldout`, a sibling, and wrote residue into the claim's store)
        assert kernel.verify(claim)["ok"] and kernel.read_manifest(claim)["root"] == sealed_root, \
            "measuring a claim must not move it"
        assert (sorted(os.listdir(claim)), sorted(os.listdir(work))) == before, \
            "the procedure works on copies: nothing appears in or beside the claim"
        assert r["workspace"] is None, "a scratch workspace is cleaned up unless kept"

        # and the rung reaches the ladder: `assess` reports it as measured
        report = assess.assess(claim, mutants=0, heldout=0.25, heldout_producers=producers)
        assert "generalization" in report["measured"], report["not_measured"]
        assert "generalization" not in report["not_measured"], report["not_measured"]
        # named without producers, the rung stays unmeasured and says which half
        # is missing -- an unmeasured dimension is stated, never omitted
        bare = assess.assess(claim, mutants=0, heldout=0.25)
        assert "no producer" in bare["not_measured"]["generalization"], bare["not_measured"]
    finally:
        shutil.rmtree(work, ignore_errors=True)

    print("heldout-ok (8 cases, 6 kept, 2 hidden; rule 1.00, table 0.00)")


if __name__ == "__main__":
    battery()
