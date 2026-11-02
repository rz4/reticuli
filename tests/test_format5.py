"""Format 5 (the APEIRON batch): carried files, constrains, assembles.

Three obligations the campaign measured, one format bump so older kernels
refuse the new vocabulary in words instead of silently under-enforcing it:

- `class = "carried"` — a file that ships but is never regrown: hashed into
  the root like a pinned output, copied byte-for-byte at rebuild, invisible
  to the producer (the campaign lost deployment/ and a README to the absence
  of this class).
- `[claim] constrains` — a pinned criterion declares which owned outputs it
  constrains, and the seal refuses a declaration over a supplied module
  (R33's refusable form).
- `[claim] assembles` — a claim whose gates judge the composition of other
  claims' shipped outputs, each member held to the root the assembly names.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reticuli import kernel


def _write(d, files):
    d.mkdir(parents=True, exist_ok=True)
    for name, body in files.items():
        p = d / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    return d


def _seal(d, files):
    _write(d, files)
    kernel.seal(str(d))
    return d


CARRIED = (
    '[claim]\nname = "ships"\nformat = 5\ninputs = ["check.py"]\n\n'
    '[[step]]\nkind = "produce"\noutput = "impl.py"\nclass = "generated"\n\n'
    '[[step]]\nkind = "produce"\noutput = "NOTES.md"\nclass = "carried"\n\n'
    '[[step]]\nkind = "gate"\noutput = "OK"\nclass = "validated"\n'
    'run = "python3 check.py && printf ok > OK"\n'
)
CARRIED_FILES = {
    "check.py": "from impl import answer\nassert answer == 42\n"
                "open('OK', 'w').write('ok')\n",
    "impl.py": "answer = 42\n",
    "NOTES.md": "how to deploy, in prose no criterion pins\n",
    "OK": "ok",
}


class TestTheFormatGate:
    def test_carried_below_format_5_refuses(self, tmp_path):
        d = _write(tmp_path / "c", {
            "reticuli.toml": CARRIED.replace("format = 5", "format = 4"),
            **CARRIED_FILES})
        with pytest.raises(kernel.ClaimError, match="format 5"):
            kernel.load_recipe(str(d))

    def test_constrains_and_assembles_below_format_5_refuse(self, tmp_path):
        for key in ('constrains = { "check.py" = ["impl.py"] }',
                    'assembles = ["m@' + "0" * 64 + '"]'):
            d = _write(tmp_path / key[:4], {"reticuli.toml": (
                f'[claim]\nname = "x"\nformat = 4\ninputs = ["check.py"]\n{key}\n\n'
                '[[step]]\nkind = "gate"\noutput = "OK"\nclass = "validated"\n'
                'run = "printf ok > OK"\n'), "check.py": "pass\n"})
            with pytest.raises(kernel.ClaimError, match="format 5"):
                kernel.load_recipe(str(d))

    def test_format_5_closes_the_class_vocabulary(self, tmp_path):
        d = _write(tmp_path / "v", {"reticuli.toml": (
            '[claim]\nname = "x"\nformat = 5\ninputs = []\n\n'
            '[[step]]\nkind = "produce"\noutput = "a.py"\nclass = "pined"\n\n'
            '[[step]]\nkind = "gate"\noutput = "OK"\nclass = "validated"\n'
            'run = "printf ok > OK"\n')})
        with pytest.raises(kernel.ClaimError, match="unknown class"):
            kernel.load_recipe(str(d))
        # format 4 keeps the loose reading: no sealed claim is stranded
        (d / "reticuli.toml").write_text(
            (d / "reticuli.toml").read_text().replace("format = 5", "format = 4"))
        kernel.load_recipe(str(d))

    def test_a_carried_gate_is_refused(self, tmp_path):
        d = _write(tmp_path / "g", {"reticuli.toml": (
            '[claim]\nname = "x"\nformat = 5\ninputs = []\n\n'
            '[[step]]\nkind = "gate"\noutput = "OK"\nclass = "carried"\n'
            'run = "printf ok > OK"\n')})
        with pytest.raises(kernel.ClaimError, match="earned, never copied"):
            kernel.load_recipe(str(d))


class TestCarried:
    def test_a_carried_file_is_in_the_root(self, tmp_path):
        d = _seal(tmp_path / "c", {"reticuli.toml": CARRIED, **CARRIED_FILES})
        assert kernel.verify(str(d))["ok"]
        (d / "NOTES.md").write_text("reworded prose\n")
        v = kernel.verify(str(d))
        assert not v["ok"] and "NOTES.md" in v["changed"]

    def test_a_carried_file_is_not_in_the_build_digest(self, tmp_path):
        d = _seal(tmp_path / "c", {"reticuli.toml": CARRIED, **CARRIED_FILES})
        before = kernel.build_digest(str(d))
        (d / "NOTES.md").write_text("other prose\n")
        assert kernel.build_digest(str(d)) == before

    def test_a_rebuild_carries_it_byte_identical_and_blind(self, tmp_path):
        d = _seal(tmp_path / "c", {"reticuli.toml": CARRIED, **CARRIED_FILES})
        producer = tmp_path / "producer.py"
        # the producer writes the generated output AND proves it was never
        # told about the carried file: RETICULI_OUTPUTS is the work list
        producer.write_text(
            "import json, os\n"
            "outputs = json.loads(os.environ['RETICULI_OUTPUTS'])\n"
            "assert outputs == ['impl.py'], outputs\n"
            "assert os.path.exists('NOTES.md'), 'carried bytes precede me'\n"
            "open('impl.py', 'w').write('answer = 42\\n')\n")
        r = kernel.rebuild(str(d), f"python3 {producer}", str(tmp_path / "m3"))
        assert r["root"] == kernel.read_manifest(str(d))["root"]
        assert (tmp_path / "m3" / "NOTES.md").read_bytes() \
            == (d / "NOTES.md").read_bytes()

    def test_a_producer_rewriting_a_carried_file_is_refused(self, tmp_path):
        d = _seal(tmp_path / "c", {"reticuli.toml": CARRIED, **CARRIED_FILES})
        producer = tmp_path / "producer.py"
        producer.write_text(
            "open('impl.py', 'w').write('answer = 42\\n')\n"
            "open('NOTES.md', 'w').write('improved prose\\n')\n")
        with pytest.raises(kernel.ClaimError, match="changed NOTES.md"):
            kernel.rebuild(str(d), f"python3 {producer}",
                           str(tmp_path / "m3"))


CONSTRAINS_FILES = {
    "check.py": "from impl import answer\nassert answer == 42\n"
                "open('OK', 'w').write('ok')\n",
    "impl.py": "answer = 42\n", "comp.py": "BASE = 2\n", "OK": "ok"}


class TestConstrains:
    RECIPE = (
        '[claim]\nname = "holds"\nformat = 5\ninputs = ["check.py"]\n'
        'constrains = {{ "check.py" = ["{target}"] }}\n\n'
        '[[step]]\nkind = "produce"\noutput = "impl.py"\nclass = "generated"\n\n'
        '[[step]]\nkind = "produce"\noutput = "comp.py"\nclass = "generated"\n'
        'from = "lower"\n\n'
        '[[step]]\nkind = "gate"\noutput = "OK"\nclass = "validated"\n'
        'run = "python3 check.py && printf ok > OK"\n'
    )

    def test_an_owned_target_seals(self, tmp_path):
        d = _write(tmp_path / "ok", {
            "reticuli.toml": self.RECIPE.format(target="impl.py"), **CONSTRAINS_FILES})
        kernel.seal(str(d))
        assert kernel.verify(str(d))["ok"]

    def test_a_supplied_target_refuses_naming_the_owner(self, tmp_path):
        d = _write(tmp_path / "r33", {
            "reticuli.toml": self.RECIPE.format(target="comp.py"), **CONSTRAINS_FILES})
        with pytest.raises(kernel.ClaimError,
                           match="supplied by 'lower'.*belongs there"):
            kernel.seal(str(d))

    def test_a_phantom_target_refuses(self, tmp_path):
        d = _write(tmp_path / "ghost", {
            "reticuli.toml": self.RECIPE.format(target="nowhere.py"),
            **CONSTRAINS_FILES})
        with pytest.raises(kernel.ClaimError, match="no produce step"):
            kernel.seal(str(d))

    def test_a_key_that_is_not_an_input_refuses_at_parse(self, tmp_path):
        d = _write(tmp_path / "key", {
            "reticuli.toml": self.RECIPE.format(target="impl.py").replace(
                '"check.py" = ', '"other.py" = '), **CONSTRAINS_FILES})
        with pytest.raises(kernel.ClaimError, match="not a declared input"):
            kernel.load_recipe(str(d))


def _member(tmp_path):
    return _seal(tmp_path / "member", {
        "reticuli.toml": (
            '[claim]\nname = "member"\ninputs = ["check_m.py"]\n\n'
            '[[step]]\nkind = "produce"\noutput = "lib.py"\nclass = "generated"\n\n'
            '[[step]]\nkind = "gate"\noutput = "MOK"\nclass = "validated"\n'
            'run = "python3 check_m.py && printf ok > MOK"\n'),
        "check_m.py": "from lib import base\nassert base() == 2\n"
                      "open('MOK', 'w').write('ok')\n",
        "lib.py": "def base():\n    return 2\n",
        "MOK": "ok",
    })


def _assembly(tmp_path, member, member_root):
    d = _write(tmp_path / "assembly", {
        "reticuli.toml": (
            '[claim]\nname = "assembly"\nformat = 5\ninputs = ["check_a.py"]\n'
            f'assembles = ["member@{member_root}"]\n\n'
            '[[step]]\nkind = "produce"\noutput = "glue.py"\nclass = "generated"\n\n'
            '[[step]]\nkind = "gate"\noutput = "AOK"\nclass = "validated"\n'
            'run = "python3 check_a.py && printf ok > AOK"\n'),
        # the composition edge no member room can see: glue calls across the
        # import seam into the member's shipped module
        "check_a.py": "from glue import doubled\nassert doubled() == 4\n"
                      "open('AOK', 'w').write('ok')\n",
        "glue.py": "from lib import base\n\ndef doubled():\n"
                   "    return base() * 2\n",
        "AOK": "ok",
    })
    drawer = d / ".reticuli" / "sealed"
    drawer.mkdir(parents=True, exist_ok=True)
    import shutil
    shutil.copytree(member, drawer / "member")
    kernel.seal(str(d))
    return d


class TestAssembles:
    def test_the_gate_judges_the_composition(self, tmp_path):
        member = _member(tmp_path)
        member_root = kernel.read_manifest(str(member))["root"]
        assembly = _assembly(tmp_path, member, member_root)
        r = kernel.audit(str(assembly))
        assert r["ok"], r

    def test_a_member_off_its_declared_root_refuses_the_fold(self, tmp_path):
        member = _member(tmp_path)
        member_root = kernel.read_manifest(str(member))["root"]
        assembly = _assembly(tmp_path, member, member_root)
        # the member's criterion moves underneath the assembly's declaration
        staged = assembly / ".reticuli" / "sealed" / "member"
        (staged / "check_m.py").write_text(
            "from lib import base\nassert base() == 2\nassert base() != 3\n"
            "open('MOK', 'w').write('ok')\n")
        with pytest.raises(kernel.ClaimError, match="recomputes to"):
            kernel.audit(str(assembly))

    def test_repinning_the_member_moves_the_assembly_root(self, tmp_path):
        member = _member(tmp_path)
        member_root = kernel.read_manifest(str(member))["root"]
        assembly = _assembly(tmp_path, member, member_root)
        before = kernel.read_manifest(str(assembly))["root"]
        other = "f" * 64
        recipe = (assembly / "reticuli.toml").read_text()
        (assembly / "reticuli.toml").write_text(
            recipe.replace(member_root, other))
        kernel.seal(str(assembly))
        assert kernel.read_manifest(str(assembly))["root"] != before, \
            "the member roots are inside the assembly's own root"

    def test_an_unregistered_member_names_the_remedy(self, tmp_path):
        member = _member(tmp_path)
        member_root = kernel.read_manifest(str(member))["root"]
        assembly = _assembly(tmp_path, member, member_root)
        import shutil
        shutil.rmtree(assembly / ".reticuli" / "sealed" / "member")
        with pytest.raises(kernel.ClaimError, match="ret pull"):
            kernel.audit(str(assembly))

    def test_a_collision_with_the_assemblys_own_file_refuses(self, tmp_path):
        member = _member(tmp_path)
        member_root = kernel.read_manifest(str(member))["root"]
        assembly = _assembly(tmp_path, member, member_root)
        recipe = (assembly / "reticuli.toml").read_text().replace(
            'output = "glue.py"', 'output = "lib.py"')
        (assembly / "reticuli.toml").write_text(recipe)
        (assembly / "lib.py").write_text("def base():\n    return 3\n")
        kernel.seal(str(assembly))
        with pytest.raises(kernel.ClaimError, match="one path, one owner"):
            kernel.audit(str(assembly))


class TestPackCarried:
    def test_pack_declares_carried_and_the_claim_round_trips(self, tmp_path, capsys):
        from reticuli import pack
        d = _write(tmp_path / "p", {
            "impl.py": "answer = 42\n",
            "check.py": "from impl import answer\nassert answer == 42\n"
                        "open('OK', 'w').write('ok')\n",
            "deploy.sh": "echo ship it\n",
        })
        r = pack.pack(str(d), "shipit", ["impl.py"], ["check.py"],
                      "python3 check.py && printf ok > OK", "OK",
                      carried=["deploy.sh"])
        assert r["ok"]
        err = capsys.readouterr().err
        assert "format 5" in err
        recipe = kernel.load_recipe(str(d))
        carried = [s for s in recipe["step"] if s.get("class") == "carried"]
        assert [s["output"] for s in carried] == ["deploy.sh"]
        assert kernel.verify(str(d))["ok"]

    def test_pack_names_the_files_in_no_class(self, tmp_path, capsys):
        from reticuli import pack
        d = _write(tmp_path / "p", {
            "impl.py": "answer = 42\n",
            "check.py": "from impl import answer\nassert answer == 42\n"
                        "open('OK', 'w').write('ok')\n",
            "orphan.cfg": "forgotten\n",
        })
        pack.pack(str(d), "noisy", ["impl.py"], ["check.py"],
                  "python3 check.py && printf ok > OK", "OK")
        err = capsys.readouterr().err
        assert "orphan.cfg" in err and "--carried" in err
