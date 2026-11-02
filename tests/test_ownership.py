"""R33 from the APEIRON campaign: ownership is a property audit can see.

A claim handed a module (`from = "<component>"`) validates its producer's own
copy of that file, and assembly discards that copy for the owning room's. A
pinned criterion asserting a property of a supplied module therefore
constrains bytes that never ship — the campaign's single largest failure
class (11 of 50 upstream-test failures). These tests pin the warning lane:
audit names every pinned criterion whose imports reach a supplied module,
names the owning component, and never refuses over it.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reticuli import kernel


def _seal(d, recipe, files):
    d.mkdir(parents=True, exist_ok=True)
    (d / "reticuli.toml").write_text(recipe)
    for name, body in files.items():
        path = d / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
    kernel.seal(str(d))
    return d


SUPPLIED = (
    '[claim]\nname = "dependent"\ninputs = ["check.py"]\n\n'
    '[[step]]\nkind = "produce"\noutput = "impl.py"\nclass = "generated"\n\n'
    '[[step]]\nkind = "produce"\noutput = "comp.py"\nclass = "generated"\n'
    'from = "lower-layer"\n\n'
    '[[step]]\nkind = "gate"\noutput = "OK"\nclass = "validated"\n'
    'run = "python3 check.py && printf ok > OK"\n'
)

FILES = {
    "impl.py": "answer = 42\n",
    "comp.py": "BASE = 2\n",
    "OK": "ok",
}


class TestOwnershipCrossings:
    def test_a_criterion_importing_a_supplied_module_is_named(self, tmp_path):
        claim = _seal(tmp_path / "claim", SUPPLIED, {
            **FILES,
            # asserts a property of comp.py — the latent R33: comp.py's
            # shipped bytes are the lower layer's, not this copy
            "check.py": "import comp\nfrom impl import answer\n"
                        "assert comp.BASE == 2 and answer == 42\n"
                        "open('OK', 'w').write('ok')\n",
        })
        crossings = kernel.ownership(str(claim))
        assert crossings == [{"criterion": "check.py", "module": "comp.py",
                              "component": "lower-layer"}]

    def test_a_criterion_touching_only_owned_modules_is_silent(self, tmp_path):
        claim = _seal(tmp_path / "claim", SUPPLIED, {
            **FILES,
            "check.py": "from impl import answer\nassert answer == 42\n"
                        "open('OK', 'w').write('ok')\n",
        })
        assert kernel.ownership(str(claim)) == []

    def test_a_claim_supplied_nothing_is_silent(self, tmp_path):
        plain = (
            '[claim]\nname = "plain"\ninputs = ["check.py"]\n\n'
            '[[step]]\nkind = "produce"\noutput = "impl.py"\nclass = "generated"\n\n'
            '[[step]]\nkind = "gate"\noutput = "OK"\nclass = "validated"\n'
            'run = "python3 check.py && printf ok > OK"\n'
        )
        claim = _seal(tmp_path / "claim", plain, {
            "impl.py": "answer = 42\n", "OK": "ok",
            "check.py": "from impl import answer\nassert answer == 42\n"
                        "open('OK', 'w').write('ok')\n",
        })
        assert kernel.ownership(str(claim)) == []

    def test_from_package_import_module_reaches_a_supplied_submodule(self, tmp_path):
        # `from pkg import mod` imports the module itself, not an attribute;
        # the prototype's regex missed this form and audit must not
        recipe = SUPPLIED.replace('output = "comp.py"', 'output = "pkg/mod.py"')
        claim = _seal(tmp_path / "claim", recipe, {
            "impl.py": "answer = 42\n",
            "pkg/__init__.py": "",
            "pkg/mod.py": "BASE = 2\n",
            "OK": "ok",
            "check.py": "from pkg import mod\nfrom impl import answer\n"
                        "assert mod.BASE == 2 and answer == 42\n"
                        "open('OK', 'w').write('ok')\n",
        })
        crossings = kernel.ownership(str(claim))
        assert {(w["criterion"], w["module"]) for w in crossings} \
            == {("check.py", "pkg/mod.py")}

    def test_an_unparsable_criterion_is_skipped_not_fatal(self, tmp_path):
        claim = _seal(tmp_path / "claim", SUPPLIED, {
            **FILES,
            "check.py": "import comp ... this is not python\n",
        })
        assert kernel.ownership(str(claim)) == []


class TestAuditCarriesTheWarning:
    def test_the_audit_result_names_the_crossing_and_still_passes(self, tmp_path):
        claim = _seal(tmp_path / "claim", SUPPLIED, {
            **FILES,
            "check.py": "import comp\nfrom impl import answer\n"
                        "assert comp.BASE == 2 and answer == 42\n"
                        "open('OK', 'w').write('ok')\n",
        })
        r = kernel.audit(str(claim))
        assert r["ok"], "the warning lane must never refuse"
        assert r["ownership"] == [{"criterion": "check.py", "module": "comp.py",
                                   "component": "lower-layer"}]

    def test_a_clean_claim_audits_with_an_empty_lane(self, tmp_path):
        claim = _seal(tmp_path / "claim", SUPPLIED, {
            **FILES,
            "check.py": "from impl import answer\nassert answer == 42\n"
                        "open('OK', 'w').write('ok')\n",
        })
        r = kernel.audit(str(claim))
        assert r["ok"] and r["ownership"] == []
