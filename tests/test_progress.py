"""kernel.audit's progress callback: presentation plumbing, nothing more.

The callback narrates a long audit (gate i of n, by name) for a caller that
wants a live line. It must fire once per declared gate, in order, and its
absence must change nothing — the default is None and the audit result is
byte-identical either way.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))
from reticuli import kernel


def _claim(tmp_path):
    (tmp_path / "reticuli.toml").write_text(
        '[claim]\nname = "p"\ninputs = ["a.txt"]\n\n'
        '[[step]]\nkind = "gate"\noutput = "V1"\nclass = "validated"\n'
        'run = "grep -q x a.txt && printf v > V1"\n\n'
        '[[step]]\nkind = "gate"\noutput = "V2"\nclass = "validated"\n'
        'run = "printf v > V2"\n')
    (tmp_path / "a.txt").write_text("x\n")
    (tmp_path / "V1").write_text("v")
    (tmp_path / "V2").write_text("v")
    kernel.seal(str(tmp_path))
    return str(tmp_path)


def test_progress_fires_per_gate_in_order(tmp_path):
    d = _claim(tmp_path)
    seen = []
    r = kernel.audit(d, progress=lambda i, n, name: seen.append((i, n, name)))
    assert r["ok"]
    assert seen == [(1, 2, "V1"), (2, 2, "V2")], seen


def test_no_callback_changes_nothing(tmp_path):
    d = _claim(tmp_path)
    with_cb = kernel.audit(d, progress=lambda *a: None)
    without = kernel.audit(d)
    for k in ("ok", "claim_ok", "root"):
        assert with_cb[k] == without[k]
    assert [g["output"] for g in with_cb["gates"]] == \
           [g["output"] for g in without["gates"]]
