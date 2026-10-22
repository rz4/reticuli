"""The fixes fed back from the first external campaign.

Each test pins one behaviour the campaign showed was missing: a rebuild must
not report success after minting a different claim (pinned produce outputs
join the watched set, and the result names the source root); a recorded
proof is trusted only while the claim still has the root it proved; mutation
sampling skips component-supplied files, whose own claims judge them; pack
warns when a dependent declares only part of what a component supplies; and
the per-file account shows pinned produce outputs.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reticuli import kernel, pack
from reticuli._cli import views


def _seal(d, recipe, files):
    d.mkdir(parents=True, exist_ok=True)
    (d / "reticuli.toml").write_text(recipe)
    for name, body in files.items():
        path = d / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
    kernel.seal(str(d))
    return d


PLAIN = (
    '[claim]\nname = "plain"\ninputs = ["check.py"]\n\n'
    '[[step]]\nkind = "produce"\noutput = "impl.py"\nclass = "generated"\n\n'
    '[[step]]\nkind = "gate"\noutput = "OK"\nclass = "validated"\n'
    'run = "python3 check.py && printf ok > OK"\n'
)

WITH_PINNED_OUTPUT = (
    '[claim]\nname = "tabled"\ninputs = ["check.py"]\n\n'
    '[[step]]\nkind = "produce"\noutput = "table.py"\nclass = "pinned"\n\n'
    '[[step]]\nkind = "produce"\noutput = "impl.py"\nclass = "generated"\n\n'
    '[[step]]\nkind = "gate"\noutput = "OK"\nclass = "validated"\n'
    'run = "python3 check.py && printf ok > OK"\n'
)

CHECK = "from impl import answer\nassert answer == 42\nopen('OK', 'w').write('ok')\n"
TABLE_CHECK = (
    "from impl import answer\nfrom table import COST\n"
    "assert answer == 42 and COST == 7\nopen('OK', 'w').write('ok')\n"
)


# ---------------------------------------------------------------------------
# R11: a rebuild may not quietly mint a different claim
# ---------------------------------------------------------------------------
class TestRebuildWatchesPinnedOutputs:
    def _claim(self, tmp_path):
        return _seal(
            tmp_path / "claim",
            WITH_PINNED_OUTPUT,
            {
                "check.py": TABLE_CHECK,
                "table.py": "COST = 7\n",
                "impl.py": "answer = 42\n",
                "OK": "ok",
            },
        )

    def test_a_producer_rewriting_a_pinned_output_refuses(self, tmp_path):
        claim = self._claim(tmp_path)
        producer = tmp_path / "producer.py"
        # writes the generated file AND rewrites the pinned table so the
        # gate still passes -- before the fix this sealed a different claim
        # and reported `rebuilt`
        producer.write_text(
            "open('impl.py', 'w').write('answer = 42\\n')\n"
            "open('table.py', 'w').write('COST = 7  # reworded\\n')\n"
        )
        with pytest.raises(kernel.ClaimError, match="the producer changed table.py"):
            kernel.rebuild(
                str(claim),
                f"python3 {producer}",
                str(tmp_path / "m3"),
            )

    def test_an_honest_rebuild_reports_the_source_root_it_reached(self, tmp_path):
        claim = self._claim(tmp_path)
        producer = tmp_path / "producer.py"
        producer.write_text("open('impl.py', 'w').write('answer = 6 * 7\\n')\n")
        result = kernel.rebuild(
            str(claim), f"python3 {producer}", str(tmp_path / "m3")
        )
        source = kernel.read_manifest(str(claim))["root"]
        assert result["source_root"] == source
        assert result["root"] == source, (
            "with every pinned byte watched, reaching any other root should "
            "be impossible rather than merely detectable"
        )


# ---------------------------------------------------------------------------
# R12: a proof is trusted only while the proved root is the current root
# ---------------------------------------------------------------------------
class TestProofStaleness:
    def _proved_claim(self, tmp_path):
        claim = _seal(
            tmp_path / "claim",
            PLAIN,
            {"check.py": CHECK, "impl.py": "answer = 42\n", "OK": "ok"},
        )
        manifest_path = claim / ".reticuli" / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["proof"] = {
            "kind": "crosscheck",
            "m2": manifest["root"],
            "m3": manifest["root"],
        }
        manifest_path.write_text(json.dumps(manifest))
        return claim

    def test_a_current_proof_counts(self, tmp_path):
        claim = self._proved_claim(tmp_path)
        view = views._claim_view(str(claim))
        assert view["proof"] is True
        assert view["proof_stale"] is False

    def test_a_reseal_marks_the_proof_stale(self, tmp_path):
        claim = self._proved_claim(tmp_path)
        old_proof = json.loads(
            (claim / ".reticuli" / "manifest.json").read_text()
        )["proof"]
        # strengthen a criterion: the root moves, the proof's roots do not
        (claim / "check.py").write_text(CHECK + "assert answer != 41\n")
        kernel.seal(str(claim))
        manifest_path = claim / ".reticuli" / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["proof"] = old_proof
        manifest_path.write_text(json.dumps(manifest))

        view = views._claim_view(str(claim))
        assert view["proof"] is False, "a proof earned on other bytes is not held"
        assert view["proof_stale"] is True
        # after a reseal EVERY receipt is stale, so the ladder restarts at
        # the audit rung -- what matters is that it no longer says "share it"
        assert "share it" not in view["next"]


# ---------------------------------------------------------------------------
# R4: mutation samples this layer's own files only
# ---------------------------------------------------------------------------
class TestMutationScopedToOwnFiles:
    def test_component_supplied_files_are_not_sampled(self, tmp_path):
        recipe = (
            '[claim]\nname = "composed"\ninputs = ["check.py"]\n\n'
            '[[step]]\nkind = "produce"\noutput = "impl.py"\nclass = "generated"\n\n'
            '[[step]]\nkind = "produce"\noutput = "comp.py"\nclass = "generated"\n'
            'from = "lower-layer"\n\n'
            '[[step]]\nkind = "gate"\noutput = "OK"\nclass = "validated"\n'
            'run = "python3 check.py && printf ok > OK"\n'
        )
        claim = _seal(
            tmp_path / "claim",
            recipe,
            {
                "check.py": CHECK,
                "impl.py": "answer = 42\n",
                # dense in mutation sites: every one sampled here would
                # dilute the layer's own score
                "comp.py": "def f(a, b):\n    return a + b * 2 - 1\n",
                "OK": "ok",
            },
        )
        score = kernel.mutation_score(str(claim), max_mutants=4)
        assert score["supplied_excluded"] == 1
        for survivor in score.get("survivors") or []:
            assert "comp.py" not in str(survivor), (
                "a supplied file was sampled; its own claim judges it"
            )


# ---------------------------------------------------------------------------
# R8: pack warns when a dependent under-declares a component
# ---------------------------------------------------------------------------
class TestUnderDeclarationWarning:
    def _component(self, tmp_path):
        comp = tmp_path / "comp"
        comp.mkdir()
        (comp / "one.py").write_text("ONE = 1\n")
        (comp / "two.py").write_text("TWO = 2\n")
        (comp / "check.py").write_text(
            "from one import ONE\nfrom two import TWO\n"
            "assert ONE + TWO == 3\nopen('OK', 'w').write('ok')\n"
        )
        pack.pack(str(comp), "lower", ["one.py", "two.py"], ["check.py"],
                  "python3 check.py", "OK")
        return comp

    def _upper(self, tmp_path, comp):
        from reticuli import registry

        ws = tmp_path / "upper"
        ws.mkdir()
        registry.pull(str(comp), str(ws))
        (ws / "check2.py").write_text(
            "from one import ONE\nassert ONE == 1\nopen('OK2', 'w').write('ok')\n"
        )
        # declares one.py from the component -- and forgets two.py, which
        # ret pull also materialized, so the warm pack cannot notice
        (ws / "reticuli.toml").write_text(
            '[claim]\nname = "upper"\ninputs = ["check2.py"]\n\n'
            '[[step]]\nkind = "produce"\noutput = "one.py"\nclass = "generated"\n'
            'from = "lower"\n\n'
            '[[step]]\nkind = "gate"\noutput = "OK2"\nclass = "validated"\n'
            'run = "python3 check2.py && printf ok > OK2"\n'
        )
        return ws

    def test_the_forgotten_output_is_named(self, tmp_path, capsys):
        ws = self._upper(tmp_path, self._component(tmp_path))
        pack.pack_declared(str(ws))
        err = capsys.readouterr().err
        assert "warning" in err
        assert "two.py" in err
        assert "lower" in err

    def test_a_fully_declared_component_warns_nothing(self, tmp_path, capsys):
        comp = self._component(tmp_path)
        ws = self._upper(tmp_path, comp)
        recipe = (ws / "reticuli.toml").read_text()
        recipe = recipe.replace(
            '[[step]]\nkind = "gate"',
            '[[step]]\nkind = "produce"\noutput = "two.py"\nclass = "generated"\n'
            'from = "lower"\n\n[[step]]\nkind = "gate"',
        )
        (ws / "reticuli.toml").write_text(recipe)
        pack.pack_declared(str(ws))
        assert "warning" not in capsys.readouterr().err


# ---------------------------------------------------------------------------
# R10: the per-file account shows pinned produce outputs
# ---------------------------------------------------------------------------
class TestFilesAccountShowsPinnedOutputs:
    def test_the_view_carries_pinned_outputs(self, tmp_path):
        claim = _seal(
            tmp_path / "claim",
            WITH_PINNED_OUTPUT,
            {
                "check.py": TABLE_CHECK,
                "table.py": "COST = 7\n",
                "impl.py": "answer = 42\n",
                "OK": "ok",
            },
        )
        view = views._claim_view(str(claim))
        assert view["pinned_outputs"] == ["table.py"]
        assert "table.py" not in view["free"]

    def test_identity_actually_covers_the_pinned_output(self, tmp_path):
        # the account claims it is pinned; prove the root agrees
        claim = _seal(
            tmp_path / "claim",
            WITH_PINNED_OUTPUT,
            {
                "check.py": TABLE_CHECK,
                "table.py": "COST = 7\n",
                "impl.py": "answer = 42\n",
                "OK": "ok",
            },
        )
        assert kernel.verify(str(claim))["ok"]
        (claim / "table.py").write_text("COST = 7  # touched\n")
        assert not kernel.verify(str(claim))["ok"]
