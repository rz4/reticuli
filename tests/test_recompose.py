"""The no-argument pull: recomposition of a collection of sibling claims.

Field origin: resealing a leaf orphans the copies inside its dependents —
the dependent's manifest link still names the leaf's old root, and later
pulls fail with `unresolved components` naming leaves that are plainly
present. The first campaign repaired this with a hand-ordered shell script;
these tests pin the verb that replaces it. The contract under test: pack
moves roots, deliberately, one claim at a time; a no-argument pull never
moves one — it restores the composition's bookkeeping (drawer copies,
manifest links, materialized files) to agree with roots that already moved,
bottom-up in the order the graph itself decides, resealing warm so the
gates re-earn at every refreshed layer.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reticuli import cli, kernel, pack, registry


def _gate(check: str, verdict: str) -> str:
    return f"python3 {check} && printf ok > {verdict}"


def _lower(ws):
    """The leaf: a packed self-claim named `low` in ws/lower."""
    d = ws / "lower"
    d.mkdir()
    (d / "impl.py").write_text("answer = 42\n")
    (d / "check.py").write_text(
        "from impl import answer\nassert answer == 42\n"
        "open('OK', 'w').write('ok')\n")
    pack.pack(str(d), "low", ["impl.py"], ["check.py"], _gate("check.py", "OK"), "OK")
    return d


def _dependent(ws, dirname, name, comp_dir, comp_name, check, verdict,
               inputs=None, supplied=("impl.py",)):
    """A claim in ws/<dirname> that layers on comp via from-steps."""
    d = ws / dirname
    d.mkdir()
    registry.pull(str(comp_dir), str(d))
    checkfile = f"check_{name}.py"
    (d / checkfile).write_text(check)
    steps = "".join(
        f'[[step]]\nkind = "produce"\noutput = "{f}"\nclass = "generated"\n'
        f'from = "{comp_name}"\n\n' for f in supplied)
    declared = json.dumps([checkfile] + list(inputs or []))
    (d / "reticuli.toml").write_text(
        f'[claim]\nname = "{name}"\ninputs = {declared}\n\n{steps}'
        f'[[step]]\nkind = "gate"\noutput = "{verdict}"\nclass = "validated"\n'
        f'run = "{_gate(checkfile, verdict)}"\n')
    pack.pack_declared(str(d))
    return d


def _pinned_leaf(ws, pinned_name, pinned_body, check_body):
    """A leaf named `low` whose recipe pins one produce output — so changing
    that file moves the leaf's root, the trigger recompose reacts to."""
    d = ws / "lower"
    d.mkdir()
    (d / "reticuli.toml").write_text(
        '[claim]\nname = "low"\ninputs = ["check.py"]\n\n'
        f'[[step]]\nkind = "produce"\noutput = "{pinned_name}"\nclass = "pinned"\n\n'
        '[[step]]\nkind = "produce"\noutput = "impl.py"\nclass = "generated"\n\n'
        '[[step]]\nkind = "gate"\noutput = "OK"\nclass = "validated"\n'
        f'run = "{_gate("check.py", "OK")}"\n')
    (d / pinned_name).write_text(pinned_body)
    (d / "impl.py").write_text("answer = 42\n")
    (d / "check.py").write_text(check_body)
    (d / "OK").write_text("ok")
    kernel.seal(str(d))
    return d


def _reseal_leaf(lower):
    """Strengthen the leaf's criteria: its root moves, nothing else does."""
    check = lower / "check.py"
    check.write_text(check.read_text() + "assert answer != 41\n")
    kernel.seal(str(lower))


def _three_layer(ws):
    lower = _lower(ws)
    upper = _dependent(ws, "upper", "up", lower, "low",
                       "from impl import answer\nassert answer == 42\n"
                       "open('OK2', 'w').write('ok')\n", "OK2")
    top = _dependent(ws, "top", "topmost", upper, "up",
                     "from impl import answer\nassert answer == 42\n"
                     "open('OK3', 'w').write('ok')\n", "OK3")
    return lower, upper, top


