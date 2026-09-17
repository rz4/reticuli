"""Identity works on any platform; judging refuses off POSIX, in words.

The kernel uses process groups, sh, and platform sandboxes to run gates --
none of it exists on Windows. Rather than a traceback halfway through a
verdict, every judging entry point refuses in band, while the identity
computation (root, seal, verify) stays platform-free.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))
from reticuli import kernel

FIXTURE = '''[claim]
name = "anywhere"

[[step]]
kind = "gate"
output = "V"
class = "validated"
run = "printf v > V"
'''


@pytest.fixture()
def claim(tmp_path):
    d = tmp_path / "claim"
    d.mkdir()
    (d / "reticuli.toml").write_text(FIXTURE)
    (d / "V").write_text("v")
    kernel.seal(str(d))
    return str(d)


def test_identity_is_platform_free(claim, monkeypatch):
    monkeypatch.setattr(kernel.os, "name", "nt")
    assert kernel.verify(claim)["ok"], "verify works anywhere"
    assert kernel.root(kernel.load_recipe(claim), claim), "so does the root"


def test_judging_refuses_off_posix(claim, monkeypatch):
    monkeypatch.setattr(kernel.os, "name", "nt")
    for judge in (
        lambda: kernel.run_gate("printf v > V", claim, kernel.load_recipe(claim)),
        lambda: kernel.audit(claim),
        lambda: kernel.rebuild(claim, "true", claim + "-m3"),
        lambda: kernel.mutation_score(claim, max_mutants=1),
    ):
        with pytest.raises(kernel.ClaimError, match="POSIX"):
            judge()
