"""The authoring on-ramp: an ordinary pytest project packs with one flag.

Lives in tests/ rather than the surface criterion because it needs pytest
installed, and criteria are stdlib-only; the surface criterion pins the
grammar, this exercises the behavior.
"""
import contextlib
import io
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))
from reticuli import cli, kernel


def _run(argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = cli.main(argv)
    return code, out.getvalue()


def _project(tmp_path):
    d = tmp_path / "proj"
    (d / "app").mkdir(parents=True)
    (d / "tests").mkdir()
    (d / "app" / "__init__.py").write_text("")
    (d / "app" / "mod.py").write_text("VALUE = 7\n")
    (d / "tests" / "test_mod.py").write_text(
        "import os, sys\n"
        "sys.path.insert(0, os.path.dirname(os.path.dirname("
        "os.path.dirname(os.path.abspath(__file__)))))\n"
        "sys.path.insert(0, os.getcwd())\n"
        "from app import mod\n\n\n"
        "def test_value():\n    assert mod.VALUE == 7\n")
    return str(d)


def test_pack_pytest_packs_an_ordinary_project(tmp_path, monkeypatch):
    # the gate's python3 must see pytest: put this interpreter's bin first on
    # the PATH the scrub keeps, which is what an activated venv does anyway
    monkeypatch.setenv("PATH", os.path.dirname(sys.executable)
                       + os.pathsep + os.environ.get("PATH", ""))
    d = _project(tmp_path)
    code, _ = _run(["pack", "proj", "--generated", "app/*.py",
                    "--pytest", "tests", "-C", d])
    assert code == 0, "one flag packs a pytest project"
    v = kernel.verify(d)
    assert v["ok"], "and the result is a sealed, fresh claim"
    recipe = kernel.load_recipe(d)
    ins = recipe["claim"]["inputs"]
    assert "tests/test_mod.py" in ins, "the suite is pinned: it is the claim"
    assert any(s.get("output") == "app/mod.py" for s in recipe.get("step", [])), \
        "the implementation is generated: it is free"


def test_pytest_flag_conflicts_with_gate(tmp_path):
    d = _project(tmp_path)
    code, _ = _run(["pack", "proj", "--generated", "app/*.py",
                    "--pytest", "tests", "--gate", "true", "--output", "OK",
                    "-C", d])
    assert code == 2, "--pytest replaces --gate/--output; both together refuse"
