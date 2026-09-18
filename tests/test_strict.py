"""The strict jail: a stranger's gate must not read your files.

Backend-dependent by nature: the masking assertions need a real jail and
skip honestly where none exists (typical Linux CI); the file-growth ceiling
is enforced by rlimit and holds on every POSIX host.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))
from reticuli import kernel

BACKEND = kernel.sandbox_backend()
JAILED = BACKEND in ("seatbelt", "bubblewrap")


@pytest.mark.skipif(not JAILED, reason="no real jail on this host")
def test_strict_masks_the_home_ground(tmp_path):
    sentinel = os.path.join(os.path.expanduser("~"), ".reticuli-strict-probe")
    with open(sentinel, "w", encoding="utf-8") as f:
        f.write("a file the stranger's gate must not read\n")
    try:
        probe = f'cat "{sentinel}" > got.txt'
        standard = kernel.run_gate(probe, str(tmp_path))
        assert standard["status"] == "ok", \
            "the standard tier reads it -- which is why the threat model says so"
        strict = kernel.run_gate(probe, str(tmp_path), strict=True)
        assert strict["status"] != "ok", "strict masks the user's own files"
    finally:
        os.remove(sentinel)


def test_strict_still_reads_the_workspace(tmp_path):
    (tmp_path / "input.txt").write_text("hello\n")
    out = kernel.run_gate("cat input.txt > V", str(tmp_path), strict=True)
    assert out["status"] == "ok", "the room itself stays readable and writable"


def test_strict_caps_file_growth(tmp_path, monkeypatch):
    monkeypatch.setenv("RETICULI_STRICT_FSIZE", "1000000")
    grow = "python3 -c \"open('big','wb').write(b'x'*3000000)\""
    strict = kernel.run_gate(grow, str(tmp_path), strict=True)
    assert strict["status"] != "ok", "three megabytes into a one-megabyte ceiling dies"
    standard = kernel.run_gate(grow, str(tmp_path))
    assert standard["status"] == "ok", "the ceiling is strict-tier policy, not standard"


def test_cli_audit_defaults_to_strict(tmp_path, monkeypatch):
    # judging is the adversarial posture: from the CLI, audit runs the
    # strict jail unless --no-strict opts down. (inspect, which used to
    # carry this default, is retired; audit inherited its posture.)
    d = tmp_path / "claim"
    d.mkdir()
    (d / "reticuli.toml").write_text(
        '[claim]\nname = "handed"\n\n[[step]]\nkind = "gate"\noutput = "V"\n'
        'class = "validated"\nrun = "printf v > V"\n')
    (d / "V").write_text("v")
    kernel.seal(str(d))
    from reticuli import cli
    seen = []
    real = kernel.audit

    def capture(claimdir, *a, **kw):
        seen.append(kw.get("strict"))
        return real(claimdir, *a, **kw)
    monkeypatch.setattr(kernel, "audit", capture)
    assert cli.main(["audit", str(d), "--shallow"]) == 0
    assert cli.main(["audit", str(d), "--shallow", "--no-strict"]) == 0
    assert seen == [True, False], seen
