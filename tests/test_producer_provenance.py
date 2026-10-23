"""A proof says a redo failed to break the claim — so it must name the redo.

A recorded proof is a statement about an oracle: a stronger producer may
break tomorrow what this one could not, and a reader who cannot tell which
producer ran cannot weigh the evidence. Two things made that unreadable.
The kernel recorded the model from the caller's environment, which is a
declaration and is empty whenever the producer picks its own default (every
CLI-driven rebuild); and the composed path recorded only `{kind, m2, m3}`,
with roots in the digest fields and no producer at all — which is what the
first campaign's ten proofs carry.

These tests pin: a producer's observation beats the caller's declaration and
says which it was; the composed proof carries root, digests, independence,
producer and layers; and status reports the oracle, or reports that the
proof names none rather than reading as though it did.
"""
import json
import sys
from pathlib import Path
from types import MappingProxyType

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reticuli import kernel, registry
from reticuli._cli import views
from reticuli.producers import codex

RECIPE = (
    '[claim]\nname = "answers"\ninputs = ["check.py"]\n\n'
    '[[step]]\nkind = "produce"\noutput = "impl.py"\nclass = "generated"\n\n'
    '[[step]]\nkind = "gate"\noutput = "OK"\nclass = "validated"\n'
    'run = "python3 check.py && printf ok > OK"\n'
)
CHECK = "from impl import answer\nassert answer == 42\nopen('OK','w').write('ok')\n"


def _claim(d: Path) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    (d / "reticuli.toml").write_text(RECIPE)
    (d / "check.py").write_text(CHECK)
    (d / "impl.py").write_text("answer = 42\n")
    (d / "OK").write_text("ok")
    kernel.seal(str(d))
    return d


def _producer(tmp_path: Path, body: str) -> str:
    """A producer script that writes impl.py and whatever usage it declares."""
    path = tmp_path / "producer.py"
    path.write_text(
        "import json, os\n"
        "open(os.environ['RETICULI_OUTPUT'], 'w').write('answer = 6 * 7\\n')\n"
        + body)
    return f"python3 {path}"


REPORTS_MODEL = (
    "u = os.environ.get('RETICULI_USAGE')\n"
    "json.dump({'vendor': 'codex', 'model': 'gpt-6-astra', 'tokens': 11,\n"
    "           'provider': 'openai', 'producer_version': '0.155.1'},\n"
    "          open(u, 'w'))\n"
)
REPORTS_NOTHING = "pass\n"


def _producer_event(claimdir: str) -> dict:
    events = kernel.ledger_events(claimdir) or []
    return next(e for e in reversed(events) if e.get("event") == "producer")


# ---------------------------------------------------------------------------
# the ledger: observation beats declaration, and says which it is
# ---------------------------------------------------------------------------
class TestWhatRanIsRecorded:
    def test_an_observing_producer_is_believed_over_the_environment(
            self, tmp_path, monkeypatch):
        claim = _claim(tmp_path / "claim")
        monkeypatch.setenv("RETICULI_MODEL", "whatever-the-caller-guessed")
        kernel.rebuild(str(claim), _producer(tmp_path, REPORTS_MODEL),
                       str(tmp_path / "m3"))
        event = _producer_event(str(tmp_path / "m3"))
        assert event["model"] == "gpt-6-astra", \
            "the producer knows what ran; the env var is only a guess"
        assert event["model_source"] == "observed"
        assert event["vendor"] == "codex"
        assert event["producer_version"] == "0.155.1"

    def test_a_silent_producer_falls_back_to_the_declaration(
            self, tmp_path, monkeypatch):
        claim = _claim(tmp_path / "claim")
        monkeypatch.setenv("RETICULI_MODEL", "declared-only")
        kernel.rebuild(str(claim), _producer(tmp_path, REPORTS_NOTHING),
                       str(tmp_path / "m3"))
        event = _producer_event(str(tmp_path / "m3"))
        assert event["model"] == "declared-only"
        assert event["model_source"] == "declared", \
            "a caller's declaration is usable, but must not pass as observation"

    def test_silence_everywhere_is_unrecorded_not_invented(
            self, tmp_path, monkeypatch):
        claim = _claim(tmp_path / "claim")
        monkeypatch.delenv("RETICULI_MODEL", raising=False)
        kernel.rebuild(str(claim), _producer(tmp_path, REPORTS_NOTHING),
                       str(tmp_path / "m3"))
        event = _producer_event(str(tmp_path / "m3"))
        assert event["model"] is None
        assert event["model_source"] == "unrecorded"
        decl = kernel.independence(str(tmp_path / "m3"))
        assert decl["model_source"] == "unrecorded" and decl["declared"]

    def test_the_declaration_carries_the_source_to_readers(
            self, tmp_path, monkeypatch):
        claim = _claim(tmp_path / "claim")
        monkeypatch.delenv("RETICULI_MODEL", raising=False)
        kernel.rebuild(str(claim), _producer(tmp_path, REPORTS_MODEL),
                       str(tmp_path / "m3"))
        decl = kernel.independence(str(tmp_path / "m3"))
        assert decl["model"] == "gpt-6-astra"
        assert decl["model_source"] == "observed"
        assert kernel._independence_line(decl).startswith(
            "declared: codex/gpt-6-astra")
        assert "not proven" in kernel._independence_line(decl), \
            "observed by the producer is still a declaration, never proof"


