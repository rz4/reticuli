"""The pinned cost envelope: ceilings the claim declares, enforced on M3.

Confidence, not identity: the format is specified in spec/claim-format.md
and the enforcement will be pinned in the kernel suite at the next revision;
these tests keep it honest in the meantime.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))
from reticuli import kernel

RECIPE = '''[claim]
name = "budgeted"
envelope = { usd = 1.0 }

[[step]]
kind = "produce"
output = "g.txt"
class = "generated"
request = "a greeting containing the word hello"

[[step]]
kind = "gate"
output = "V"
class = "validated"
run = "grep -qi hello g.txt && printf v > V"
'''


@pytest.fixture()
def machines(tmp_path):
    m1 = tmp_path / "m1"
    m1.mkdir()
    (m1 / "reticuli.toml").write_text(RECIPE)
    (m1 / "g.txt").write_text("hello, world\n")
    subprocess.run("grep -qi hello g.txt && printf v > V", shell=True,
                   cwd=m1, check=True)
    kernel.seal(str(m1))
    m2 = tmp_path / "m2"
    shutil.copytree(m1, m2)
    m3 = tmp_path / "m3"
    kernel.rebuild(str(m1), "printf 'hello again\\n' > g.txt", str(m3))
    return str(m1), str(m2), str(m3)


def _set_usd(claim, usd):
    with open(os.path.join(claim, kernel.LEDGER), "w") as f:
        f.write(json.dumps({"event": "oracle", "calls": 1, "usd": usd}) + "\n")


def test_within_the_envelope_passes(machines):
    m1, m2, m3 = machines
    _set_usd(m3, 0.5)
    r = kernel.crosscheck(m1, m2, m3)
    assert r["satisfied"] and r["cost"]["envelope"]["usd"]["within"] is True


def test_an_overrun_fails_the_test(machines):
    m1, m2, m3 = machines
    _set_usd(m3, 2.0)
    r = kernel.crosscheck(m1, m2, m3)
    assert not r["satisfied"]
    assert r["cost"]["envelope"]["usd"]["within"] is False
    assert r["equivalence"] and all(r["audited"].values()), \
        "only the envelope failed; the overrun is the whole story"


def test_an_unmeasured_declared_unit_is_incomplete(machines):
    m1, m2, m3 = machines
    with open(os.path.join(m3, kernel.LEDGER), "w") as f:
        f.write(json.dumps({"event": "oracle", "calls": 1}) + "\n")
    r = kernel.crosscheck(m1, m2, m3)
    assert not r["satisfied"] and r["verdict"] == "incomplete", \
        "a declared hard condition nobody measured cannot accept"
    assert r["cost"]["envelope"]["usd"]["within"] is None
    assert r["rejected"] == [], "and it is not a rejection either"


def test_no_declaration_no_envelope(tmp_path):
    m1 = tmp_path / "plain"
    m1.mkdir()
    (m1 / "reticuli.toml").write_text(RECIPE.replace(
        "envelope = { usd = 1.0 }\n", ""))
    (m1 / "g.txt").write_text("hello\n")
    subprocess.run("grep -qi hello g.txt && printf v > V", shell=True,
                   cwd=m1, check=True)
    kernel.seal(str(m1))
    m2 = tmp_path / "copy"
    shutil.copytree(m1, m2)
    m3 = tmp_path / "redo"
    kernel.rebuild(str(m1), "printf 'hello redo\\n' > g.txt", str(m3))
    r = kernel.crosscheck(str(m1), str(m2), str(m3))
    assert r["satisfied"] and r["cost"]["envelope"] is None


@pytest.mark.parametrize("bad,why", [
    ('envelope = "cheap"', "not a table"),
    ("envelope = { gpu_hours = 5 }", "unknown unit"),
    ("envelope = { usd = true }", "boolean"),
    ("envelope = { usd = -1.0 }", "negative"),
    ("envelope = { }", "empty"),
])
def test_a_damaged_envelope_refuses_at_parse(bad, why):
    d = tempfile.mkdtemp()
    try:
        with open(os.path.join(d, "reticuli.toml"), "w") as f:
            f.write(RECIPE.replace("envelope = { usd = 1.0 }", bad))
        with pytest.raises(kernel.ClaimError):
            kernel.load_recipe(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)
