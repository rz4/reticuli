"""The cost story: named producers, and the discovery session's bill.

Named producers (`--producer openai[:model]`) expand to the shipped module
with the matched vendor key forwarded; anything else passes through
verbatim, so a producer stays any program. Preflight refuses before money
moves. And a hook-traced session that recorded its harness transcript
prices the claim's C1 from the transcript's own usage entries — usd only
when the harness reported one (no price table: tables drift), tokens
always, everything stamped as the testimony it is.
"""
import json
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))
from reticuli import authoring, cli, kernel


# -- named producers ---------------------------------------------------------

def test_raw_commands_pass_through_verbatim():
    for raw in ("printf hi > g.txt", "python3 mybuild.py", "make impl"):
        command, env = cli._expand_producer(raw)
        assert command == raw and env is None


def test_named_producer_refuses_before_spending(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(kernel.ClaimError) as err:
        cli._expand_producer("openai")
    assert "the openai producer needs" in str(err.value)


def test_named_producer_forwards_only_the_matched_key(monkeypatch):
    import importlib.util
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: object())
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "other-vendor")
    monkeypatch.delenv("RETICULI_PRICE", raising=False)
    command, env = cli._expand_producer("openai:gpt-5-mini")
    assert "-m reticuli.producers.openai" in command and " -P " in command
    assert env["OPENAI_API_KEY"] == "sk-test"
    assert "ANTHROPIC_API_KEY" not in env, "only the matched vendor's key"
    assert env["RETICULI_MODEL"] == "gpt-5-mini"
    assert "PYTHONPATH" in env, "the producer imports THIS reticuli"


# -- the discovery session's bill --------------------------------------------

def _transcript(path, entries):
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(json.dumps(e) + "\n" for e in entries)


def _stamp(offset):
    return time.strftime("%Y-%m-%dT%H:%M:%S+00:00",
                         time.gmtime(time.time() + offset))


def _usage(offset, tokens_in, tokens_out, usd=None):
    entry = {"type": "assistant", "timestamp": _stamp(offset),
             "message": {"usage": {"input_tokens": tokens_in,
                                   "output_tokens": tokens_out}}}
    if usd is not None:
        entry["costUSD"] = usd
    return entry


def test_session_bill_sums_the_window_and_takes_harness_usd(tmp_path):
    transcript = tmp_path / "session.jsonl"
    _transcript(str(transcript), [
        _usage(-9000, 999999, 999999, usd=99.0),   # before the session window
        _usage(-30, 1000, 500, usd=0.02),
        _usage(-10, 2000, 700, usd=0.03),
        {"type": "user", "timestamp": _stamp(-20)},   # no usage: ignored
    ])
    now = time.time()
    ev = [{"event": "session", "transcript": str(transcript), "ts": now - 60},
          {"event": "prompt", "text": "x", "ts": now - 60},
          {"event": "bash", "cmd": "true", "ts": now - 5}]
    bill = authoring._session_bill(ev)
    assert bill["tokens"] == 4200, bill
    assert bill["usd"] == pytest.approx(0.05)
    assert bill["source"] == "agent-transcript"
    assert bill["scope"] == "session-window"


def test_session_bill_is_tokens_only_when_the_harness_names_no_usd(tmp_path):
    transcript = tmp_path / "session.jsonl"
    _transcript(str(transcript), [_usage(-30, 100, 50)])
    now = time.time()
    ev = [{"event": "session", "transcript": str(transcript), "ts": now - 60},
          {"event": "prompt", "text": "x", "ts": now - 60}]
    bill = authoring._session_bill(ev)
    assert bill["tokens"] == 150 and "usd" not in bill, \
        "no price table: usd only when the harness itself reported one"


def test_session_bill_never_blocks_a_pack(tmp_path):
    now = time.time()
    ev = [{"event": "session", "transcript": str(tmp_path / "gone.jsonl"),
           "ts": now}, {"event": "prompt", "text": "x", "ts": now}]
    assert authoring._session_bill(ev) is None
    assert authoring._session_bill([]) is None


