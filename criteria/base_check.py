"""cli-base conformance gate — the output contract and the claim views.

output: the `--json` envelope shape and the one-voice error line. views: reading
a sealed claim into the documented state dict and the `next` ladder. Writes
BASE_OK.

    python3 criteria/base_check.py
"""
import argparse
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile

SRC = "src" if os.path.isdir("src/reticuli") else "."
sys.path.insert(0, SRC)
from reticuli._cli import output, views
from reticuli import kernel

ENVELOPE = {"command", "ok", "status", "root", "data"}

CLAIM = ('[claim]\nname = "b"\ninputs = ["check.txt"]\n\n[[step]]\nkind = "produce"\n'
         'output = "impl.txt"\nclass = "generated"\nrequest = "x"\n\n[[step]]\n'
         'kind = "gate"\noutput = "V"\nclass = "validated"\n'
         'run = "grep -qx ok impl.txt && printf v > V"\n')


def battery() -> None:
    # the --json envelope: five top-level fields, the verb echoed, data underneath
    args = argparse.Namespace(json=True, verbose=False, color="never", cmd="verify")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        output._finish("verify", {"root": "a" * 64, "ok": True}, True, "fresh", args, None)
    env = json.loads(buf.getvalue())
    assert set(env) == ENVELOPE and env["command"] == "verify" and env["ok"] is True, \
        f"the envelope shape: {set(env)}"

    # the one-voice error line: ret: <verb>: <fact>, on stderr
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        output._err("verify", "no recipe here")
    assert err.getvalue().startswith("ret: verify: no recipe here"), err.getvalue()

    # views: a sealed claim reads into the documented state dict + a next rung
    d = tempfile.mkdtemp()
    try:
        c = os.path.join(d, "c")
        os.makedirs(c)
        for n, b in {"claim.toml": CLAIM, "check.txt": "the impl says ok\n",
                     "impl.txt": "ok\n"}.items():
            with open(os.path.join(c, n), "w") as _f:
                _f.write(b)
        subprocess.run("grep -qx ok impl.txt && printf v > V", shell=True, cwd=c, check=True)
        kernel.seal(c)
        view = views._claim_view(c)
        assert {"name", "root", "phase", "next"} <= set(view), \
            f"the claim view carries the documented keys: {sorted(view)}"
        assert isinstance(views._next_step(view), str) and views._next_step(view), \
            "the ladder names a next rung"
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    battery()
    if os.path.isfile("reticuli.toml") or os.path.isfile("claim.toml"):
        with open("BASE_OK", "w") as f:
            f.write("base-ok\n")
    print("base-ok")
