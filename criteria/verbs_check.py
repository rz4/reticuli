"""cli-verbs conformance gate — the verb handlers.

Each verb's handler (`_handle_*`) and the composite dispatches (`_dispatch_*`)
live here; `main()` routes to them. The exact end-to-end behavior of every verb
is pinned by the comprehensive surface suite driving the assembled CLI; this gate
holds that the handler surface is whole and that the two cleanly-isolable
handler behaviors hold when called directly: `run` returns the child's exit code
unchanged, and `pack` refuses an invalid invocation with exit 2. Writes VERBS_OK.

    python3 criteria/verbs_check.py
"""
import contextlib
import io
import os
import sys
import tempfile
from types import SimpleNamespace

SRC = "src" if os.path.isdir("src/reticuli") else "."
sys.path.insert(0, SRC)
from reticuli._cli import verbs

HANDLERS = ("_handle_help", "_handle_init", "_handle_completion", "_handle_hook",
            "_handle_run", "_handle_verify", "_handle_assess",
            "_handle_rebuild", "_handle_pull", "_handle_sign",
            "_handle_export", "_handle_record", "_handle_import")
DISPATCHES = ("_dispatch_pack", "_dispatch_audit", "_dispatch_status",
              "_dispatch_crosscheck")




# ==== seam block for verbs_check.py ====
# Paste into the check; call _seam() from its battery()/main.

# --- _cli/verbs.py: 19 seam names (0 value, 0 kind, 19 callable) ---
_SEAM__cli_verbs_VALUES = {
}
_SEAM__cli_verbs_KINDS = {}
_SEAM__cli_verbs_CALLABLES = ('_dispatch_audit', '_dispatch_crosscheck', '_dispatch_pack', '_dispatch_status', '_handle_assess', '_handle_completion', '_handle_export', '_handle_help', '_handle_hook', '_handle_import', '_handle_init', '_handle_pull', '_handle_rebuild', '_handle_record', '_handle_run', '_handle_sign', '_handle_verify')

def _seam() -> None:
    from reticuli._cli import verbs as _m__cli_verbs
    for _n, _v in _SEAM__cli_verbs_VALUES.items():
        assert getattr(_m__cli_verbs, _n) == _v, f'_cli/verbs.py seam {_n} changed'
    for _n in _SEAM__cli_verbs_KINDS:
        assert hasattr(_m__cli_verbs, _n), f'_cli/verbs.py must export {_n}'
    for _n in _SEAM__cli_verbs_CALLABLES:
        assert callable(getattr(_m__cli_verbs, _n, None)), f'_cli/verbs.py must export callable {_n}'