def test_discovery_never_enters_the_band(tmp_path):
    # THE REGRESSION THE FIRST REAL PROOF HIT: the session bill fed the
    # cost band as if discovery were production, and a valid three-machine
    # proof was rejected for exhibiting exactly the gap the measurement
    # exists to show. Scope-stamped events total under `discovery`,
    # reported beside the band, never inside it.
    d = tmp_path / "c"
    d.mkdir()
    (d / ".reticuli").mkdir()
    with open(d / ".reticuli" / "ledger.jsonl", "w") as f:
        f.write(json.dumps({"event": "oracle", "calls": 1}) + "\n")
        f.write(json.dumps({"event": "session-usage", "tokens": 154075,
                            "scope": "session-window"}) + "\n")
    totals = kernel.cost(str(d))
    assert totals["calls"] == 1 and "tokens" not in totals, \
        "discovery tokens stay out of the band's units"
    assert totals["discovery"]["tokens"] == 154075, \
        "and stay visible as what they are"


def test_a_billed_claim_still_crosschecks(tmp_path):
    import shutil
    ws = tmp_path / "ws"
    (ws / ".reticuli").mkdir(parents=True)
    (ws / "answer.txt").write_text("42\n")
    transcript = tmp_path / "t.jsonl"
    _transcript(str(transcript), [_usage(-5, 150000, 4075)])
    gate = "grep -qx 42 answer.txt && printf ok > OK"
    now = time.time()
    events = [{"event": "session", "transcript": str(transcript), "ts": now - 30},
              {"event": "prompt", "text": "write it", "ts": now - 30},
              {"event": "write", "path": "answer.txt", "ts": now - 20},
              {"event": "bash", "cmd": gate, "ts": now - 10}]
    with open(ws / ".reticuli" / "draft.jsonl", "w") as f:
        f.write("\n".join(json.dumps(e) for e in events) + "\n")
    import subprocess
    subprocess.run(gate, shell=True, cwd=str(ws), check=True)
    m1 = str(tmp_path / "m1")
    authoring.build_claim(str(ws), ["OK"], m1, name="answer")
    m2 = str(tmp_path / "m2")
    shutil.copytree(m1, m2)
    m3 = str(tmp_path / "m3")
    kernel.rebuild(m1, "printf '42\\n' > answer.txt", m3)
    r = kernel.crosscheck(m1, m2, m3)
    assert r["satisfied"] and r["cost"]["comparable"] is not False, \
        "a 154k-token discovery bill does not reject a 1-call redo"
    assert r["cost"]["M1"]["discovery"]["tokens"] == 154075, \
        "the gap is reported -- it is the useful measure, not a violation"


def test_the_bill_lands_on_the_packed_claim(tmp_path):
    ws = tmp_path / "ws"
    (ws / ".reticuli").mkdir(parents=True)
    (ws / "answer.txt").write_text("42\n")
    transcript = tmp_path / "t.jsonl"
    _transcript(str(transcript), [_usage(-5, 300, 200, usd=0.01)])
    gate = "grep -qx 42 answer.txt && printf ok > OK"
    now = time.time()
    events = [{"event": "session", "transcript": str(transcript), "ts": now - 30},
              {"event": "prompt", "text": "write it", "ts": now - 30},
              {"event": "write", "path": "answer.txt", "ts": now - 20},
              {"event": "bash", "cmd": gate, "ts": now - 10}]
    with open(ws / ".reticuli" / "draft.jsonl", "w") as f:
        f.write("\n".join(json.dumps(e) for e in events) + "\n")
    import subprocess
    subprocess.run(gate, shell=True, cwd=str(ws), check=True)
    claim = tmp_path / "claim"
    authoring.build_claim(str(ws), ["OK"], str(claim), name="answer")
    c1 = kernel.cost(str(claim))
    assert c1["calls"] == 1
    disc = c1["discovery"]
    assert disc["tokens"] == 500, "the transcript's usage priced the discovery"
    assert disc["usd"] == pytest.approx(0.01)
    assert "tokens" not in c1 and "usd" not in c1, \
        "discovery is reported, never fed to the band"
