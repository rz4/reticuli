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
REPORTS_REQUESTED = (
    "u = os.environ.get('RETICULI_USAGE')\n"
    "json.dump({'vendor': 'codex', 'model': 'gpt-6-astra',\n"
    "           'model_source': 'requested'}, open(u, 'w'))\n"
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

    def test_a_producer_may_say_how_well_it_knows(self, tmp_path, monkeypatch):
        claim = _claim(tmp_path / "claim")
        monkeypatch.delenv("RETICULI_MODEL", raising=False)
        kernel.rebuild(str(claim), _producer(tmp_path, REPORTS_REQUESTED),
                       str(tmp_path / "m3"))
        event = _producer_event(str(tmp_path / "m3"))
        assert event["model"] == "gpt-6-astra"
        assert event["model_source"] == "requested", \
            "a CLI that only knows what it asked for must not claim to have " \
            "observed the answer"

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
    """The stdout stream and the rollout log are DIFFERENT schemas.

    `codex exec --json` prints only thread.started / turn.started /
    item.completed / turn.completed, and none of it names the model; the
    rollout log under ~/.codex/sessions does, and thread.started hands over
    the id that identifies it. Measured against codex 0.155.1 — writing the
    observer against the rollout shapes alone left every draw's model and
    every draw's token count unrecorded, which is how the first campaign
    came to have neither.
    """
    # the stdout family, verbatim from a probe run
    THREAD = MappingProxyType(
        {"type": "thread.started", "thread_id": "01a16923-80ca-7702-9b09"})
    TURN_DONE = MappingProxyType({"type": "turn.completed", "usage": {
        "input_tokens": 14205, "cached_input_tokens": 12160,
        "cache_write_input_tokens": 0, "output_tokens": 5,
        "reasoning_output_tokens": 0}})
    # the rollout family, still read when resolving the model afterwards
    SESSION_META = MappingProxyType({"type": "session_meta", "payload": {
        "cli_version": "0.155.1", "model_provider": "openai",
        "base_instructions": {"provenance": {"model": "gpt-6-astra"}}}})
    TURN_CONTEXT = MappingProxyType(
        {"type": "turn_context", "payload": {"model": "gpt-6-astra"}})
    WORLD_STATE = MappingProxyType({"type": "world_state", "payload": {
        "state": {"model": "gpt-6-astra"}}})

    def test_the_thread_id_is_kept_from_the_stdout_stream(self):
        state = {}
        codex._observe(self.THREAD, state)
        assert state["thread_id"] == "01a16923-80ca-7702-9b09", \
            "the only handle stdout gives for finding what model ran"

    def test_tokens_come_from_the_explicit_usage_block(self):
        state = {"tokens": 0}
        codex._observe(self.TURN_DONE, state)
        assert state["tokens"] == 14210, \
            "input + output; cached is a subset of input and reasoning of output"

    def test_the_heuristic_walk_never_saw_this_schema(self):
        # why the campaign recorded no cost at all: the walk accepts a key
        # only if it says `total`, and this schema has no such key
        assert codex._find_tokens(dict(self.TURN_DONE)) == 0

    def test_an_explicit_block_beats_the_walk(self):
        state = {"tokens": 0}
        codex._digest_event(json.dumps(dict(self.TURN_DONE)), state)
        codex._digest_event(json.dumps({"total_tokens": 999999}), state)
        assert state["tokens"] == 14210, "a subtotal may not overwrite a total"

    def test_the_model_is_read_from_the_rollout_shapes(self):
        for event in (self.TURN_CONTEXT, self.WORLD_STATE, self.SESSION_META):
            state = {}
            codex._observe(event, state)
            assert state.get("model") == "gpt-6-astra", event["type"]
            assert state.get("model_source") == "observed"

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
        codex._observe({"type": "turn.completed", "usage": "not a dict"}, state)
        codex._observe({"type": "thread.started"}, state)
        assert state == {}, "a miss leaves the field unrecorded"

    def test_the_first_observation_wins(self):
        state = {}
        codex._observe(self.TURN_CONTEXT, state)
        codex._observe({"type": "turn_context", "payload": {"model": "later"}},
                       state)
        assert state["model"] == "gpt-6-astra"

    def test_the_model_is_resolved_from_the_threads_rollout(
            self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        day = tmp_path / ".codex" / "sessions" / "2026" / "10" / "23"
        day.mkdir(parents=True)
        (day / "rollout-2026-10-23T10-00-00-thread-xyz.jsonl").write_text(
            json.dumps(dict(self.SESSION_META)) + "\n"
            + json.dumps(dict(self.TURN_CONTEXT)) + "\n")
        state = {"thread_id": "thread-xyz"}
        codex._resolve_model(state)
        assert state["model"] == "gpt-6-astra"
        assert state["model_source"] == "observed", \
            "read back from codex's own record of the run"
        assert state["producer_version"] == "0.155.1"

    def test_without_a_rollout_the_requested_model_is_marked_requested(
            self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        state = {"thread_id": "missing", "requested_model": "gpt-6-astra"}
        codex._resolve_model(state)
        assert state["model"] == "gpt-6-astra"
        assert state["model_source"] == "requested", \
            "we asked for it; codex could in principle have substituted"

    def test_asking_for_nothing_and_finding_nothing_records_nothing(
            self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        state = {"thread_id": "missing"}
        codex._resolve_model(state)
        assert "model" not in state

    def test_the_report_carries_what_was_observed(self, tmp_path, monkeypatch):
        usage = tmp_path / "usage.json"
        monkeypatch.setenv("RETICULI_USAGE", str(usage))
        monkeypatch.setenv("HOME", str(tmp_path))
        codex._report({"tokens": 7, "model": "gpt-6-astra",
                       "model_source": "observed",
                       "provider": "openai", "producer_version": "0.155.1"})
        rec = json.loads(usage.read_text())
        assert rec == {"vendor": "codex", "metered": False, "tokens": 7,
                       "model": "gpt-6-astra", "model_source": "observed",
                       "provider": "openai", "producer_version": "0.155.1"}

    def test_an_unobserved_run_reports_cost_only(self, tmp_path, monkeypatch):
        usage = tmp_path / "usage.json"
        monkeypatch.setenv("RETICULI_USAGE", str(usage))
        monkeypatch.setenv("HOME", str(tmp_path))
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
