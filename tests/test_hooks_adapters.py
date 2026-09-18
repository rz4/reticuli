"""Multi-harness capture. The generic adapter accepts reticuli's own event
shape, so any harness can integrate by emitting it; the Claude Code adapter
still maps that product's vocabulary; and the wired hook command adapts to how
reticuli is reachable, so a harness is never pointed at a command that is not
there (the silent-no-op the audit found).

    pytest tests/test_hooks_adapters.py   (or: python3 tests/test_hooks_adapters.py)
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from reticuli import hooks


def _session(tmp: str) -> str:
    os.makedirs(os.path.join(tmp, ".reticuli"))
    return tmp


def test_generic_adapter_traces_canonical_events() -> None:
    with tempfile.TemporaryDirectory() as ws:
        _session(ws)
        assert hooks.event({"event": "write", "path": "a.py"}, ws)["event"] == "write"
        assert hooks.event({"event": "bash", "cmd": "pytest"}, ws)["event"] == "bash"
        assert hooks.event({"event": "prompt", "text": "do it"}, ws)["event"] == "prompt"
        r = hooks.event({"event": "read", "path": "a.py"}, ws)
        assert r["event"] == "read" and r["path"] == "a.py" and r["via"] == "hook"


def test_generic_adapter_confines_paths() -> None:
    with tempfile.TemporaryDirectory() as ws:
        _session(ws)
        assert hooks.event({"event": "write", "path": "../escape.py"}, ws) is None, \
            "a path outside the session is not traced"


def test_claude_adapter_still_maps_its_vocabulary() -> None:
    with tempfile.TemporaryDirectory() as ws:
        _session(ws)
        ev = hooks.event({"hook_event_name": "PostToolUse", "tool_name": "Bash",
                          "tool_input": {"command": "make"}}, ws)
        assert ev and ev["event"] == "bash" and ev["cmd"] == "make"


def test_no_session_is_a_silent_noop() -> None:
    with tempfile.TemporaryDirectory() as ws:      # no .reticuli store
        assert hooks.event({"event": "bash", "cmd": "x"}, ws) is None


def test_hook_command_adapts_to_reachability() -> None:
    assert hooks._is_reticuli_hook("ret hook")
    assert hooks._is_reticuli_hook("/usr/bin/python3 -m reticuli hook")
    saved = os.environ.get("PATH", "")
    try:
        os.environ["PATH"] = ""                     # no `ret` resolvable
        cmd = hooks._hook_command()
        assert cmd.endswith("-m reticuli hook"), cmd
        assert hooks._is_reticuli_hook(cmd)
    finally:
        os.environ["PATH"] = saved


def test_install_is_idempotent() -> None:
    with tempfile.TemporaryDirectory() as proj:
        first = hooks.install(proj)
        assert first["wired"], "first install wires both events"
        again = hooks.install(proj)
        assert not again["wired"], "a second install recognizes the wiring"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("hooks-adapters-ok")
