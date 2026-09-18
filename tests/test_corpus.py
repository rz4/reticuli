"""The reference corpus: assess results accumulate so one claim can be read
against a population. Residue by construction -- it never touches identity.

    pytest tests/test_corpus.py   (or: python3 tests/test_corpus.py)
"""
import os
import statistics
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from reticuli import corpus


def _report(rate: float, blind: bool | None = None) -> dict:
    r = {"claim": "c", "root": "r", "gate": "earned",
         "measured": {"circularity": {"ok": True},
                      "mutation": {"rate": rate, "killed": int(rate * 10),
                                   "mutants": 10, "candidates": 20}}}
    if blind is not None:
        r["measured"]["re_derivation"] = {"ok": blind, "blind": True}
    return r


def test_flatten_keeps_the_measured_numbers() -> None:
    rec = corpus.flatten(_report(0.5, blind=True))
    assert rec["claim"] == "c" and rec["circularity_ok"] is True
    assert rec["mutation"]["rate"] == 0.5 and rec["re_derivation_blind"] is True
    assert "when" in rec, "a corpus record is stamped with when it was taken"


def test_distribution_and_placement() -> None:
    recs = [corpus.flatten(_report(x, blind=(x > 0.5))) for x in (0.2, 0.4, 0.6, 0.8)]
    dist = corpus.distribution(recs)
    assert dist["n"] == 4
    assert dist["mutation"]["median"] == round(statistics.median([0.2, 0.4, 0.6, 0.8]), 3)
    assert dist["re_derivation_blind"]["n"] == 4
    assert dist["re_derivation_blind"]["passed"] == 2, "0.6 and 0.8 passed blind"
    placed = corpus.place(corpus.flatten(_report(0.6, blind=True)), dist)
    assert placed["population"] == 4
    assert placed["mutation"]["percentile"] == 75, "three of four rates are <= 0.6"
    assert placed["re_derivation_blind"]["population_rate"] == 0.5


def test_record_and_place_compares_against_prior_then_appends() -> None:
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "corpus.jsonl")
        first = corpus.record_and_place(path, _report(0.5))
        assert first["population"] == 0, "the first run sees an empty population"
        second = corpus.record_and_place(path, _report(0.9))
        assert second["population"] == 1, "placed against the prior only, not itself"
        assert len(corpus.load(path)) == 2, "both runs were recorded"


def test_thin_population_says_nothing_it_cannot() -> None:
    placed = corpus.place(corpus.flatten(_report(0.5)), corpus.distribution([]))
    assert placed["population"] == 0 and "mutation" not in placed, \
        "an empty corpus yields no percentile to mislead with"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("corpus-ok")
