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
            "_handle_hooks", "_handle_run", "_handle_verify", "_handle_assess",
            "_handle_rebuild", "_handle_pull", "_handle_attest", "_handle_sign",
            "_handle_export", "_handle_record", "_handle_import")
DISPATCHES = ("_dispatch_pack", "_dispatch_audit", "_dispatch_status",
              "_dispatch_crosscheck")


def battery() -> None:
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
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    battery()
    if os.path.isfile("reticuli.toml") or os.path.isfile("claim.toml"):
        with open("VERBS_OK", "w") as f:
            f.write("verbs-ok\n")
    print("verbs-ok")
