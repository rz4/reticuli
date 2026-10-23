"""Materializing bytes over bytes must not leave a gate judging the old ones.

CPython keys a `__pycache__` entry on the source's (mtime seconds, size), so
replacing a file with same-sized content inside the same second is invisible
to the import system: the next import hands back the bytes that used to be
there. Every verb that writes a file over an existing one is exposed —
`pull` wiring a component into a dependent, the launcher writing regrown
outputs back over a project, held-out case staging — and the failure mode is
the worst available, a gate passing on code that is no longer present.

Found while building the no-argument `pull`: a one-byte refresh of a pinned
table sailed through the gate that pins exactly that byte. The fix lives at
the one chokepoint those verbs share rather than at each call site, and these
tests pin it there, at the level where it is a property of copying rather
than a property of recomposition.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reticuli import _util


def _cached(module: Path) -> list[Path]:
    cache = module.parent / "__pycache__"
    if not cache.is_dir():
        return []
    return sorted(p for p in cache.iterdir() if p.suffix in (".pyc", ".pyo"))


def _compile(module: Path) -> Path:
    """Import the module in a child so a real cache entry lands beside it."""
    import subprocess
    subprocess.run(
        [sys.executable, "-c", f"import {module.stem}"],
        cwd=str(module.parent), check=True, capture_output=True)
    entries = _cached(module)
    assert entries, "the fixture needs a real bytecode cache to invalidate"
    return entries[0]


class TestTheCacheIsInvalidated:
    def test_a_same_size_replacement_drops_the_cache(self, tmp_path):
        module = tmp_path / "table.py"
        module.write_text("COST = 7\n")
        _compile(module)
        # same length, same second: the two facts that make this invisible
        replacement = tmp_path / "other.py"
        replacement.write_text("COST = 8\n")
        _util.copy_into(str(replacement), str(module))
        assert _cached(module) == [], "a replaced source keeps no stale cache"

    def test_a_child_process_reads_the_new_bytes(self, tmp_path):
        import subprocess
        module = tmp_path / "table.py"
        module.write_text("COST = 7\n")
        _compile(module)
        replacement = tmp_path / "other.py"
        replacement.write_text("COST = 8\n")
        # the real test of the real hazard: what a gate would see
        _util.copy_into(str(replacement), str(module))
        out = subprocess.run(
            [sys.executable, "-c", "import table; print(table.COST)"],
            cwd=str(tmp_path), check=True, capture_output=True, text=True)
        assert out.stdout.strip() == "8", \
            "a gate must judge the bytes present, not the bytes cached"

    def test_a_sibling_sharing_the_prefix_is_left_alone(self, tmp_path):
        module = tmp_path / "table.py"
        sibling = tmp_path / "table_helper.py"
        module.write_text("COST = 7\n")
        sibling.write_text("HELPER = 1\n")
        _compile(module)
        _compile(sibling)
        kept = [p.name for p in _cached(sibling) if "table_helper" in p.name]
        assert kept, "the fixture needs the sibling cached"
        _util.drop_bytecode(str(module))
        after = [p.name for p in _cached(sibling) if "table_helper" in p.name]
        assert after == kept, \
            "invalidation is per module; a name-prefix neighbour is not ours"

    def test_the_legacy_side_by_side_pyc_goes_too(self, tmp_path):
        module = tmp_path / "old.py"
        module.write_text("VALUE = 1\n")
        legacy = tmp_path / "old.pyc"
        legacy.write_bytes(b"stale")
        _util.drop_bytecode(str(module))
        assert not legacy.exists()

    def test_a_non_python_file_is_copied_untouched(self, tmp_path):
        data = tmp_path / "weights.bin"
        data.write_bytes(b"\x00\x01")
        target = tmp_path / "copy.bin"
        _util.copy_into(str(data), str(target))
        assert target.read_bytes() == b"\x00\x01"

    def test_no_cache_beside_the_file_is_not_an_error(self, tmp_path):
        module = tmp_path / "fresh.py"
        module.write_text("X = 1\n")
        _util.drop_bytecode(str(module))      # nothing to drop
        assert module.read_text() == "X = 1\n"

    def test_an_unwritable_cache_does_not_fail_the_copy(self, tmp_path):
        # invalidation is best-effort: a cache we cannot clear is a risk to
        # report, never a reason to refuse to wire a component
        module = tmp_path / "table.py"
        module.write_text("COST = 7\n")
        _compile(module)
        cache = module.parent / "__pycache__"
        mode = cache.stat().st_mode
        os.chmod(cache, 0o500)                # no writes: removal will fail
        try:
            _util.drop_bytecode(str(module))
        finally:
            os.chmod(cache, mode)
        assert module.read_text() == "COST = 7\n"


class TestTheVerbsThatMaterialize:
    def test_pull_refreshes_what_a_gate_will_import(self, tmp_path):
        """The field case: a component's bytes change, `ret pull` wires the
        new ones in, and the dependent's gate must see them."""
        import subprocess

        from reticuli import kernel, pack, registry
        comp = tmp_path / "comp"
        comp.mkdir()
        (comp / "table.py").write_text("COST = 7\n")
        (comp / "check.py").write_text(
            "from table import COST\nassert COST in (7, 8)\n"
            "open('OK', 'w').write('ok')\n")
        pack.pack(str(comp), "low", ["table.py"], ["check.py"],
                  "python3 check.py && printf ok > OK", "OK")

        ws = tmp_path / "upper"
        ws.mkdir()
        registry.pull(str(comp), str(ws))
        subprocess.run([sys.executable, "-c", "import table"],
                       cwd=str(ws), check=True, capture_output=True)
        assert _cached(ws / "table.py"), "the fixture needs a stale cache"

        (comp / "table.py").write_text("COST = 8\n")   # same size, new bytes
        kernel.seal(str(comp))
        for store in ("sealed", "signed"):
            import shutil
            shutil.rmtree(ws / ".reticuli" / store / "low", ignore_errors=True)
        registry.pull(str(comp), str(ws))

        out = subprocess.run(
            [sys.executable, "-c", "import table; print(table.COST)"],
            cwd=str(ws), check=True, capture_output=True, text=True)
        assert out.stdout.strip() == "8", \
            "the dependent imports what pull actually wired in"
