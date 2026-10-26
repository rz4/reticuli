"""A shipped producer must be reachable by its name, and reach the adapter.

`--producer codex` looked like it worked and did not. The name table held
only the SDK producers, so `codex` fell through to the verbatim-command path
and reticuli ran the bare `codex` binary -- which with no arguments opens the
interactive TUI, reads a piped stdin, and dies with "Error: stdin is not a
terminal". The adapter in producers/codex.py, which knows how to pass a
prompt and observe the model, was never entered. Nothing in the output said
"that is not a producer I know"; the error came from codex and read like a
codex problem.

The second failure was inside the adapter and had the same shape: it named
`--dangerously-bypass-approvals-and-sandbox`, which on codex >= 0.155
refuses a piped prompt for the same reason. The producer always pipes, so
once the dispatch bug was fixed the adapter still could not run.

Both are untestable through the real CLI, so these tests pin the two
decisions directly: which command a name expands to, and which flags the
invocation carries.

Also pinned: the model resolution fallback. The adapter reads codex's own
session log to record WHICH ORACLE RAN, and joined on the thread id from a
`thread.started` event. codex 0.155 emits no such event, so the join falls
back to mtime against a watermark taken before launch -- weaker as a key,
still an observation rather than a declaration.
"""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reticuli import kernel
from reticuli._cli import handlers
from reticuli.producers import codex


# --- which command does a name expand to -------------------------------

@pytest.mark.parametrize("name", ["codex", "claude"])
def test_cli_producer_name_reaches_the_adapter(name, monkeypatch):
    """Not the bare binary: the module that knows how to drive it."""
    import shutil
    monkeypatch.setattr(shutil, "which", lambda b: f"/usr/bin/{b}")

    command, env = handlers._expand_producer(name)

    assert f"reticuli.producers.{name}" in command, (
        f"--producer {name} must run the adapter module; got {command!r}. "
        f"Expanding to the bare `{name}` binary opens its interactive UI and "
        f"dies on a piped prompt.")
    assert command.split()[0] != name, "the bare binary is not the producer"
    assert "-P" in command.split(), (
        "the adapter must import THIS reticuli, not the room's files")
    assert env and env.get("PYTHONPATH"), (
        "the adapter needs our package's parent on PYTHONPATH")


def test_cli_producer_model_rides_the_environment(monkeypatch):
    import shutil
    monkeypatch.setattr(shutil, "which", lambda b: f"/usr/bin/{b}")
    monkeypatch.delenv("RETICULI_MODEL", raising=False)

    command, env = handlers._expand_producer("codex:gpt-6-astra")

    assert env["RETICULI_MODEL"] == "gpt-6-astra"
    assert "gpt-6-astra" not in command, (
        "the model is passed through the environment, not spliced into the "
        "command, so the adapter can also record what it ASKED for")


def test_missing_cli_refuses_by_name_before_anything_runs(monkeypatch):
    """A one-line refusal here, not a traceback from inside the room."""
    import shutil
    monkeypatch.setattr(shutil, "which", lambda b: None)

    with pytest.raises(kernel.ClaimError) as excinfo:
        handlers._expand_producer("codex")

    message = str(excinfo.value)
    assert "codex" in message and "PATH" in message, message


def test_an_unknown_spec_is_still_a_verbatim_command():
    """A producer is any program; the name table must not swallow commands."""
    command, env = handlers._expand_producer("python3 my_producer.py --flag")
    assert command == "python3 my_producer.py --flag"
    assert env is None


def test_every_shipped_adapter_is_nameable():
    """A module in producers/ that no name reaches is a trap, not a feature."""
    shipped = {p.stem for p in
               (Path(handlers.__file__).resolve().parents[1] / "producers")
               .glob("*.py") if not p.stem.startswith("_")}
    nameable = set(handlers._PRODUCERS) | set(handlers._CLI_PRODUCERS)
    assert shipped <= nameable, (
        f"these adapters ship but no --producer name reaches them: "
        f"{sorted(shipped - nameable)}")


# --- which flags does the codex invocation carry ------------------------

def test_codex_argv_never_names_the_tty_only_flag(monkeypatch):
    monkeypatch.delenv("RETICULI_CODEX_SANDBOX", raising=False)
    argv = codex._argv("/usr/bin/codex", None, "/tmp/room")
    assert codex.BANNED_FLAG not in argv, (
        f"{codex.BANNED_FLAG} refuses a piped prompt on codex >= 0.155, and "
        f"this producer always pipes, so naming it makes the producer unable "
        f"to run at all")


