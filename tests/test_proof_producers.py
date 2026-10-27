"""A proof must name every oracle that failed to break the claim.

`ret crosscheck` accepts any number of realizations and tests each one, but
the proof it recorded kept a single `producer` taken from whichever rebuild
was listed LAST. Two consequences, both of which bit while re-earning the
ten APEIRON layer proofs across two producer families:

  * a claim reconstructed independently by codex AND by claude could only
    say so about one of them -- and a cross-family rebuild exists precisely
    to be the control for producer dependence, so that is the one claim the
    proof could not express
  * which one survived into the record was POSITIONAL. The two families
    carry different provenance (codex's model is read back from its session
    log and marked `observed`; the claude adapter's is the name we passed,
    marked `requested`), so listing the same four realizations in the order
    the rooms happened to be built silently produced a weaker record than
    the reverse, with nothing in the output to say so.

These tests pin the record, the ranking, and the view.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reticuli import registry
from reticuli._cli import views

OBSERVED = {"vendor": "codex", "model": "gpt-6-astra",
            "model_source": "observed", "blind": True, "declared": True}
REQUESTED = {"vendor": "claude-code", "model": "claude-opus-5",
             "model_source": "requested", "blind": True, "declared": True}
DECLARED = {"vendor": "openai", "model": "o-whatever",
            "model_source": "declared", "blind": True, "declared": True}


def _result(producer, m3digest):
    return {"satisfied": True,
            "roots": {"M1": "r" * 64},
            "digests": {"M2": "m2digest", "M3": m3digest},
            "independence": f"declared: {producer['vendor']}/{producer['model']}",
            "producer": dict(producer)}


# --- the ranking replaces the positional accident ----------------------

def test_strongest_declaration_prefers_observed_over_requested():
    assert registry.strongest_declaration([REQUESTED, OBSERVED]) == OBSERVED
    assert registry.strongest_declaration([OBSERVED, REQUESTED]) == OBSERVED, (
        "the choice must not depend on order -- that was the defect")


def test_strongest_declaration_orders_every_provenance():
    assert registry.strongest_declaration([DECLARED, REQUESTED]) == REQUESTED
    assert registry.strongest_declaration([DECLARED, OBSERVED]) == OBSERVED
    unrecorded = {"vendor": "x", "model": "y"}
    assert registry.strongest_declaration([unrecorded, DECLARED]) == DECLARED, (
        "a model with no stated provenance ranks below a declared one")


def test_strongest_declaration_handles_nothing_known():
    assert registry.strongest_declaration([]) is None
    assert registry.strongest_declaration([None, {}]) is None


# --- the recorded proof carries every leg ------------------------------

def test_sealed_proof_names_every_rebuild(tmp_path, monkeypatch):
    sealed = {}
    monkeypatch.setattr(registry, "seal_with",
                        lambda m1, **kw: sealed.update(kw))
    monkeypatch.setattr(registry, "chain", lambda m1: [])
    monkeypatch.setattr(registry.kernel, "read_manifest", lambda m1: {})

    results = [_result(REQUESTED, "d-claude"), _result(OBSERVED, "d-codex")]
    proof = registry.seal_proof(str(tmp_path), results)

    assert [d["model"] for d in proof["producers"]] == \
        ["claude-opus-5", "gpt-6-astra"], (
            "every rebuild's producer must be recorded, in order")
    assert len(proof["rebuilds"]) == 2
    assert {r["digest"] for r in proof["rebuilds"]} == {"d-claude", "d-codex"}, (
        "each rebuild's own build digest must be kept, not just the first's")
    assert proof["producer"]["model_source"] == "observed", (
        "the single `producer` field must hold the best-evidenced "
        "declaration, not the last one listed")
    assert proof["root"] == "r" * 64
    assert proof["m2"] == "m2digest"
    assert sealed["proof"] is proof, "the proof must actually be sealed"


def test_sealed_proof_is_order_independent(tmp_path, monkeypatch):
    """The same realizations in either order record the same `producer`."""
    monkeypatch.setattr(registry, "seal_with", lambda m1, **kw: None)
    monkeypatch.setattr(registry, "chain", lambda m1: [])
    monkeypatch.setattr(registry.kernel, "read_manifest", lambda m1: {})

    forward = registry.seal_proof(
        str(tmp_path), [_result(REQUESTED, "a"), _result(OBSERVED, "b")])
    reverse = registry.seal_proof(
        str(tmp_path), [_result(OBSERVED, "b"), _result(REQUESTED, "a")])

    assert forward["producer"] == reverse["producer"], (
        "argument order must not decide which oracle the proof names")
    assert {d["model"] for d in forward["producers"]} == \
           {d["model"] for d in reverse["producers"]}


def test_single_rebuild_proof_keeps_its_shape(tmp_path, monkeypatch):
    """One rebuild still records the shape existing readers parse."""
    monkeypatch.setattr(registry, "seal_with", lambda m1, **kw: None)
    monkeypatch.setattr(registry, "chain", lambda m1: [])
    monkeypatch.setattr(registry.kernel, "read_manifest", lambda m1: {})

    proof = registry.seal_proof(str(tmp_path), [_result(OBSERVED, "only")])

    assert proof["producer"]["model"] == "gpt-6-astra"
    assert proof["m3"] == "only"
    assert len(proof["producers"]) == 1


# --- what status reports -----------------------------------------------

def test_status_reports_every_oracle():
    manifest = {"proof": {"kind": "crosscheck",
                          "producer": OBSERVED,
                          "producers": [REQUESTED, OBSERVED]}}
    assert views._proof_producer(manifest) == \
        "claude-code/claude-opus-5, codex/gpt-6-astra", (
            "a claim rebuilt by two families must say both")


def test_status_falls_back_to_an_older_single_producer_proof():
    manifest = {"proof": {"kind": "crosscheck", "producer": OBSERVED}}
    assert views._proof_producer(manifest) == "codex/gpt-6-astra"


def test_status_deduplicates_one_family_rebuilt_twice():
    manifest = {"proof": {"producers": [OBSERVED, dict(OBSERVED)]}}
    assert views._proof_producer(manifest) == "codex/gpt-6-astra", (
        "two rebuilds by the same oracle is one oracle")


def test_status_says_nothing_when_the_proof_names_nothing():
    assert views._proof_producer({"proof": {"kind": "crosscheck"}}) is None
    assert views._proof_producer({"proof": {"producers": [{}, None]}}) is None
    assert views._proof_producer({}) is None, "no proof, no oracle"