# ---------------------------------------------------------------------------
# the codex producer observes its own run
# ---------------------------------------------------------------------------
class TestCodexObservesItsOwnRun:
    # the shapes codex 0.155.1 actually emits, trimmed to the fields read
    SESSION_META = MappingProxyType({"type": "session_meta", "payload": {
        "cli_version": "0.155.1", "model_provider": "openai",
        "base_instructions": {"provenance": {"model": "gpt-6-astra"}}}})
    TURN_CONTEXT = MappingProxyType(
        {"type": "turn_context", "payload": {"model": "gpt-6-astra"}})
    WORLD_STATE = MappingProxyType({"type": "world_state", "payload": {
        "state": {"model": "gpt-6-astra"}}})

    def test_the_model_is_read_from_the_event_stream(self):
        for event in (self.TURN_CONTEXT, self.WORLD_STATE, self.SESSION_META):
            state = {}
            codex._observe(event, state)
            assert state.get("model") == "gpt-6-astra", event["type"]

    def test_provider_and_version_come_from_the_session(self):
        state = {}
        codex._observe(self.SESSION_META, state)
        assert state["provider"] == "openai"
        assert state["producer_version"] == "0.155.1"

    def test_a_drifted_schema_records_nothing_rather_than_guessing(self):
        state = {}
        codex._observe({"type": "turn_context", "payload": {"mdl": "x"}}, state)
        codex._observe({"type": "unknown", "payload": {"model": "y"}}, state)
        codex._observe({"type": "turn_context", "payload": None}, state)
        assert state == {}, "a miss leaves the field unrecorded"

    def test_the_first_observation_wins(self):
        state = {}
        codex._observe(self.TURN_CONTEXT, state)
        codex._observe({"type": "turn_context", "payload": {"model": "later"}},
                       state)
        assert state["model"] == "gpt-6-astra"

    def test_the_report_carries_what_was_observed(self, tmp_path, monkeypatch):
        usage = tmp_path / "usage.json"
        monkeypatch.setenv("RETICULI_USAGE", str(usage))
        codex._report({"tokens": 7, "model": "gpt-6-astra",
                       "provider": "openai", "producer_version": "0.155.1"})
        rec = json.loads(usage.read_text())
        assert rec == {"vendor": "codex", "metered": False, "tokens": 7,
                       "model": "gpt-6-astra", "provider": "openai",
                       "producer_version": "0.155.1"}

    def test_an_unobserved_run_reports_cost_only(self, tmp_path, monkeypatch):
        usage = tmp_path / "usage.json"
        monkeypatch.setenv("RETICULI_USAGE", str(usage))
        codex._report({"tokens": 3})
        assert json.loads(usage.read_text()) == {
            "vendor": "codex", "metered": False, "tokens": 3}


