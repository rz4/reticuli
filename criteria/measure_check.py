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
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    battery()
    if os.path.isfile("reticuli.toml") or os.path.isfile("claim.toml"):
        with open("MEASURE_OK", "w") as f:
            f.write("measure-ok\n")
    print("measure-ok")