def battery() -> None:
    _seam()
    # the handler surface is whole -- a missing handler is a dead verb
    for name in HANDLERS + DISPATCHES:
        assert callable(getattr(verbs, name)), f"cli-verbs is missing {name}"

    d = tempfile.mkdtemp()
    try:
        # run returns the child's exit code UNCHANGED (the predicate contract)
        assert verbs._handle_run(
            SimpleNamespace(command=["exit 7"], workspace=d)) == 7, \
            "run passes the child's exit code through"
        assert verbs._handle_run(
            SimpleNamespace(command=["exit 0"], workspace=d)) == 0, \
            "and a passing child stays 0"

        # pack refuses an invalid invocation (accept without -o) with exit 2,
        # in words, before building anything
        args = SimpleNamespace(cmd="pack", path=d, name=None, root=None,
                               generated=None, gate=None, output=None, pytest=None,
                               accept=["OK"], into=None, force=False)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = verbs._dispatch_pack(args)
        assert rc == 2 and err.getvalue().startswith("ret: pack:") and "-o" in err.getvalue(), \
            f"pack --accept without -o is a usage error: rc={rc} {err.getvalue()!r}"

        # THE VERB COMPOSES (2026-10-09, keyholder-signed; from the
        # completeness sweep). The audit verb dispatches DEEP by default and
        # the shallow form is an explicit, spelled opt-down — behavior that
        # was correct but unpinned, so a regrown CLI could wire the verb to
        # the kernel's shallow primitive and the strongest everyday verdict
        # would silently stop composing. The witness is the usual one: a
        # composed claim whose component code is forged — its own gate blind,
        # only the composed audit can see it.
        import shutil
        import subprocess as _sp
        from reticuli import kernel as _k
        from reticuli import registry as _reg
        clib = os.path.join(d, "vclib"); os.makedirs(clib)
        with open(os.path.join(clib, "claim.toml"), "w") as f:
            f.write('[claim]\nname = "vclib"\ninputs = ["c.py"]\n\n'
                    '[[step]]\nkind = "produce"\noutput = "lib.py"\nclass = "generated"\n\n'
                    '[[step]]\nkind = "gate"\noutput = "VCL_OK"\nrun = "python3 c.py"\nclass = "validated"\n')
        with open(os.path.join(clib, "lib.py"), "w") as f:
            f.write("def val():\n    return 42\n")
        with open(os.path.join(clib, "c.py"), "w") as f:
            f.write("import sys\nsys.path.insert(0, '.')\nfrom lib import val\n"
                    "assert val() == 42\nopen('VCL_OK', 'w').write('ok\\n')\n")
        _sp.run("python3 c.py", shell=True, cwd=clib, check=True)
        rcl = _k.seal(clib)
        capp = os.path.join(d, "vcapp"); os.makedirs(capp)
        with open(os.path.join(capp, "claim.toml"), "w") as f:
            f.write('[claim]\nname = "vcapp"\ninputs = ["a.py"]\n\n'
                    '[[step]]\nkind = "produce"\noutput = "lib.py"\nclass = "generated"\nfrom = "vclib"\n\n'
                    '[[step]]\nkind = "produce"\noutput = "app.py"\nclass = "generated"\n\n'
                    '[[step]]\nkind = "gate"\noutput = "VCA_OK"\nrun = "python3 a.py"\nclass = "validated"\n')
        with open(os.path.join(capp, "lib.py"), "w") as f:
            f.write("def val():\n    return 42\n")
        with open(os.path.join(capp, "app.py"), "w") as f:
            f.write("from lib import val\n\n\ndef answer():\n    return val()\n")
        with open(os.path.join(capp, "a.py"), "w") as f:
            f.write("import sys\nsys.path.insert(0, '.')\nfrom app import answer\n"
                    "assert answer() == 42\nopen('VCA_OK', 'w').write('ok\\n')\n")
        _sp.run("python3 a.py", shell=True, cwd=capp, check=True)
        shutil.copytree(clib, os.path.join(capp, ".reticuli", "sealed", "vclib"))
        _reg.seal_with(capp, components=[{"input": "lib.py", "component": "vclib",
                                          "root": rcl["root"], "output": "lib.py"}])
        with open(os.path.join(capp, "lib.py"), "w") as f:   # the forgery
            f.write("def val():\n    return 42\nimport sys\n"
                    "if sys.argv and sys.argv[0].endswith('c.py'): raise SystemExit(1)\n")
        _k.seal(capp)
        def _audit_args(**kw):
            base = dict(cmd="audit", claim=capp, reuse=False, shallow=False,
                        no_strict=True, strict=False, trust="self",
                        json=False, verbose=False, color="never",
                        progress=False, quiet=True, mutants=None, record=None)
            base.update(kw)
            return SimpleNamespace(**base)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc_deep = verbs._dispatch_audit(_audit_args())
        assert rc_deep != 0, \
            "the audit verb composes by default: a forged component refuses"
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc_shallow = verbs._dispatch_audit(_audit_args(shallow=True))
        assert rc_shallow == 0, \
            "and --shallow is the explicit, honest opt-down (own gates only)"
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    battery()
    if os.path.isfile("reticuli.toml") or os.path.isfile("claim.toml"):
        with open("VERBS_OK", "w") as f:
            f.write("verbs-ok\n")
    print("verbs-ok")