# ---------------------------------------------------------------------------
# the pure view: status over a collection of sibling claims
# ---------------------------------------------------------------------------
class TestCollectionView:
    def test_a_coherent_composition_reads_coherent(self, tmp_path):
        _three_layer(tmp_path)
        col = registry.collection(str(tmp_path))
        assert [m["name"] for m in col["members"]] == ["low", "up", "topmost"], \
            "dependency order, leaves first — a property of the graph"
        assert col["stale"] == 0 and col["unresolved"] == 0

    def test_a_resealed_leaf_marks_its_dependent_stale(self, tmp_path):
        lower = _lower(tmp_path)
        _dependent(tmp_path, "upper", "up", lower, "low",
                   "from impl import answer\nassert answer == 42\n"
                   "open('OK2', 'w').write('ok')\n", "OK2")
        _reseal_leaf(lower)
        col = registry.collection(str(tmp_path))
        up = next(m for m in col["members"] if m["name"] == "up")
        assert up["links"][0]["status"] == "stale"
        assert col["stale"] == 1

    def test_two_siblings_with_one_name_refuse(self, tmp_path):
        for dirname in ("a", "b"):
            d = tmp_path / dirname
            d.mkdir()
            (d / "impl.py").write_text("answer = 42\n")
            (d / "check.py").write_text("open('OK', 'w').write('ok')\n")
            pack.pack(str(d), "same", ["impl.py"], ["check.py"],
                      _gate("check.py", "OK"), "OK")
        with pytest.raises(kernel.ClaimError, match="both named 'same'"):
            registry.collection(str(tmp_path))


# ---------------------------------------------------------------------------
# recompose: bottom-up, root-preserving, judged live
# ---------------------------------------------------------------------------
class TestRecompose:
    def test_the_cascade_refreshes_without_moving_a_root(self, tmp_path):
        lower, upper, top = _three_layer(tmp_path)
        root_up = kernel.read_manifest(str(upper))["root"]
        root_top = kernel.read_manifest(str(top))["root"]
        _reseal_leaf(lower)
        new_low = kernel.read_manifest(str(lower))["root"]

        r = registry.recompose(str(tmp_path))
        assert r["ok"]
        actions = {row["name"]: row["action"] for row in r["claims"]}
        # top's link roots never went stale — only its drawer copy of `up`
        # froze on the old closure; staleness judged live catches it AFTER
        # up's refresh, which a snapshot taken up front could not
        assert actions == {"low": "held", "up": "refreshed",
                           "topmost": "refreshed"}
        assert kernel.read_manifest(str(upper))["root"] == root_up
        assert kernel.read_manifest(str(top))["root"] == root_top
        assert kernel.read_manifest(str(upper))["components"][0]["root"] == new_low
        drawer = top / ".reticuli" / "sealed" / "up"
        assert kernel.read_manifest(str(drawer))["components"][0]["root"] == new_low, \
            "the dependent's frozen closure is the rot this verb exists to clear"
        assert registry.collection(str(tmp_path))["stale"] == 0

    def test_a_coherent_composition_is_all_held(self, tmp_path):
        _three_layer(tmp_path)
        r = registry.recompose(str(tmp_path))
        assert r["ok"] and r["refreshed_count"] == 0
        assert all(row["action"] == "held" for row in r["claims"])

    def test_a_pinned_supplied_file_is_refused_not_resealed(self, tmp_path):
        # the ATen-table pattern: the dependent PINS a component-supplied
        # file, so refreshing it would move the dependent's root — that is
        # a criteria change, pack's territory, never recompose's
        d = _pinned_leaf(tmp_path, "table.py", "COST = 7\n",
                         "from table import COST\nassert COST in (7, 8)\n"
                         "open('OK', 'w').write('ok')\n")
        upper = _dependent(tmp_path, "upper", "up", d, "low",
                           "from table import COST\nassert COST == 7\n"
                           "open('OK2', 'w').write('ok')\n", "OK2",
                           inputs=["table.py"])
        root_up = kernel.read_manifest(str(upper))["root"]
        (d / "table.py").write_text("COST = 8\n")
        kernel.seal(str(d))

        r = registry.recompose(str(tmp_path))
        row = next(x for x in r["claims"] if x["name"] == "up")
        assert row["action"] == "refused"
        assert "table.py" in row["reason"] and "ret pack" in row["reason"]
        assert kernel.read_manifest(str(upper))["root"] == root_up
        assert (upper / "table.py").read_text() == "COST = 7\n", \
            "a refusal touches nothing — the pinned byte is the human's call"

    def test_a_rejecting_gate_stops_the_walk_where_it_broke(self, tmp_path):
        # data.py is PINNED in low (changing it moves low's root) and
        # GENERATED in up (so the refresh is legal there) — the honest case
        # where the composition genuinely broke and only a warm gate says so
        lower = _pinned_leaf(tmp_path, "data.py", "LIMIT = 1\n",
                             "from data import LIMIT\nassert LIMIT in (1, 2)\n"
                             "open('OK', 'w').write('ok')\n")
        upper = _dependent(tmp_path, "upper", "up", lower, "low",
                           "from data import LIMIT\nassert LIMIT == 1\n"
                           "open('OK2', 'w').write('ok')\n", "OK2",
                           supplied=("impl.py", "data.py"))
        top = _dependent(tmp_path, "top", "topmost", upper, "up",
                         "from impl import answer\nassert answer == 42\n"
                         "open('OK3', 'w').write('ok')\n", "OK3")
        root_top = kernel.read_manifest(str(top))["root"]
        (lower / "data.py").write_text("LIMIT = 2\n")
        kernel.seal(str(lower))                     # pinned byte: root moves

        r = registry.recompose(str(tmp_path))
        assert not r["ok"]
        assert [x["action"] for x in r["claims"]] == ["held", "failed"], \
            "the first refusing layer localizes the break; nothing above runs"
        failed = r["claims"][1]
        assert failed["name"] == "up" and "gate" in failed["reason"]
        # the failed dependent's IDENTITY is untouched: only generated bytes
        # and drawer residue moved, and neither is inside the root
        assert kernel.verify(str(upper))["ok"]
        assert kernel.read_manifest(str(top))["root"] == root_top

    def test_a_refreshed_claims_proof_predates_and_the_report_says_so(self, tmp_path):
        lower = _lower(tmp_path)
        upper = _dependent(tmp_path, "upper", "up", lower, "low",
                           "from impl import answer\nassert answer == 42\n"
                           "open('OK2', 'w').write('ok')\n", "OK2")
        mpath = upper / ".reticuli" / "manifest.json"
        manifest = json.loads(mpath.read_text())
        manifest["proof"] = {"kind": "crosscheck", "m2": manifest["root"],
                             "m3": manifest["root"]}
        mpath.write_text(json.dumps(manifest))
        _reseal_leaf(lower)

        r = registry.recompose(str(tmp_path))
        assert r["proofs_predate"] == ["up"], \
            "the root held, so the R12 staleness check stays green — only " \
            "this report knows the proof was earned over older component bytes"
        after = json.loads(mpath.read_text())
        assert after.get("proof"), "resealing preserves residue it does not own"
        assert after["root"] == manifest["root"]

    def test_an_empty_directory_refuses_with_the_remedy(self, tmp_path):
        with pytest.raises(kernel.ClaimError, match="no sealed claims"):
            registry.recompose(str(tmp_path))