def test_codex_argv_asks_for_workspace_write(monkeypatch):
    monkeypatch.delenv("RETICULI_CODEX_SANDBOX", raising=False)
    argv = codex._argv("/usr/bin/codex", None, "/tmp/room")
    assert "--sandbox" in argv
    assert argv[argv.index("--sandbox") + 1] == "workspace-write", (
        "the producer writes files into the blind workspace and runs the gate "
        "there; that is the authority it needs and no more")
    assert argv[-1] == "-", "the prompt arrives on stdin"
    assert "--json" in argv, "the event stream is how cost and model are observed"
    assert argv[argv.index("-C") + 1] == "/tmp/room"


def test_codex_sandbox_is_overridable(monkeypatch):
    monkeypatch.setenv("RETICULI_CODEX_SANDBOX", "read-only")
    argv = codex._argv("/usr/bin/codex", None, "/tmp/room")
    assert argv[argv.index("--sandbox") + 1] == "read-only"


def test_codex_argv_passes_a_requested_model(monkeypatch):
    monkeypatch.delenv("RETICULI_CODEX_SANDBOX", raising=False)
    argv = codex._argv("/usr/bin/codex", "gpt-6-astra", "/tmp/room")
    assert argv[argv.index("-m") + 1] == "gpt-6-astra"


# --- how the oracle is identified when there is no thread id ------------

def _log(root: Path, name: str, mtime: float) -> Path:
    path = root / name
    path.write_text('{"type":"session_meta"}\n')
    os.utime(path, (mtime, mtime))
    return path


def test_rollout_prefers_a_thread_id_match(tmp_path, monkeypatch):
    monkeypatch.setattr(codex, "_sessions_dir", lambda: str(tmp_path))
    _log(tmp_path, "rollout-2026-01-01-THREADX.jsonl", 1000.0)
    newer = _log(tmp_path, "rollout-2026-01-02-OTHER.jsonl", 9000.0)

    found = codex._rollout("THREADX", floor=500.0)

    assert found, "a thread id that names a log must find it"
    assert "THREADX" in os.path.basename(found[0]), (
        f"an exact identifier beats a newer timestamp; got {found[0]!r} "
        f"ahead of it (the newer log is {newer.name})")


def test_rollout_falls_back_to_logs_written_after_the_watermark(tmp_path,
                                                               monkeypatch):
    monkeypatch.setattr(codex, "_sessions_dir", lambda: str(tmp_path))
    _log(tmp_path, "before.jsonl", 1000.0)
    _log(tmp_path, "ours.jsonl", 3000.0)

    found = [os.path.basename(p) for p in codex._rollout("", floor=2000.0)]

    assert found == ["ours.jsonl"], (
        f"with no thread id, only logs newer than the pre-launch watermark "
        f"are candidates; got {found}")


def test_rollout_with_no_watermark_and_no_thread_id_finds_nothing(tmp_path,
                                                                 monkeypatch):
    """Better to record no model than to guess one from an unrelated run."""
    monkeypatch.setattr(codex, "_sessions_dir", lambda: str(tmp_path))
    _log(tmp_path, "someone-elses.jsonl", 1000.0)

    assert codex._rollout("", floor=0.0) == []


def test_session_floor_is_the_newest_mtime(tmp_path, monkeypatch):
    monkeypatch.setattr(codex, "_sessions_dir", lambda: str(tmp_path))
    assert codex._session_floor() == 0.0, "no logs, no watermark"
    _log(tmp_path, "a.jsonl", 1000.0)
    _log(tmp_path, "b.jsonl", 5000.0)
    assert codex._session_floor() == 5000.0


def test_resolved_model_is_marked_observed_not_requested(tmp_path, monkeypatch):
    """The point of reading the log: `observed` outranks `requested`."""
    monkeypatch.setattr(codex, "_sessions_dir", lambda: str(tmp_path))
    path = tmp_path / "ours.jsonl"
    path.write_text(
        '{"type":"turn_context","payload":{"model":"gpt-6-astra"}}\n')
    os.utime(path, (3000.0, 3000.0))

    state = {"session_floor": 2000.0, "requested_model": "something-else"}
    codex._resolve_model(state)

    assert state["model"] == "gpt-6-astra", (
        "the model must come from codex's own record, not the flag we hoped "
        "it honored")
    assert state["model_source"] == "observed"


