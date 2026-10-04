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
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    battery()
    if os.path.isfile("reticuli.toml") or os.path.isfile("claim.toml"):
        with open("MEASURE_OK", "w") as f:
            f.write("measure-ok\n")
    print("measure-ok")
