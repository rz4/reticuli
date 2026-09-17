"""The declared environment: a hash-pinned lockfile, furnished before gates.

Confidence, not identity: the format is specified in spec/claim-format.md
and the enforcement will be pinned in the kernel suite at the next revision.
The tests build their own one-module wheel, so furnishing is exercised
offline and every installed byte is named by its hash.
"""
import hashlib
import os
import shutil
import sys
import zipfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))
from reticuli import kernel

WHEEL = "envprobe-1.0-py3-none-any.whl"

RECIPE = f'''[claim]
name = "furnished"
environment = "requirements.lock"
inputs = ["check_env.py", "{WHEEL}"]

[[step]]
kind = "produce"
output = "out.txt"
class = "generated"
request = "any text"

[[step]]
kind = "gate"
output = "OK"
class = "validated"
run = "python3 check_env.py"
'''

CHECK = '''import envprobe
assert envprobe.VALUE == 42, "the furnished package answers"
with open("OK", "w", encoding="utf-8") as f:
    f.write("ok\\n")
'''


def build_wheel(where) -> str:
    """A minimal, deterministic wheel: one module, no install-time code."""
    path = os.path.join(where, WHEEL)
    info = "envprobe-1.0.dist-info"
    members = [
        ("envprobe/__init__.py", "VALUE = 42\n"),
        (f"{info}/METADATA", "Metadata-Version: 2.1\nName: envprobe\nVersion: 1.0\n"),
        (f"{info}/WHEEL", ("Wheel-Version: 1.0\nGenerator: reticuli-tests\n"
                           "Root-Is-Purelib: true\nTag: py3-none-any\n")),
        (f"{info}/RECORD", ("envprobe/__init__.py,,\n"
                            f"{info}/METADATA,,\n{info}/WHEEL,,\n{info}/RECORD,,\n")),
    ]
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, content in members:
            entry = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            z.writestr(entry, content)
    return path


def sha256(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


@pytest.fixture()
def cache(tmp_path, monkeypatch):
    where = tmp_path / "env-cache"
    monkeypatch.setenv("RETICULI_ENV_CACHE", str(where))
    return where


@pytest.fixture()
def claim(tmp_path):
    d = tmp_path / "claim"
    d.mkdir()
    wheel = build_wheel(str(d))
    (d / "requirements.lock").write_text(
        f"./{WHEEL} --hash=sha256:{sha256(wheel)}\n")
    (d / "reticuli.toml").write_text(RECIPE)
    (d / "check_env.py").write_text(CHECK)
    (d / "out.txt").write_text("anything\n")
    (d / "OK").write_text("ok\n")
    kernel.seal(str(d))
    return str(d)


def test_audit_furnishes_the_room(claim, cache):
    r = kernel.audit(claim)
    assert r["ok"], r
    assert r["gates"][0]["status"] == "ok"
    assert os.path.isdir(cache), "the furnished venv landed in the cache"


def test_the_environment_is_identity(claim, cache):
    before = kernel.verify(claim)["root"]
    with open(os.path.join(claim, "requirements.lock"), "a") as f:
        f.write("# a different environment\n")
    after = kernel.verify(claim)
    assert not after["ok"] and after["recomputed"] != before, \
        "editing the lockfile moves the root: dependency versions decide"


def test_a_wrong_hash_is_an_environment_failure(claim, cache, tmp_path):
    bad = tmp_path / "bad"
    shutil.copytree(claim, bad)
    lock = bad / "requirements.lock"
    text = lock.read_text()
    honest = text.split("sha256:")[1][:64]
    lock.write_text(text.replace(honest, "0" * 64))
    kernel.seal(str(bad))
    r = kernel.audit(str(bad))
    assert not r["ok"]
    assert r["gates"][0]["status"] == "environment", \
        "an unfurnishable room is untested, never disproven"
    assert "environment" in r["environment"][0]


def test_the_cache_is_reused(claim, cache):
    assert kernel.audit(claim)["ok"]
    rooms = os.listdir(cache)
    assert kernel.audit(claim)["ok"]
    assert os.listdir(cache) == rooms, "one lockfile digest, one venv"


def test_rebuild_furnishes_for_producer_and_gates(claim, cache, tmp_path):
    m3 = tmp_path / "m3"
    out = kernel.rebuild(claim, "printf 'regrown\\n' > out.txt", str(m3))
    assert out["root"] == kernel.verify(claim)["root"]


def test_recipe_refusals(tmp_path):
    d = tmp_path / "bad"
    d.mkdir()
    (d / "reticuli.toml").write_text('[claim]\nname = "x"\nenvironment = 7\n')
    with pytest.raises(kernel.ClaimError):
        kernel.load_recipe(str(d))
    (d / "reticuli.toml").write_text(
        '[claim]\nname = "x"\nenvironment = "missing.lock"\n')
    with pytest.raises(kernel.ClaimError):
        kernel.root(kernel.load_recipe(str(d)), str(d))


def test_the_scrub_survives_furnishing(claim, cache, monkeypatch):
    # furnishing adds one PATH entry and nothing else: an inherited secret
    # still never reaches a gate
    monkeypatch.setenv("RETICULI_LEAK_PROBE", "s3cr3t-not-real")
    out = kernel.run_gate('printf "%s" "${RETICULI_LEAK_PROBE:-clean}" > leak.txt',
                          claim, kernel.load_recipe(claim),
                          extra_path=os.path.join(str(cache), "nowhere"))
    assert out["status"] == "ok"
    with open(os.path.join(claim, "leak.txt")) as f:
        assert f.read() == "clean"