def test_requested_model_is_the_honest_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(codex, "_sessions_dir", lambda: str(tmp_path))
    state = {"session_floor": 2000.0, "requested_model": "gpt-6-astra"}
    codex._resolve_model(state)
    assert state["model"] == "gpt-6-astra"
    assert state["model_source"] == "requested", (
        "a model we asked for is not a model we saw, and a proof must say "
        "which it was")


# --- which pinned inputs a producer is told to read ---------------------

def test_data_inputs_are_not_offered_for_reading(tmp_path):
    """A pinned dataset must not be listed among the files to read.

    The producer contract says to read every input in full. A claim pinning a
    3MB MNIST subset and a 916KB checkpoint sent one producer into megabytes
    of binary: 794,891 tokens spent, no implementation written, gate never
    reached. Identity is unaffected either way -- both kinds stay pinned and
    present -- so this is purely about what the prompt asks for.
    """
    from reticuli.producers import _inputs

    check = tmp_path / "check.py"
    check.write_text("assert True\n")
    recipe = tmp_path / "claim.toml"
    recipe.write_text('[claim]\nname = "x"\n')
    binary = tmp_path / "weights.pth"
    binary.write_bytes(b"PK\x03\x04\x00\x00pickled")
    idx = tmp_path / "images-idx3-ubyte"
    idx.write_bytes(b"\x00\x00\x08\x03" + bytes(4096))
    huge = tmp_path / "table.csv"
    huge.write_text("a,b\n" * 200_000)          # text, but far past the cap

    paths = [str(p) for p in (check, recipe, binary, idx, huge)]
    read, data = _inputs.split(paths)

    assert read == [str(check), str(recipe)], (
        f"only the small text criteria should be offered for reading; got "
        f"{read}")
    assert data == [str(binary), str(idx), str(huge)], (
        f"binary and oversized inputs are data; got {data}")
    assert str(binary) in _inputs.note(data), (
        "the prompt must name the data inputs it is telling the model to skip")
    assert _inputs.note([]) == "", "no data inputs, no note"


def test_both_adapters_share_one_classifier():
    """The prompt line is duplicated across adapters, so a fix must not be.

    R16 existed identically in codex.py and claude.py because they carry the
    same instruction. Fixing one and leaving the other to rediscover it is
    the failure this pins.
    """
    import inspect

    from reticuli.producers import claude, codex

    for adapter in (codex, claude):
        source = inspect.getsource(adapter)
        assert "_inputs.split" in source, (
            f"{adapter.__name__} must classify its inputs through the shared "
            f"module, not its own copy")
        assert "{to_read}" in source, (
            f"{adapter.__name__}'s prompt must offer only the readable "
            f"inputs")
        assert "{inputs}" not in source, (
            f"{adapter.__name__} still interpolates the whole input list")


# --- a proof must name the oracle that survived it ---------------------

def test_claude_producer_records_its_model(tmp_path, monkeypatch):
    """R14 for the other adapter: it recorded vendor and nothing else.

    A cross-family rebuild is the control for producer dependence, so a proof
    earned here that says only "claude-code" cannot support the claim the run
    was made to establish.
    """
    from reticuli.producers import claude

    usage = tmp_path / "usage.json"
    monkeypatch.setenv("RETICULI_USAGE", str(usage))
    monkeypatch.setenv("RETICULI_MODEL", "claude-opus-5")
    claude._report()

    record = json.loads(usage.read_text())
    assert record["vendor"] == "claude-code"
    assert record["model"] == "claude-opus-5", (
        f"the model must be recorded; got {record}")
    assert record["model_source"] == "requested", (
        "a model we asked for is not a model we observed, and the record "
        "must say which it was")
    assert record["metered"] is False, (
        "a subscription has no per-token line; saying so is honest")


def test_claude_producer_omits_a_model_it_was_not_given(tmp_path, monkeypatch):
    """No model named, no model claimed -- silence beats invention."""
    from reticuli.producers import claude

    usage = tmp_path / "usage.json"
    monkeypatch.setenv("RETICULI_USAGE", str(usage))
    monkeypatch.delenv("RETICULI_MODEL", raising=False)
    claude._report()

    record = json.loads(usage.read_text())
    assert "model" not in record, (
        f"with no model requested the record must not invent one; got {record}")
    assert record["vendor"] == "claude-code"
