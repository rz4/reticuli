"""measure conformance gate — assessment and reuse.

assess measures how much a claim's tests prove (mutation, buckets); reuse keys a
verdict by root+build+platform+interpreter and never records a failure. Writes
MEASURE_OK.

    python3 criteria/measure_check.py
"""
import os
import subprocess
import sys
import tempfile

SRC = "src" if os.path.isdir("src/reticuli") else "."
sys.path.insert(0, SRC)
from reticuli import assess as assess_mod, reuse, kernel

CLAIM = ('[claim]\nname = "m"\ninputs = ["check.py"]\n\n[[step]]\nkind = "produce"\n'
         'output = "impl.py"\nclass = "generated"\nrequest = "x"\n\n[[step]]\n'
         'kind = "gate"\noutput = "OK"\nclass = "validated"\n'
         'run = "python3 check.py && printf ok > OK"\n')
IMPL = "def f(n):\n    return n * 2\n"
CHECK = "from impl import f\nassert f(3) == 6 and f(0) == 0\n"


def battery() -> None:
    d = tempfile.mkdtemp()
    try:
        c = os.path.join(d, "c")
        os.makedirs(c)
        for n, b in {"claim.toml": CLAIM, "impl.py": IMPL, "check.py": CHECK}.items():
            with open(os.path.join(c, n), "w") as _f:
                _f.write(b)
        subprocess.run("python3 check.py && printf ok > OK", shell=True, cwd=c, check=True)
        kernel.seal(c)

        # reuse: the fingerprint keys on identity + build + host, and a verdict
        # round-trips; a failing verdict is never remembered
        fp = reuse.fingerprint(c)
        assert {"root", "build", "platform", "python"} <= set(fp), \
            f"the reuse fingerprint keys on root+build+host: {sorted(fp)}"
        reuse.remember(c, {"ok": True, "gates": []})
        assert reuse.lookup(c) is not None, "a passing verdict round-trips"

        # assess: measuring the tests yields the documented buckets
        r = assess_mod.assess(c, mutants=2)
        assert {"measured", "not_measured", "not_applicable"} <= set(r), \
            f"assess reports the buckets: {sorted(r)}"

        # REUSE IS A PROMISE, NOT A CONVENIENCE (2026-10-04, the final
        # bundle): a layered audit that skips work already earned must say
        # so — `reused`, never `earned` — name whose trust it leaned on,
        # and redo everything when nothing is cached. The honesty contract
        # of the verdict cache, pinned where the cache lives.
        saved_cache = os.environ.get("RETICULI_CACHE")
        os.environ["RETICULI_CACHE"] = os.path.join(d, "earned-cache")
        try:
            lw = os.path.join(d, "layered")
            os.makedirs(lw)
            with open(os.path.join(lw, "m.py"), "w") as f:
                f.write("X = 1\n")
            with open(os.path.join(lw, "c1.py"), "w") as f:
                f.write("import sys; sys.path.insert(0, '.')\n"
                        "import m\nassert m.X == 1\n")
            with open(os.path.join(lw, "n.py"), "w") as f:
                f.write("import sys; sys.path.insert(0, '.')\n"
                        "import m\nY = m.X + 1\n")
            with open(os.path.join(lw, "c2.py"), "w") as f:
                f.write("import sys; sys.path.insert(0, '.')\n"
                        "import n\nassert n.Y == 2\n")
            spec = [
                {"name": "floor",
                 "files": {"m.py": os.path.join(lw, "m.py")},
                 "check": ("c1.py", os.path.join(lw, "c1.py")),
                 "gate": "python3 c1.py", "verdict": "L1_OK"},
                {"name": "upper",
                 "files": {"m.py": os.path.join(lw, "m.py"),
                           "n.py": os.path.join(lw, "n.py")},
                 "check": ("c2.py", os.path.join(lw, "c2.py")),
                 "gate": "python3 c2.py", "verdict": "L2_OK"},
            ]
            first = reuse.layered_audit(spec)
            assert first["ok"] and \
                [row["status"] for row in first["layers"]] == ["earned", "earned"], \
                f"nothing cached: every layer is earned cold: {first['layers']}"
            second = reuse.layered_audit(spec)
            assert second["ok"] and \
                [row["status"] for row in second["layers"]] == ["reused", "reused"], \
                "identical work is reused, and says so"
            assert all(row.get("reused") and row.get("source")
                       for row in second["layers"]), \
                "a reused verdict carries when it was earned and whose " \
                "trust it leaned on — cheaper is louder, never quieter"
            assert not any(row["status"] == "earned"
                           for row in second["layers"]), \
                "`reused` is never spelled `earned`"
        finally:
            if saved_cache is None:
                os.environ.pop("RETICULI_CACHE", None)
            else:
                os.environ["RETICULI_CACHE"] = saved_cache

        _heldout_agreement_contract()
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)


