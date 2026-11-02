"""Declared-shape divergence (APEIRON item 3): a transition states the shape
of the change it expects, and the comparator holds the revised data to it.

The acceptance case is A66's own: two warmup-evaluation rows added at the
head of the eval series, values identical everywhere, and the subject's
global step counter relabeling every later row — a two-row declared fix that
a flat digest read as near-total divergence. Declared as rows-inserted on
the eval surface with the join on the row's own content (stage, event_id)
and the counter excused, it verifies green; the same declaration over a
genuinely value-divergent tree refuses, naming the first row outside the
declared shape.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reticuli import divergence
from reticuli.kernel import ClaimError


def _eval_row(event_id, step, value):
    return {"stage": "eval", "event_id": event_id, "step": step, "value": value}


ORIGINAL = {
    "eval/accuracy": [_eval_row(3, 30, 0.91), _eval_row(4, 40, 0.93),
                      _eval_row(5, 50, 0.95)],
    "cl/loss": [{"stage": "cl", "event_id": 1, "step": 10, "value": 1.2},
                {"stage": "cl", "event_id": 2, "step": 20, "value": 0.8}],
    "train_time": [3.1, 2.9],
}

# A66: two warmup rows join the head, and the global counter relabels
# every later eval row; the measurements themselves never moved.
A66_REVISED = {
    "eval/accuracy": [_eval_row(1, 10, 0.42), _eval_row(2, 20, 0.77),
                      _eval_row(3, 50, 0.91), _eval_row(4, 60, 0.93),
                      _eval_row(5, 70, 0.95)],
    "cl/loss": ORIGINAL["cl/loss"],
    "train_time": [3.4, 2.7],
}

A66_DECLARATION = {
    "ignore": ["*_time", "*_flops"],
    "expect": [{"class": "rows-inserted", "series": "eval/*",
                "where": {"stage": "eval"},
                "join": ["stage", "event_id"], "free": ["step"]}],
}


class TestTheA66Shape:
    def test_the_declared_fix_verifies_green(self):
        r = divergence.verify(ORIGINAL, A66_REVISED, A66_DECLARATION)
        assert r["ok"], r["refusals"]
        assert r["series"]["eval/accuracy"] == {
            "class": "rows-inserted", "clause": 0, "detail": "+2 inserted"}
        assert r["series"]["cl/loss"]["class"] == "identical"
        assert r["series"]["train_time"]["class"] == "ignored"

    def test_a_genuinely_divergent_tree_refuses_naming_the_row(self):
        drifted = json.loads(json.dumps(A66_REVISED))
        drifted["eval/accuracy"][3]["value"] = 0.11   # event_id 4 lies
        r = divergence.verify(ORIGINAL, drifted, A66_DECLARATION)
        assert not r["ok"]
        (refusal,) = r["refusals"]
        assert refusal["series"] == "eval/accuracy"
        assert refusal["index"] == 3
        assert refusal["row"]["event_id"] == 4
        assert "identity" in refusal["reason"]

    def test_an_inserted_row_off_the_declared_surface_refuses(self):
        smuggled = json.loads(json.dumps(A66_REVISED))
        smuggled["eval/accuracy"].insert(
            2, {"stage": "train", "event_id": 99, "step": 25, "value": 0.5})
        r = divergence.verify(ORIGINAL, smuggled, A66_DECLARATION)
        assert not r["ok"]
        (refusal,) = r["refusals"]
        assert refusal["index"] == 2 and "surface" in refusal["reason"]

    def test_a_dropped_original_row_refuses(self):
        lossy = json.loads(json.dumps(A66_REVISED))
        del lossy["eval/accuracy"][4]                 # event_id 5 vanishes
        r = divergence.verify(ORIGINAL, lossy, A66_DECLARATION)
        assert not r["ok"]
        (refusal,) = r["refusals"]
        assert "no longer carries" in refusal["reason"]
        assert refusal["row"]["event_id"] == 5


class TestTheOtherClasses:
    def test_prefix_added_passes_at_the_head_only(self):
        decl = {"expect": [{"class": "prefix-added", "series": "s",
                            "where": {"stage": "eval"}, "free": ["step"]}]}
        orig = {"s": [_eval_row(3, 30, 0.9)]}
        head = {"s": [_eval_row(1, 10, 0.4), _eval_row(3, 40, 0.9)]}
        assert divergence.verify(orig, head, decl)["ok"]
        tail = {"s": [_eval_row(3, 30, 0.9), _eval_row(9, 90, 0.4)]}
        r = divergence.verify(orig, tail, decl)
        assert not r["ok"] and "prefix-added" in r["refusals"][0]["reason"]

    def test_value_change_allows_only_the_named_keys(self):
        decl = {"expect": [{"class": "value-change", "series": "s",
                            "join": ["event_id"], "keys": ["value"]}]}
        orig = {"s": [_eval_row(1, 10, 0.5), _eval_row(2, 20, 0.6)]}
        ok = {"s": [_eval_row(1, 10, 0.55), _eval_row(2, 20, 0.6)]}
        r = divergence.verify(orig, ok, decl)
        assert r["ok"] and r["series"]["s"]["detail"] == "1 row(s) changed in the declared keys"
        stray = {"s": [_eval_row(1, 99, 0.55), _eval_row(2, 20, 0.6)]}
        r = divergence.verify(orig, stray, decl)
        assert not r["ok"] and "outside the declared keys" in r["refusals"][0]["reason"]

    def test_scalar_rows_work_subsequence_style(self):
        # compare_v2's world: a series of bare values, the join their content
        decl = {"expect": [{"class": "rows-inserted", "series": "*"}]}
        r = divergence.verify({"v": [1, 2, 3]}, {"v": [0, 1, 2, 9, 3]}, decl)
        assert r["ok"] and r["series"]["v"]["detail"] == "+2 inserted"


class TestTheDefaultIsStrict:
    def test_an_undeclared_divergence_refuses(self):
        r = divergence.verify({"s": [1, 2]}, {"s": [1, 3]}, {})
        assert not r["ok"]
        assert "no declaration" in r["refusals"][0]["reason"]
        assert r["refusals"][0]["index"] == 1

    def test_a_series_on_one_side_only_refuses(self):
        r = divergence.verify({"a": [1]}, {"b": [1]}, {})
        reasons = {x["series"]: x["reason"] for x in r["refusals"]}
        assert "only the revision carries" in reasons["b"]
        assert "no longer carries" in reasons["a"]

    def test_a_malformed_declaration_is_refused_in_band(self):
        for bad in ([{"class": "nonsense", "series": "*"}],
                    [{"class": "rows-inserted"}],
                    [{"class": "value-change", "series": "*"}]):
            with pytest.raises(ClaimError):
                divergence.verify({}, {}, {"expect": bad})
        with pytest.raises(ClaimError):
            divergence.verify({}, {}, {"expected": []})   # a typo must not pass


class TestTheFiles:
    def test_csv_round_trip_and_exit_codes(self, tmp_path):
        head = "step,metric,value\n"
        (tmp_path / "orig.csv").write_text(
            head + "30,acc,0.91\n40,acc,0.93\n")
        (tmp_path / "rev.csv").write_text(
            head + "10,acc,0.42\n50,acc,0.91\n60,acc,0.93\n")
        decl = {"expect": [{"class": "prefix-added", "series": "acc",
                            "free": ["step"]}]}
        (tmp_path / "decl.json").write_text(json.dumps(decl))
        assert divergence.main([str(tmp_path / "orig.csv"),
                                str(tmp_path / "rev.csv"),
                                str(tmp_path / "decl.json")]) == 0
        (tmp_path / "bad.csv").write_text(
            head + "10,acc,0.42\n50,acc,0.80\n60,acc,0.93\n")
        assert divergence.main([str(tmp_path / "orig.csv"),
                                str(tmp_path / "bad.csv"),
                                str(tmp_path / "decl.json")]) == 1
