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




# ==== seam block for base_check.py ====
# Paste into the check; call _seam() from its battery()/main.

# --- _cli/output.py: 7 seam names (0 value, 0 kind, 7 callable) ---
_SEAM__cli_output_VALUES = {
}
_SEAM__cli_output_KINDS = {}
_SEAM__cli_output_CALLABLES = ('_Progress', '_confirm', '_err', '_finish', '_line', '_rel', '_warn_block')

# --- _cli/views.py: 9 seam names (0 value, 0 kind, 9 callable) ---
_SEAM__cli_views_VALUES = {
}
_SEAM__cli_views_KINDS = {}
_SEAM__cli_views_CALLABLES = ('_claim_view', '_deciding_words', '_gate_ok', '_next_step', '_phase', '_read_residue', '_signatures', '_verdict', '_verified')

def _seam() -> None:
    from reticuli._cli import output as _m__cli_output
    for _n, _v in _SEAM__cli_output_VALUES.items():
        assert getattr(_m__cli_output, _n) == _v, f'_cli/output.py seam {_n} changed'
    for _n in _SEAM__cli_output_KINDS:
        assert hasattr(_m__cli_output, _n), f'_cli/output.py must export {_n}'
    for _n in _SEAM__cli_output_CALLABLES:
        assert callable(getattr(_m__cli_output, _n, None)), f'_cli/output.py must export callable {_n}'
    from reticuli._cli import views as _m__cli_views
    for _n, _v in _SEAM__cli_views_VALUES.items():
        assert getattr(_m__cli_views, _n) == _v, f'_cli/views.py seam {_n} changed'
    for _n in _SEAM__cli_views_KINDS:
        assert hasattr(_m__cli_views, _n), f'_cli/views.py must export {_n}'
    for _n in _SEAM__cli_views_CALLABLES:
        assert callable(getattr(_m__cli_views, _n, None)), f'_cli/views.py must export callable {_n}'


def battery() -> None:
    _seam()
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
