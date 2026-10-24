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
