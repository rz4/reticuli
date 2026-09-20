"""Kernel-build conformance gate — materialize, re-earn, rebuild.

`audit` re-runs a claim's gates against the bytes present, cold, and re-checks
that the claim still holds; a stored "passed" is never trusted. Writes BUILD_OK.

    python3 criteria/build_check.py        (from the repository root)
"""
import os
import subprocess
import sys
import tempfile

SRC = "src" if os.path.isdir("src/reticuli") else "."
sys.path.insert(0, SRC)
from reticuli._kernel import build, seal

CLAIM = ('[claim]\nname = "b"\ninputs = ["check.txt"]\n\n[[step]]\n'
         'kind = "produce"\noutput = "impl.txt"\nclass = "generated"\n'
         'request = "x"\n\n[[step]]\nkind = "gate"\noutput = "V"\n'
         'class = "validated"\nrun = "grep -qx ok impl.txt && printf v > V"\n')


def battery() -> None:
    d = tempfile.mkdtemp()
    try:
        c = os.path.join(d, "c")
        os.makedirs(c)
        for name, body in {"claim.toml": CLAIM, "check.txt": "the impl says ok\n",
                           "impl.txt": "ok\n"}.items():
            with open(os.path.join(c, name), "w", encoding="utf-8") as f:
                f.write(body)
        subprocess.run("grep -qx ok impl.txt && printf v > V",
                       shell=True, cwd=c, check=True)
        seal.seal(c)
        assert seal.verify(c)["ok"], "the claim seals and verifies"

        r = build.audit(c)
        assert r["ok"], f"a sealed claim re-earns its gate cold: {r.get('verdict')}"
        assert r["gates"] and r["gates"][0]["status"] in ("ok", "reproduced"), \
            f"the gate is reproduced: {r['gates']!r}"

        # editing the pinned input breaks the claim: audit is not fooled
        with open(os.path.join(c, "check.txt"), "w", encoding="utf-8") as f:
            f.write("a different criterion\n")
        assert not build.audit(c)["ok"], "a tampered pinned input fails audit"
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    battery()
    if os.path.isfile("reticuli.toml") or os.path.isfile("claim.toml"):
        with open("BUILD_OK", "w", encoding="utf-8") as f:
            f.write("build-ok\n")
    print("build-ok")