def _heldout_agreement_contract() -> None:
    """THE HELD-OUT AGREEMENT STATISTIC IS UNDER CONTRACT (2026-11-03).

    An outside source review observed that `heldout.py` is a generated
    output, `tests/` is outside this root, and no pinned criterion exercised
    the agreement arithmetic -- so a conforming rebuild could change what the
    research outputs MEAN while passing every pinned check. Two conforming
    versions of the tool would then report different adequacy for the same
    reconstruction experiment. That is the gap this closes.

    What is pinned here is the arithmetic AND the interpretation's limit. The
    marginal excess is confounded by case difficulty: under conditional
    independence its expectation is `2 * Cov_i(p_Ai, p_Bi)`, so producers
    that share nothing at all show a large positive excess whenever some
    cases are harder than others -- which is every real corpus. The
    difficulty-adjusted form is the one that may be read as evidence of
    shared structure, it needs four producers to exist, and it says so
    instead of guessing.
    """
    from reticuli import heldout

    # --- the marginal arithmetic, exactly ---
    a = {"c0": True, "c1": True, "c2": False, "c3": False}
    same = heldout.agreement(a, a)
    assert same["agreement"] == 1.0, "identical outcomes agree everywhere"
    pa = 0.5
    assert abs(same["expected"] - (pa * pa + (1 - pa) * (1 - pa))) < 1e-12, \
        "expected is the marginal-rate independence baseline, p*q + (1-p)(1-q)"
    assert abs(same["excess"] - (1.0 - 0.5)) < 1e-12, \
        "excess is observed minus that baseline"
    opposite = {k: not v for k, v in a.items()}
    assert heldout.agreement(a, opposite)["agreement"] == 0.0, \
        "opposite outcomes agree nowhere"
    assert heldout.agreement({}, {})["cases"] == 0 \
        and heldout.agreement({}, {})["excess"] is None, \
        "no shared case is unmeasured, never a zero"
    # rates come from the SHARED cases, so the three numbers stay consistent
    partial = heldout.agreement({"c0": True, "c9": False}, {"c0": True})
    assert partial["cases"] == 1 and partial["agreement"] == 1.0, \
        "only cases both producers were judged on are compared"

    # --- the confounder, as a fixture rather than a claim in prose ---
    # Deterministic: 100 cases, two producers that share NO structure. On the
    # 50 easy cases each fails exactly one DIFFERENT case; on the 50 hard
    # cases each passes exactly one DIFFERENT case. Their outcomes are
    # therefore maximally unaligned given the difficulty, and the excess is
    # still large and positive -- it is measuring difficulty.
    easy = [f"e{i}" for i in range(50)]
    hard = [f"h{i}" for i in range(50)]
    pa_out = {c: True for c in easy} | {c: False for c in hard}
    pb_out = dict(pa_out)
    pa_out[easy[0]] = False; pa_out[hard[0]] = True
    pb_out[easy[1]] = False; pb_out[hard[1]] = True
    conf = heldout.agreement(pa_out, pb_out)
    assert conf["excess"] > 0.4, \
        f"the marginal excess is inflated by difficulty alone: {conf['excess']:.3f}"

    # --- the difficulty-adjusted form, and its floor ---
    assert heldout.stratified_excess({"a": pa_out, "b": pb_out})["stratified"] \
        is None, "two producers cannot identify convention from difficulty"
    three = {"a": pa_out, "b": pb_out, "c": dict(pa_out)}
    r3 = heldout.stratified_excess(three)
    assert r3["stratified"] is None and "four" in (r3["why"] or ""), \
        "three producers leave one leave-out observation, too few for an " \
        "unbiased per-case estimate; the floor is reported, not guessed"
    # four producers: the estimate exists. Every producer here is near-
    # identical, so the leave-out null explains the agreement and the
    # difficulty-adjusted excess sits at zero rather than near +0.5.
    four = {"a": pa_out, "b": pb_out, "c": dict(pa_out), "d": dict(pb_out)}
    r4 = heldout.stratified_excess(four)
    assert r4["stratified"] is not None, "four producers admit the estimate"
    assert abs(r4["stratified"]) < 0.1, \
        f"structure the whole population shares is explained by the " \
        f"difficulty null, not reported as hidden convention: {r4['stratified']:.3f}"
    assert conf["excess"] - r4["stratified"] > 0.3, \
        "and the two statistics must be distinguishable: the marginal form " \
        "reports as shared structure what the adjusted form attributes to " \
        "difficulty"


if __name__ == "__main__":
    battery()
    if os.path.isfile("reticuli.toml") or os.path.isfile("claim.toml"):
        with open("MEASURE_OK", "w") as f:
            f.write("measure-ok\n")
    print("measure-ok")