# ---------------------------------------------------------------------------
# the composed proof carries what the kernel's does
# ---------------------------------------------------------------------------
class TestComposedProofNamesItsOracle:
    def _three(self, tmp_path, monkeypatch, usage_body=REPORTS_MODEL):
        m1 = _claim(tmp_path / "m1")
        # M2 is byte-reuse; M3 an independent redo by the producer
        m2 = tmp_path / "m2"
        registry.copy_claim(str(m1), str(m2))
        monkeypatch.delenv("RETICULI_MODEL", raising=False)
        kernel.rebuild(str(m1), _producer(tmp_path, usage_body),
                       str(tmp_path / "m3"))
        return m1, m2, tmp_path / "m3"

    def test_the_proof_names_root_digests_and_oracle(self, tmp_path, monkeypatch):
        m1, m2, m3 = self._three(tmp_path, monkeypatch)
        result = registry.record_proof_deep(str(m1), str(m2), str(m3))
        assert result["satisfied"] and result["proof_recorded"], result["verdict"]
        proof = kernel.read_manifest(str(m1))["proof"]
        assert proof["root"] == kernel.read_manifest(str(m1))["root"]
        assert proof["m2"] == result["digests"]["M2"]
        assert proof["m3"] == result["digests"]["M3"]
        assert proof["producer"]["model"] == "gpt-6-astra"
        assert proof["producer"]["model_source"] == "observed"
        assert proof["independence"].startswith("declared: codex/gpt-6-astra")
        assert proof["recorded"].endswith("Z")

    def test_the_proof_still_counts_as_current(self, tmp_path, monkeypatch):
        m1, m2, m3 = self._three(tmp_path, monkeypatch)
        registry.record_proof_deep(str(m1), str(m2), str(m3))
        view = views._claim_view(str(m1))
        assert view["proof"] is True and view["proof_stale"] is False, \
            "digests in m2/m3 must not break the staleness check"
        assert view["proof_producer"] == "codex/gpt-6-astra"
        # the lower rungs are unearned here, so the ladder still points at
        # audit; what matters is that it no longer asks to be proved
        assert "prove it" not in view["next"]

    def test_an_unnamed_oracle_is_reported_as_unnamed(self, tmp_path, monkeypatch):
        m1, m2, m3 = self._three(tmp_path, monkeypatch, REPORTS_NOTHING)
        registry.record_proof_deep(str(m1), str(m2), str(m3))
        proof = kernel.read_manifest(str(m1))["proof"]
        assert proof["producer"]["model"] is None
        assert proof["producer"]["model_source"] == "unrecorded"
        view = views._claim_view(str(m1))
        assert view["proof"] is True
        assert view["proof_producer"] is None, \
            "no oracle recorded must read as none, never as a blank name"

    def test_a_campaign_era_proof_is_still_read_correctly(self, tmp_path):
        # the shape the first campaign sealed: roots in the digest fields,
        # no producer, no root key. Readers must keep working on it.
        claim = _claim(tmp_path / "claim")
        path = claim / ".reticuli" / "manifest.json"
        manifest = json.loads(path.read_text())
        manifest["proof"] = {"kind": "crosscheck", "m2": manifest["root"],
                             "m3": manifest["root"]}
        path.write_text(json.dumps(manifest))
        view = views._claim_view(str(claim))
        assert view["proof"] is True and view["proof_stale"] is False
        assert view["proof_producer"] is None


# ---------------------------------------------------------------------------
# the CLI says which oracle, in the fact sheet
# ---------------------------------------------------------------------------
class TestStatusSaysWhichOracle:
    def test_the_proof_row_carries_the_oracle(self, tmp_path, capsys):
        from reticuli._cli import statusview
        view = {"name": "x", "root": "a" * 64, "phase": "sealed", "ok": True,
                "recomputed": None, "changed": [], "audited": None,
                "deciding": None, "discovery": None, "proof": True,
                "proof_stale": False, "proof_producer": "codex/gpt-6-astra",
                "signatures": 0,
                "fixed": {"criteria": [], "inputs": 0, "inputs_list": [],
                          "requires": [], "environment": None,
                          "envelope": None, "mutation_floor": None},
                "free": [], "pinned_outputs": [], "verdicts": [],
                "next": "stand behind it"}
        statusview._ledger_status_claim(view)
        out = capsys.readouterr().out
        assert "recorded (codex/gpt-6-astra)" in out
        view["proof_producer"] = None
        statusview._ledger_status_claim(view)
        out = capsys.readouterr().out
        assert "the redo named no oracle" in out, \
            "an unnamed oracle is said out loud, not silently equivalent"