# ---------------------------------------------------------------------------
# the CLI surface: ret pull [<claim>], ret status over a collection
# ---------------------------------------------------------------------------
class TestCli:
    def test_pull_with_no_claim_recomposes(self, tmp_path, capsys):
        lower, _upper, _top = _three_layer(tmp_path)
        _reseal_leaf(lower)
        assert cli.main(["pull", "-C", str(tmp_path)]) == 0
        out = capsys.readouterr().out
        assert "refreshed" in out and "root unchanged" in out
        assert registry.collection(str(tmp_path))["stale"] == 0

    def test_pull_with_a_claim_still_pulls(self, tmp_path):
        lower = _lower(tmp_path)
        ws = tmp_path / "fresh"
        ws.mkdir()
        assert cli.main(["pull", str(lower), "-C", str(ws)]) == 0
        assert (ws / ".reticuli" / "sealed" / "low").is_dir()

    def test_a_failed_recompose_exits_nonzero(self, tmp_path):
        lower = _pinned_leaf(tmp_path, "data.py", "LIMIT = 1\n",
                             "from data import LIMIT\nassert LIMIT in (1, 2)\n"
                             "open('OK', 'w').write('ok')\n")
        _dependent(tmp_path, "upper", "up", lower, "low",
                   "from data import LIMIT\nassert LIMIT == 1\n"
                   "open('OK2', 'w').write('ok')\n", "OK2",
                   supplied=("impl.py", "data.py"))
        (lower / "data.py").write_text("LIMIT = 2\n")
        kernel.seal(str(lower))
        assert cli.main(["pull", "-C", str(tmp_path)]) == 1

    def test_status_shows_the_collection(self, tmp_path, capsys):
        lower, _upper, _top = _three_layer(tmp_path)
        assert cli.main(["status", str(tmp_path), "--json"]) == 0
        r = json.loads(capsys.readouterr().out)
        assert r["status"] == "coherent"
        assert len(r["data"]["members"]) == 3
        _reseal_leaf(lower)
        assert cli.main(["status", str(tmp_path), "--json"]) == 0
        r = json.loads(capsys.readouterr().out)
        assert r["status"] == "stale" and r["data"]["stale"] == 1
